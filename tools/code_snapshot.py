"""Snapshots TRANSACTIONNELS du workspace pour les éditions de code — le « /rewind ».

Un commit FANTÔME est pris automatiquement avant la PREMIÈRE mutation de fichier d'un
run (write_file/edit_file/apply_patch, cf. tools/code_edit) : si la série d'éditions
casse les tests et que l'autofix n'y arrive pas, on revient d'un coup à l'état d'avant.

Mécanisme : un dépôt git PARALLÈLE (« shadow », git-dir séparé `.athena_shadow/` dans le
workspace, work-tree = workspace) → fonctionne aussi sur les projets SANS dépôt git, et
ne touche jamais au vrai `.git` du projet (index, stash et historique intacts). Les
répertoires lourds/dérivés (venv, node_modules, caches) sont exclus des snapshots et
PROTÉGÉS au rollback (clean respecte les exclusions).
"""
import os
import subprocess
import contextvars

_SHADOW = ".athena_shadow"
_EXCLUDES = [_SHADOW + "/", ".git/", "__pycache__/", "*.pyc", ".venv/", "venv/",
             "node_modules/", ".chroma_db/", ".tts_cache/", "dist/", "build/",
             ".pytest_cache/", ".mypy_cache/", ".ruff_cache/"]

# Snapshot pris automatiquement au 1er outil MUTANT du run courant (posé par code_edit).
run_snapshot_id: "contextvars.ContextVar" = contextvars.ContextVar("run_snapshot_id", default=None)


def _workspace_dir():
    try:
        from core.state import get_workspace_dir
        return os.path.realpath(get_workspace_dir())
    except Exception:
        base = os.getenv("ACTIVE_WORKSPACE_DIR", "").strip() or os.path.join(os.getcwd(), "workspace")
        return os.path.realpath(base)


def _git(ws: str, args: list, timeout: int = 60):
    """git avec le dépôt SHADOW (git-dir séparé) sur le work-tree du workspace."""
    env = dict(os.environ,
               GIT_AUTHOR_NAME="athena", GIT_AUTHOR_EMAIL="athena@local",
               GIT_COMMITTER_NAME="athena", GIT_COMMITTER_EMAIL="athena@local")
    res = subprocess.run(
        ["git", "--git-dir", os.path.join(ws, _SHADOW), "--work-tree", ws] + args,
        capture_output=True, text=True, timeout=timeout, env=env)
    return res.returncode, (res.stdout or "").strip(), (res.stderr or "").strip()


def _ensure_shadow(ws: str):
    shadow = os.path.join(ws, _SHADOW)
    if not os.path.isdir(shadow):
        rc, _, err = _git(ws, ["init", "-q"])
        if rc != 0:
            raise RuntimeError(f"init du dépôt shadow impossible : {err}")
    # Exclusions (relues à chaque fois : la liste peut évoluer entre versions).
    info = os.path.join(shadow, "info")
    os.makedirs(info, exist_ok=True)
    with open(os.path.join(info, "exclude"), "w", encoding="utf-8") as f:
        f.write("\n".join(_EXCLUDES) + "\n")


def take_snapshot(label: str = "") -> str:
    """Commit fantôme de l'état actuel du workspace. Renvoie l'id (hash court)."""
    ws = _workspace_dir()
    _ensure_shadow(ws)
    rc, _, err = _git(ws, ["add", "-A"])
    if rc != 0:
        raise RuntimeError(f"snapshot impossible (add) : {err}")
    rc, _, err = _git(ws, ["commit", "-q", "--allow-empty",
                           "-m", label or "snapshot avant édition"])
    if rc != 0:
        raise RuntimeError(f"snapshot impossible (commit) : {err}")
    rc, out, err = _git(ws, ["rev-parse", "--short", "HEAD"])
    if rc != 0:
        raise RuntimeError(f"snapshot illisible : {err}")
    return out


def auto_snapshot_before_mutation():
    """Appelé par code_edit avant chaque écriture : prend UN snapshot par run (le
    premier), mémorisé dans run_snapshot_id. Best-effort (git absent → no-op)."""
    if run_snapshot_id.get() is not None:
        return run_snapshot_id.get() or None
    try:
        snap = take_snapshot("auto : état avant les éditions de ce run")
        run_snapshot_id.set(snap)
        return snap
    except Exception:
        run_snapshot_id.set("")  # marqueur « tenté, indisponible » : on ne réessaie pas
        return None


def code_snapshot(label: str = "") -> str:
    """
    Prend un SNAPSHOT du workspace (commit fantôme, n'affecte pas le vrai dépôt git du
    projet). À utiliser avant une série d'éditions risquées ; code_rollback y revient.

    Args:
        label (str): Description optionnelle du snapshot.

    Returns:
        str: L'identifiant du snapshot.
    """
    try:
        snap = take_snapshot(label or "snapshot manuel")
        return f"📸 Snapshot {snap} pris. Reviens-y avec code_rollback('{snap}') si besoin."
    except Exception as e:
        return f"Erreur snapshot : {e}"


def code_rollback(snapshot_id: str = "") -> str:
    """
    REVIENT à un snapshot du workspace : toutes les éditions faites depuis (fichiers
    modifiés ET créés) sont annulées. Sans argument : snapshot automatique du début du
    run (état d'avant tes éditions). Utilise-le quand les tests restent cassés malgré
    tes tentatives de correction.

    Args:
        snapshot_id (str): Id renvoyé par code_snapshot (vide = snapshot auto du run).

    Returns:
        str: Confirmation (fichiers restaurés) ou erreur.
    """
    from core import projects
    if not projects.can_write():
        return "Erreur : édition non autorisée (accès en lecture seule)."
    ws = _workspace_dir()
    snap = (snapshot_id or "").strip() or (run_snapshot_id.get() or "")
    if not snap:
        return ("Erreur : aucun snapshot (ni id fourni, ni snapshot automatique dans ce "
                "run — aucune édition n'a encore eu lieu ?).")
    if not os.path.isdir(os.path.join(ws, _SHADOW)):
        return "Erreur : aucun dépôt de snapshots dans ce workspace."
    rc, _, err = _git(ws, ["checkout", "-q", snap, "--", "."])
    if rc != 0:
        return f"Erreur rollback (checkout {snap}) : {err}"
    # Supprime les fichiers CRÉÉS depuis le snapshot (non suivis par lui). clean
    # respecte info/exclude → venv/node_modules/etc. ne sont jamais touchés.
    rc, out, err = _git(ws, ["clean", "-fdq"])
    if rc != 0:
        return f"Rollback partiel : fichiers restaurés, mais nettoyage incomplet ({err})."
    return (f"⏪ Rollback au snapshot {snap} : le workspace est revenu à l'état d'avant "
            "les éditions (fichiers modifiés restaurés, fichiers créés supprimés).")


def list_snapshots(limit: int = 10) -> str:
    """Snapshots récents du workspace (id + label), le plus récent d'abord."""
    ws = _workspace_dir()
    if not os.path.isdir(os.path.join(ws, _SHADOW)):
        return "Aucun snapshot pour ce workspace."
    rc, out, err = _git(ws, ["log", "--oneline", f"-{max(1, int(limit))}"])
    return out if rc == 0 and out else (err or "Aucun snapshot.")

"""Outils git agentiques, confinés au dépôt du workspace.

Permettent à un agent codeur d'inspecter et de versionner son travail : statut, diff,
log, création de branche, commit. Exécution SANS shell (liste d'arguments → pas
d'injection), via `git -C <workspace>` (confiné au dépôt du workspace). Le PUSH n'est
volontairement PAS exposé : pousser vers un distant reste une action humaine.
"""
import os
import re
import subprocess


def _workspace_dir():
    try:
        import server
        return os.path.realpath(server.get_workspace_dir())
    except Exception:
        base = os.getenv("ACTIVE_WORKSPACE_DIR", "").strip() or os.path.join(os.getcwd(), "workspace")
        return os.path.realpath(base)


def _resolve_dir(subdir: str = ""):
    """Répertoire cible (workspace ou un sous-dossier, ex. un worktree), confiné au
    workspace. Renvoie (abspath, None) ou (None, err)."""
    ws = _workspace_dir()
    sub = (subdir or "").strip().strip("/")
    if not sub:
        return ws, None
    real = os.path.realpath(os.path.join(ws, sub))
    if os.path.commonpath([real, ws]) != ws:
        return None, "Erreur : chemin hors du workspace refusé."
    return real, None


def _run_git(args, timeout: int = 30, subdir: str = ""):
    target, err = _resolve_dir(subdir)
    if err:
        return 1, "", err
    try:
        res = subprocess.run(["git", "-C", target] + args, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return 127, "", "git n'est pas installé sur l'hôte."
    except subprocess.TimeoutExpired:
        return 124, "", f"git a dépassé le délai de {timeout}s."
    except Exception as e:
        return 1, "", str(e)


def _is_repo(subdir: str = "") -> bool:
    rc, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"], subdir=subdir)
    return rc == 0 and out.strip() == "true"


def _need_repo(subdir: str = ""):
    if not _is_repo(subdir):
        return "Erreur : le workspace n'est pas un dépôt git (utilise « git init » via execute_bash_command si voulu)."
    return None


def git_status(subdir: str = "") -> str:
    """Affiche l'état du dépôt git (branche courante + fichiers modifiés).
    subdir: sous-dossier du workspace (ex. un worktree '.worktrees/feature-x')."""
    err = _need_repo(subdir)
    if err:
        return err
    rc, branch, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], subdir=subdir)
    rc2, out, errout = _run_git(["status", "--short"], subdir=subdir)
    if rc2 != 0:
        return f"Erreur git status : {errout.strip()}"
    body = out.strip() or "(arbre de travail propre)"
    return f"[branche : {branch.strip()}]\n{body}"


def git_diff(path: str = "", staged: bool = False, subdir: str = "") -> str:
    """Affiche le diff. path: limiter à un fichier. staged=True pour les modifs indexées.
    subdir: sous-dossier du workspace (ex. un worktree)."""
    err = _need_repo(subdir)
    if err:
        return err
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args += ["--", path]
    rc, out, errout = _run_git(args, timeout=30, subdir=subdir)
    if rc != 0:
        return f"Erreur git diff : {errout.strip()}"
    out = out.strip()
    if not out:
        return "(aucune différence)"
    if len(out) > 8000:
        out = out[:8000] + "\n… [diff tronqué]"
    return out


def git_log(count: int = 10, subdir: str = "") -> str:
    """Affiche les derniers commits (hash court + message). count: nombre de commits.
    subdir: sous-dossier du workspace (ex. un worktree)."""
    err = _need_repo(subdir)
    if err:
        return err
    count = max(1, min(int(count or 10), 100))
    rc, out, errout = _run_git(["log", f"-{count}", "--pretty=format:%h %ad %s", "--date=short"], subdir=subdir)
    if rc != 0:
        return f"Erreur git log : {errout.strip()}"
    return out.strip() or "(aucun commit)"


def git_create_branch(name: str, subdir: str = "") -> str:
    """Crée une nouvelle branche et bascule dessus (git checkout -b). name: nom de branche.
    subdir: sous-dossier du workspace (ex. un worktree)."""
    err = _need_repo(subdir)
    if err:
        return err
    name = (name or "").strip()
    if not re.match(r"^[A-Za-z0-9._/-]+$", name) or name.startswith("-"):
        return "Erreur : nom de branche invalide (lettres, chiffres, . _ / - uniquement)."
    rc, out, errout = _run_git(["checkout", "-b", name], subdir=subdir)
    if rc != 0:
        return f"Erreur création de branche : {(errout or out).strip()}"
    return f"Branche créée et active : {name}"


def git_commit(message: str, all_changes: bool = True, subdir: str = "") -> str:
    """
    Indexe les modifications puis crée un commit. message: message de commit (sémantique).
    all_changes=True indexe tout le suivi modifié (git add -A) ; sinon ne commite que ce
    qui est déjà indexé. subdir: sous-dossier du workspace (ex. un worktree). Ne POUSSE pas.
    """
    err = _need_repo(subdir)
    if err:
        return err
    message = (message or "").strip()
    if not message:
        return "Erreur : message de commit vide."
    if all_changes:
        rc, _o, e = _run_git(["add", "-A"], subdir=subdir)
        if rc != 0:
            return f"Erreur git add : {e.strip()}"
    rc, out, errout = _run_git(["commit", "-m", message], subdir=subdir)
    combined = (out + "\n" + errout).strip()
    if rc != 0:
        if "nothing to commit" in combined.lower():
            return "Rien à committer (arbre de travail propre)."
        if "Please tell me who you are" in combined or "user.email" in combined:
            return ("Erreur : identité git non configurée. Configure user.name/user.email "
                    "dans le dépôt avant de committer.")
        return f"Erreur git commit : {combined}"
    rc2, short, _ = _run_git(["rev-parse", "--short", "HEAD"], subdir=subdir)
    return f"Commit créé ({short.strip()}) : {message}"


# --- Worktrees : répertoires de travail isolés (branches en parallèle) ------
def _branch_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-") or "wt"


def git_create_worktree(branch: str) -> str:
    """
    Crée un WORKTREE isolé (répertoire de travail séparé sur une nouvelle branche) sous
    .worktrees/ DANS le workspace, pour bosser une feature sans toucher l'arbre principal.
    Renvoie le sous-dossier à passer aux autres outils (read_file/edit_file/git_* via subdir).
    branch: nom de la branche (créée si absente).
    """
    err = _need_repo()
    if err:
        return err
    branch = (branch or "").strip()
    if not re.match(r"^[A-Za-z0-9._/-]+$", branch) or branch.startswith("-"):
        return "Erreur : nom de branche invalide."
    rel = os.path.join(".worktrees", _branch_slug(branch))
    target, derr = _resolve_dir(rel)
    if derr:
        return derr
    if os.path.exists(target):
        return f"Un worktree existe déjà : {rel}"
    # -B : crée ou réinitialise la branche sur HEAD courant.
    rc, out, errout = _run_git(["worktree", "add", "-B", branch, target])
    if rc != 0:
        return f"Erreur worktree : {(errout or out).strip()}"
    return (f"Worktree créé : {rel} (branche « {branch} »). Utilise subdir='{rel}' sur "
            "read_file/edit_file/run_checks/git_* pour y travailler.")


def git_list_worktrees() -> str:
    """Liste les worktrees du dépôt (chemin + branche)."""
    err = _need_repo()
    if err:
        return err
    rc, out, errout = _run_git(["worktree", "list"])
    if rc != 0:
        return f"Erreur : {errout.strip()}"
    ws = _workspace_dir()
    lines = []
    for l in (out or "").splitlines():
        lines.append(l.replace(ws + os.sep, "").replace(ws, "."))
    return "\n".join(lines) or "(aucun worktree)"


def git_remove_worktree(subdir: str) -> str:
    """Supprime un worktree (par son sous-dossier, ex. '.worktrees/feature-x'). La branche
    associée est conservée. subdir: le sous-dossier renvoyé par git_create_worktree."""
    err = _need_repo()
    if err:
        return err
    target, derr = _resolve_dir(subdir)
    if derr:
        return derr
    if target == _workspace_dir():
        return "Erreur : refuse de supprimer le workspace principal."
    rc, out, errout = _run_git(["worktree", "remove", "--force", target])
    if rc != 0:
        return f"Erreur : {(errout or out).strip()}"
    return f"Worktree supprimé : {subdir}"

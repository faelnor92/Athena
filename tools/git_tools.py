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


def _run_git(args, timeout: int = 30):
    ws = _workspace_dir()
    try:
        res = subprocess.run(["git", "-C", ws] + args, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return 127, "", "git n'est pas installé sur l'hôte."
    except subprocess.TimeoutExpired:
        return 124, "", f"git a dépassé le délai de {timeout}s."
    except Exception as e:
        return 1, "", str(e)


def _is_repo() -> bool:
    rc, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


def _need_repo():
    if not _is_repo():
        return "Erreur : le workspace n'est pas un dépôt git (utilise « git init » via execute_bash_command si voulu)."
    return None


def git_status() -> str:
    """Affiche l'état du dépôt git du workspace (branche courante + fichiers modifiés)."""
    err = _need_repo()
    if err:
        return err
    rc, branch, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    rc2, out, errout = _run_git(["status", "--short"])
    if rc2 != 0:
        return f"Erreur git status : {errout.strip()}"
    body = out.strip() or "(arbre de travail propre)"
    return f"[branche : {branch.strip()}]\n{body}"


def git_diff(path: str = "", staged: bool = False) -> str:
    """Affiche le diff du workspace. path: limiter à un fichier (optionnel).
    staged=True pour le diff des modifications déjà indexées (git diff --cached)."""
    err = _need_repo()
    if err:
        return err
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        args += ["--", path]
    rc, out, errout = _run_git(args, timeout=30)
    if rc != 0:
        return f"Erreur git diff : {errout.strip()}"
    out = out.strip()
    if not out:
        return "(aucune différence)"
    if len(out) > 8000:
        out = out[:8000] + "\n… [diff tronqué]"
    return out


def git_log(count: int = 10) -> str:
    """Affiche les derniers commits (hash court + message). count: nombre de commits."""
    err = _need_repo()
    if err:
        return err
    count = max(1, min(int(count or 10), 100))
    rc, out, errout = _run_git(["log", f"-{count}", "--pretty=format:%h %ad %s", "--date=short"])
    if rc != 0:
        return f"Erreur git log : {errout.strip()}"
    return out.strip() or "(aucun commit)"


def git_create_branch(name: str) -> str:
    """Crée une nouvelle branche et bascule dessus (git checkout -b). name: nom de branche."""
    err = _need_repo()
    if err:
        return err
    name = (name or "").strip()
    if not re.match(r"^[A-Za-z0-9._/-]+$", name) or name.startswith("-"):
        return "Erreur : nom de branche invalide (lettres, chiffres, . _ / - uniquement)."
    rc, out, errout = _run_git(["checkout", "-b", name])
    if rc != 0:
        return f"Erreur création de branche : {(errout or out).strip()}"
    return f"Branche créée et active : {name}"


def git_commit(message: str, all_changes: bool = True) -> str:
    """
    Indexe les modifications puis crée un commit dans le dépôt du workspace.
    message: message de commit (sémantique). all_changes=True indexe tout le suivi
    modifié (git add -A) ; sinon ne commite que ce qui est déjà indexé. Ne POUSSE pas.
    """
    err = _need_repo()
    if err:
        return err
    message = (message or "").strip()
    if not message:
        return "Erreur : message de commit vide."
    if all_changes:
        rc, _o, e = _run_git(["add", "-A"])
        if rc != 0:
            return f"Erreur git add : {e.strip()}"
    rc, out, errout = _run_git(["commit", "-m", message])
    combined = (out + "\n" + errout).strip()
    if rc != 0:
        if "nothing to commit" in combined.lower():
            return "Rien à committer (arbre de travail propre)."
        if "Please tell me who you are" in combined or "user.email" in combined:
            return ("Erreur : identité git non configurée. Configure user.name/user.email "
                    "dans le dépôt avant de committer.")
        return f"Erreur git commit : {combined}"
    rc2, short, _ = _run_git(["rev-parse", "--short", "HEAD"])
    return f"Commit créé ({short.strip()}) : {message}"

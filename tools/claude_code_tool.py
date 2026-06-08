"""Plugin Claude Code — délègue une tâche de CODE à l'agent Claude Code (CLI headless).

Athena orchestre, Claude Code (agent frontier d'Anthropic) exécute le travail de code DANS
le dossier du PROJET ACTIF. C'est le pattern « agent externe exposé comme outil ».

Sécurité / cadrage :
  - exécution scopée au dossier du projet actif (cwd + --add-dir) ;
  - permissions bornées par défaut (`acceptEdits` : éditions auto-acceptées, pas de bypass) ;
  - opt-in explicite (désactivé par défaut) ; timeout.

Variables d'environnement :
  CLAUDE_CODE_ENABLED     "true" pour activer (défaut false)
  CLAUDE_CODE_BIN         chemin du binaire (défaut: `claude` du PATH)
  CLAUDE_CODE_TIMEOUT     secondes (défaut 300)
  CLAUDE_CODE_PERMISSION  --permission-mode : default | acceptEdits (défaut) | plan | bypassPermissions
  CLAUDE_CODE_MODEL       modèle imposé (optionnel)
  CLAUDE_CODE_ALLOWED_TOOLS  liste --allowedTools (optionnel, ex: "Edit Write Read")
"""
import os
import json
import shutil
import subprocess


def _bin() -> str:
    return os.getenv("CLAUDE_CODE_BIN", "").strip() or (shutil.which("claude") or "")


def available() -> bool:
    """Vrai si le binaire Claude Code est présent."""
    return bool(_bin())


def enabled() -> bool:
    # Toggle runtime (Réglages > Plugins) prioritaire ; repli sur la variable d'env.
    try:
        from core import shared_store
        v = shared_store.get("plugins", "claude_code_enabled", None)
        if v is not None:
            return bool(v)
    except Exception:
        pass
    return os.getenv("CLAUDE_CODE_ENABLED", "false").lower() in ("true", "1", "yes")


def _project_dir() -> str:
    try:
        from core.state import get_workspace_dir
        return os.path.abspath(get_workspace_dir())
    except Exception:
        return os.getcwd()


def claude_code(task: str) -> str:
    """Délègue une tâche de CODE à Claude Code (agent de code frontier) dans le PROJET ACTIF :
    écrire/modifier/déboguer/refactorer du code, sur plusieurs fichiers, etc. Renvoie le
    compte-rendu de Claude Code. À privilégier pour du code complexe nécessitant un agent
    de code puissant. Décris la tâche précisément (fichiers, objectif, contraintes)."""
    if not enabled():
        return ("Erreur : le plugin Claude Code est désactivé. Active-le dans Réglages > Plugins "
                "(ou CLAUDE_CODE_ENABLED=true).")
    binp = _bin()
    if not binp:
        return ("Erreur : binaire `claude` introuvable. Installe Claude Code (npm i -g "
                "@anthropic-ai/claude-code) ou définis CLAUDE_CODE_BIN.")
    if not (task or "").strip():
        return "Erreur : tâche vide."
    cwd = _project_dir()
    timeout = int(os.getenv("CLAUDE_CODE_TIMEOUT", "300") or 300)
    perm = os.getenv("CLAUDE_CODE_PERMISSION", "acceptEdits").strip()
    cmd = [binp, "-p", task, "--output-format", "json", "--permission-mode", perm, "--add-dir", cwd]
    model = os.getenv("CLAUDE_CODE_MODEL", "").strip()
    if model:
        cmd += ["--model", model]
    allowed = os.getenv("CLAUDE_CODE_ALLOWED_TOOLS", "").strip()
    if allowed:
        cmd += ["--allowedTools"] + allowed.split()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"Erreur : Claude Code a dépassé le délai ({timeout}s)."
    except Exception as e:
        return f"Erreur lors de l'appel à Claude Code : {e}"
    out = (r.stdout or "").strip()
    # --output-format json : objet avec 'result' (texte final de l'agent).
    try:
        data = json.loads(out)
        if isinstance(data, dict):
            txt = data.get("result") or data.get("text") or out
            return str(txt)[:8000]
    except Exception:
        pass
    return (out or (r.stderr or "").strip()[:2000] or "Claude Code n'a rien renvoyé.")[:8000]

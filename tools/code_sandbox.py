import sys
import subprocess
import tempfile
import os

from tools import sandbox_runner


def _format_output(stdout: str, stderr: str) -> str:
    output = ""
    if stdout:
        output += f"--- SORTIE (stdout) ---\n{stdout}\n"
    if stderr:
        output += f"--- ERREUR (stderr) ---\n{stderr}\n"
    if not output:
        output = "Code exécuté avec succès (aucune sortie)."
    return output


def _run_local_unsandboxed(code: str) -> str:
    """Repli NON ISOLÉ : exécute le code avec les droits du serveur.
    Utilisé uniquement si SANDBOX_MODE=off (risque explicitement assumé)."""
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
        f.write(code)
        temp_path = f.name
    try:
        try:
            from core.state import get_workspace_dir
            cwd = get_workspace_dir()
        except Exception:
            cwd = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True, text=True, timeout=15, cwd=cwd,
        )
        return _format_output(result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return "Erreur: Temps d'exécution dépassé (Timeout de 15 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution: {str(e)}"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def execute_python_code(code: str) -> str:
    """
    Exécute un script Python dans une sandbox Docker jetable et isolée
    (réseau coupé, RAM/CPU/PID bornés, racine en lecture seule, sans privilèges,
    seul le workspace monté en écriture) puis capture stdout/stderr.

    Si la variable d'environnement SANDBOX_MODE vaut "off", le code est exécuté
    localement SANS isolation (avec les droits du serveur) — à n'utiliser qu'en
    développement et en toute connaissance de cause.

    Args:
        code (str): Le code Python complet à exécuter.

    Returns:
        str: Le résultat de l'exécution (stdout ou les erreurs stderr).
    """
    # Projet en LECTURE SEULE (membre « viewer ») : le workspace est monté en écriture
    # dans la sandbox → on refuse l'exécution de code pour préserver la lecture seule.
    try:
        from core import projects
        if not projects.can_write():
            return "Erreur : projet en LECTURE SEULE (rôle lecteur) — exécution de code refusée."
    except Exception:
        pass

    if sandbox_runner.sandbox_mode() == "off":
        return _run_local_unsandboxed(code)

    if not sandbox_runner.docker_available():
        return (
            "Erreur sandbox : Docker est requis pour exécuter du code de manière isolée "
            "mais n'est pas disponible (démon arrêté ou binaire absent). "
            "Démarrez Docker, ou définissez SANDBOX_MODE=off pour une exécution locale "
            "NON isolée (risque assumé)."
        )

    stdout, stderr, _rc = sandbox_runner.run_python(code, timeout=15)
    return _format_output(stdout, stderr)

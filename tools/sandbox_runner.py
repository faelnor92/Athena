"""Exécution de code/commande isolée dans un conteneur Docker jetable.

Objectif : remplacer l'ancienne « fausse sandbox » (subprocess local avec les
droits du serveur) par une isolation réelle.

Contraintes appliquées au conteneur :
  - réseau coupé           (--network none)
  - RAM / CPU / PID bornés (--memory, --cpus, --pids-limit)
  - racine en lecture seule (--read-only) + /tmp en tmpfs
  - aucune capacité Linux  (--cap-drop ALL, --security-opt no-new-privileges)
  - exécution sous l'UID hôte pour que les fichiers créés restent accessibles
  - seul le workspace actif est monté en écriture sur /work

Pilotage par variables d'environnement :
  SANDBOX_MODE          "docker" (défaut) | "off" (exécution locale, risque assumé)
  SANDBOX_DOCKER_IMAGE  image de base (défaut: python:3.11-slim)
  SANDBOX_MEM_LIMIT     ex: "256m"
  SANDBOX_CPUS          ex: "1.0"
  SANDBOX_PIDS_LIMIT    ex: "128"
"""
import os
import shlex
import shutil
import subprocess
import uuid
from typing import List, Optional, Tuple

DEFAULT_IMAGE = "python:3.11-slim"


def sandbox_mode() -> str:
    return os.getenv("SANDBOX_MODE", "docker").strip().lower()


def docker_available() -> bool:
    """Vrai si le binaire docker existe ET que le démon répond."""
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def _workspace_dir() -> str:
    ws = os.path.abspath(os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd()))
    os.makedirs(ws, exist_ok=True)
    return ws


def _docker_run_args(name: str) -> List[str]:
    ws = _workspace_dir()
    # Réseau coupé par défaut ; activable explicitement si du code doit sortir.
    network = "bridge" if os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower() in ("true", "1", "yes") else "none"
    args = [
        "docker", "run", "--rm", "-i",
        "--name", name,
        "--network", network,
        "--memory", os.getenv("SANDBOX_MEM_LIMIT", "256m"),
        "--memory-swap", os.getenv("SANDBOX_MEM_LIMIT", "256m"),
        "--cpus", os.getenv("SANDBOX_CPUS", "1.0"),
        "--pids-limit", os.getenv("SANDBOX_PIDS_LIMIT", "128"),
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,size=64m",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "-v", f"{ws}:/work",
        "-w", "/work",
    ]
    # Exécuter sous l'UID/GID de l'hôte (indisponible sous Windows).
    if hasattr(os, "getuid"):
        args += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return args


def _execute(extra_args: List[str], stdin_data: str, timeout: int) -> Tuple[str, str, int]:
    """Lance le conteneur, renvoie (stdout, stderr, returncode)."""
    name = f"athena-sbx-{uuid.uuid4().hex[:12]}"
    image = os.getenv("SANDBOX_DOCKER_IMAGE", DEFAULT_IMAGE)
    cmd = _docker_run_args(name) + [image] + extra_args
    try:
        r = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        # Le conteneur peut survivre au timeout du client : on le tue.
        subprocess.run(["docker", "kill", name], capture_output=True)
        return "", f"Erreur : délai d'exécution dépassé (Timeout de {timeout} secondes).", 124
    except Exception as e:
        return "", f"Erreur sandbox Docker : {e}", 1


def run_python(code: str, timeout: int = 15) -> Tuple[str, str, int]:
    """Exécute du code Python dans le conteneur (code passé via stdin)."""
    # `python -` lit le script depuis stdin.
    return _execute(["python", "-"], stdin_data=code, timeout=timeout)


def run_bash(command: str, timeout: int = 15, workdir: Optional[str] = None) -> Tuple[str, str, int]:
    """Exécute une commande shell dans le conteneur.

    workdir : sous-répertoire (relatif à /work) où se placer avant l'exécution."""
    if workdir and workdir not in (".", ""):
        command = f"cd {shlex.quote(workdir)} && {command}"
    return _execute(["bash", "-lc", command], stdin_data="", timeout=timeout)

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
    # Le PROJET ACTIF (get_workspace_dir) — pas l'ancienne var globale — pour que la
    # sandbox monte/exécute dans le bon dossier ; le montage `-v ws:/work` étant en
    # écriture, les fichiers produits par le code persistent dans le projet sur l'hôte.
    try:
        from core.state import get_workspace_dir
        ws = os.path.abspath(get_workspace_dir())
    except Exception:
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

    workdir : sous-répertoire (relatif à /work) où se placer avant l'exécution.

    Si un CONTENEUR DEV PERSISTANT est actif pour le contexte courant (console codeur),
    on y délègue : git/pip/npm + état persistent entre commandes. Sinon, conteneur jetable."""
    try:
        from tools import dev_container
        _dc_key = dev_container.active_key()
        if _dc_key and dev_container.enabled():
            # Le conteneur dev tolère des commandes plus longues (installs/tests).
            return dev_container.exec_bash(_dc_key, command, timeout=max(timeout, 120), workdir=workdir)
    except Exception:
        pass
    if workdir and workdir not in (".", ""):
        command = f"cd {shlex.quote(workdir)} && {command}"
    return _execute(["bash", "-lc", command], stdin_data="", timeout=timeout)


def run_python_in_dir(code: str, host_dir: str, image: Optional[str] = None,
                      timeout: int = 30, allow_network: bool = False) -> Tuple[str, str, int]:
    """Exécute du code Python dans un conteneur Docker en montant `host_dir` sur /work
    (cwd=/work). Les fichiers PRODUITS par le code (pptx, images, html…) PERSISTENT dans
    host_dir sur l'hôte → on peut les récupérer après coup. Mêmes garde-fous que le reste
    de la sandbox : réseau coupé (sauf allow_network/SANDBOX_ALLOW_NETWORK), --cap-drop ALL,
    racine en lecture seule (hors /work + /tmp tmpfs), limites mem/cpu/pids, UID hôte.

    `image` : image Docker à utiliser (défaut SANDBOX_DOCKER_IMAGE) — passer une image
    contenant les libs nécessaires (ex. python-pptx, matplotlib) pour le code généré.
    Le script est écrit dans host_dir/run.py pour que les chemins relatifs et os.listdir('.')
    du code se comportent comme attendu. Renvoie (stdout, stderr, returncode)."""
    host_dir = os.path.abspath(host_dir)
    os.makedirs(host_dir, exist_ok=True)
    with open(os.path.join(host_dir, "run.py"), "w", encoding="utf-8") as f:
        f.write(code)
    name = f"athena-sbx-{uuid.uuid4().hex[:12]}"
    img = image or os.getenv("SANDBOX_DOCKER_IMAGE", DEFAULT_IMAGE)
    network = "bridge" if (allow_network or os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower()
                           in ("true", "1", "yes")) else "none"
    mem = os.getenv("SANDBOX_DESIGN_MEM_LIMIT", "512m")
    args = [
        "docker", "run", "--rm", "-i",
        "--name", name,
        "--network", network,
        "--memory", mem, "--memory-swap", mem,
        "--cpus", os.getenv("SANDBOX_CPUS", "1.0"),
        "--pids-limit", os.getenv("SANDBOX_PIDS_LIMIT", "128"),
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,size=128m",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        # HOME/MPLCONFIGDIR dans le tmpfs : matplotlib/pptx écrivent leur cache sans heurter
        # la racine en lecture seule.
        "-e", "HOME=/tmp", "-e", "MPLCONFIGDIR=/tmp", "-e", "XDG_CACHE_HOME=/tmp",
        "-v", f"{host_dir}:/work",
        "-w", "/work",
    ]
    if hasattr(os, "getuid"):
        args += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd = args + [img, "python", "run.py"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        return "", f"Erreur : délai d'exécution dépassé (Timeout de {timeout} secondes).", 124
    except Exception as e:
        return "", f"Erreur sandbox Docker : {e}", 1

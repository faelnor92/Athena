"""Conteneur de développement PERSISTANT par projet (inspiré d'OpenClaw).

Contrairement à `sandbox_runner` (conteneur JETABLE par commande, réseau coupé,
rootfs read-only — bien pour exécuter du code non fiable), ce module maintient UN
conteneur Docker long-vivant par (utilisateur, projet). Les installs (`pip`, `npm`),
`git`, les fichiers temporaires et l'état persistent ENTRE les commandes — comme un
vrai terminal de dev. Réservé à la console codeur (admin-only, pilotée par l'humain).

Modèle d'isolation (toujours fort, mais adapté au dev) :
  - conteneur détaché, gardé en vie (`sleep infinity`)
  - `--cap-drop ALL` + `--security-opt no-new-privileges` (aucune capacité Linux)
  - limites mémoire / CPU / PID (généreuses mais bornées)
  - réseau ACTIVÉ par défaut (installs) — désactivable
  - le projet actif est monté en écriture sur /work ; le reste de l'hôte est invisible
  - les commandes tournent sous l'UID HÔTE → les fichiers créés restent éditables
    depuis l'IDE (pas de fichiers root:root). Un provisioning unique (en root DANS le
    conteneur) installe `git` si l'image ne l'a pas.

Pilotage par variables d'environnement :
  DEV_CONTAINER_MODE     "auto" (défaut : si docker dispo) | "on" | "off"
  SANDBOX_DEV_IMAGE      image de base (défaut: python:3.13-slim ; mettez une image
                         contenant déjà git+node+toolchains pour aller plus vite)
  DEV_CONTAINER_NETWORK  "bridge" (défaut) | "none"
  DEV_CONTAINER_MEM      ex: "2g"   (défaut)
  DEV_CONTAINER_CPUS     ex: "2.0"  (défaut)
  DEV_CONTAINER_PIDS     ex: "512"  (défaut)
  DEV_CONTAINER_IDLE     secondes d'inactivité avant nettoyage par reap_idle (défaut 3600)
  DEV_CONTAINER_PROVISION_GIT  "true" (défaut) : installe git si absent au 1er démarrage
"""
import contextvars
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple

DEFAULT_IMAGE = "python:3.13-slim"
_DERIVED_TAG = "athena-dev-base:auto"  # image dérivée (base + git) construite à la volée
_NAME_PREFIX = "athena-dev-"
_HOME = "/work/.athena-home"  # HOME dans le conteneur, sous le projet monté (host-owned)
_image_build_lock = threading.Lock()

# Un verrou par clé de conteneur : évite deux créations concurrentes du même conteneur.
_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
# Dernière utilisation (monotonic) par nom de conteneur, pour le GC d'inactivité.
_last_use: Dict[str, float] = {}

# Conteneur dev ACTIF pour le contexte d'exécution courant (ContextVar : se propage aux
# threads via to_thread). Quand il est positionné (par la console codeur), les outils bash
# des agents (run_checks/execute_bash_command via sandbox_runner) s'exécutent DANS ce
# conteneur persistant au lieu de la sandbox jetable. None ailleurs (chat/voix).
_active_key: contextvars.ContextVar = contextvars.ContextVar("dev_container_active", default=None)


def activate(key: str):
    """Active le conteneur dev `key` pour le contexte courant. Renvoie un token (reset)."""
    return _active_key.set(key or None)


def deactivate(token) -> None:
    try:
        _active_key.reset(token)
    except Exception:
        pass


def active_key() -> Optional[str]:
    return _active_key.get()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = threading.Lock()
            _locks[key] = lk
        return lk


def mode() -> str:
    return os.getenv("DEV_CONTAINER_MODE", "auto").strip().lower()


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def enabled() -> bool:
    """Le conteneur dev persistant doit-il être utilisé ?"""
    m = mode()
    if m == "off":
        return False
    if m == "on":
        return True
    return docker_available()  # "auto"


def _image_exists(tag: str) -> bool:
    try:
        r = subprocess.run(["docker", "image", "inspect", tag], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _ensure_derived_image() -> Tuple[str, Optional[str]]:
    """Construit (une fois) une image dérivée de la base + git, car `--cap-drop ALL`
    empêche d'installer quoi que ce soit au runtime (apt a besoin de capacités). Le
    `docker build`, lui, s'exécute avec les privilèges du démon. Renvoie (tag, erreur).
    Paquets supplémentaires possibles via DEV_CONTAINER_APT (ex: "nodejs npm build-essential")."""
    with _image_build_lock:
        if _image_exists(_DERIVED_TAG):
            return _DERIVED_TAG, None
        extra = (os.getenv("DEV_CONTAINER_APT", "") or "").strip()
        pkgs = "git ca-certificates" + (f" {extra}" if extra else "")
        dockerfile = (
            f"FROM {DEFAULT_IMAGE}\n"
            f"RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends "
            f"{pkgs} && rm -rf /var/lib/apt/lists/*\n"
        )
        try:
            r = subprocess.run(
                ["docker", "build", "-q", "-t", _DERIVED_TAG, "-"],
                input=dockerfile, capture_output=True, text=True, timeout=600,
            )
            if r.returncode != 0:
                return DEFAULT_IMAGE, f"Build image dev échoué : {r.stderr.strip()[-400:]}"
            return _DERIVED_TAG, None
        except Exception as e:
            return DEFAULT_IMAGE, f"Build image dev impossible : {e}"


def _effective_image() -> Tuple[str, Optional[str]]:
    """Image à utiliser pour le conteneur dev (+ erreur éventuelle non bloquante).
    Si l'utilisateur fixe SANDBOX_DEV_IMAGE, on la respecte telle quelle (elle doit
    contenir git+toolchains). Sinon on dérive automatiquement la base + git."""
    user_img = os.getenv("SANDBOX_DEV_IMAGE", "").strip()
    if user_img:
        return user_img, None
    return _ensure_derived_image()


def sanitize_key(user: str, project: Optional[str]) -> str:
    """Clé stable et sûre pour nommer le conteneur : <user>-<project|global>."""
    raw = f"{user or 'local'}-{project or 'global'}"
    key = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-").lower()
    return key[:48] or "local-global"


def container_name(key: str) -> str:
    return f"{_NAME_PREFIX}{key}"


def _workspace_dir() -> str:
    try:
        from core.state import get_workspace_dir
        ws = os.path.abspath(get_workspace_dir())
    except Exception:
        ws = os.path.abspath(os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd()))
    os.makedirs(ws, exist_ok=True)
    return ws


def _is_running(name: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def pause(key: str) -> bool:
    """Gèle le conteneur dev `key` (docker pause) — fige mémoire/processus/fichiers temp.
    Best-effort : renvoie True si la pause a réussi. Utilisé par la pile de contextes."""
    if not key or not docker_available():
        return False
    name = container_name(key)
    if not _is_running(name):
        return False
    try:
        r = subprocess.run(["docker", "pause", name], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def unpause(key: str) -> bool:
    """Relance un conteneur dev `key` mis en pause (docker unpause). Best-effort."""
    if not key or not docker_available():
        return False
    name = container_name(key)
    try:
        r = subprocess.run(["docker", "unpause", name], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _run_args(name: str, image: str) -> List[str]:
    ws = _workspace_dir()
    network = os.getenv("DEV_CONTAINER_NETWORK", "bridge").strip() or "bridge"
    mem = os.getenv("DEV_CONTAINER_MEM", "2g")
    args = [
        "docker", "run", "-d", "--name", name,
        "--network", network,
        "--memory", mem, "--memory-swap", mem,
        "--cpus", os.getenv("DEV_CONTAINER_CPUS", "2.0"),
        "--pids-limit", os.getenv("DEV_CONTAINER_PIDS", "512"),
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "-v", f"{ws}:/work",
        "-w", "/work",
        "--entrypoint", "sleep",
    ]
    return args + [image, "infinity"]


def _exec_uid_args() -> List[str]:
    """Exécuter les commandes sous l'UID/GID hôte (fichiers host-owned). POSIX seul."""
    if hasattr(os, "getuid"):
        return ["-u", f"{os.getuid()}:{os.getgid()}"]
    return []


def ensure(key: str) -> Tuple[Optional[str], Optional[str]]:
    """Garantit qu'un conteneur dev tourne pour `key`. Renvoie (nom, erreur)."""
    if not docker_available():
        return None, "Docker indisponible : conteneur dev impossible."
    name = container_name(key)
    with _lock_for(key):
        if _is_running(name):
            _last_use[name] = time.monotonic()
            return name, None
        # Image effective : dérivée (base + git) construite au build, car `--cap-drop ALL`
        # interdit toute install au runtime. En cas d'échec de build (offline…), on retombe
        # sur la base : git pourra manquer, l'erreur sera explicite à l'usage.
        image, img_err = _effective_image()
        # Un conteneur du même nom mais arrêté (crash, reboot) : on le retire d'abord.
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
        r = subprocess.run(_run_args(name, image), capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None, f"Échec création du conteneur dev : {r.stderr.strip() or r.stdout.strip()}"
        _last_use[name] = time.monotonic()
        return name, None


def exec_bash(key: str, command: str, timeout: int = 120,
              workdir: Optional[str] = None) -> Tuple[str, str, int]:
    """Exécute une commande dans le conteneur dev persistant de `key`.

    workdir : sous-répertoire relatif à /work. HOME pointe vers un dossier du projet
    (host-owned) pour que pip --user / caches npm persistent et restent éditables."""
    name, err = ensure(key)
    if err:
        return "", err, 1
    _last_use[name] = time.monotonic()
    sub = workdir if (workdir and workdir not in (".", "")) else "."
    # Wrapper : HOME persistant dans le projet, PATH user-local, cd dans le sous-dossier.
    wrapped = (
        f"export HOME={shlex.quote(_HOME)}; "
        f"export PATH=\"$HOME/.local/bin:$PATH\"; "
        f"mkdir -p \"$HOME\" 2>/dev/null; "
        f"cd {shlex.quote(sub)} 2>/dev/null || true; "
        f"{command}"
    )
    cmd = ["docker", "exec"] + _exec_uid_args() + [name, "bash", "-lc", wrapped]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", f"Erreur : délai d'exécution dépassé (Timeout de {timeout} secondes).", 124
    except Exception as e:
        return "", f"Erreur conteneur dev : {e}", 1


def stop(key: str) -> bool:
    """Arrête et supprime le conteneur dev de `key`."""
    name = container_name(key)
    try:
        r = subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        _last_use.pop(name, None)
        return r.returncode == 0
    except Exception:
        return False


def list_containers() -> List[str]:
    """Noms des conteneurs dev Athena actuellement présents."""
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={_NAME_PREFIX}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15,
        )
        return [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def reap_idle(max_idle_s: Optional[float] = None) -> List[str]:
    """Arrête les conteneurs dev inactifs depuis plus de `max_idle_s`. Renvoie les noms tués.
    Ne connaît l'inactivité que des conteneurs vus dans CE process (via _last_use)."""
    if max_idle_s is None:
        try:
            max_idle_s = float(os.getenv("DEV_CONTAINER_IDLE", "3600") or 3600)
        except ValueError:
            max_idle_s = 3600.0
    now = time.monotonic()
    killed = []
    for name, ts in list(_last_use.items()):
        if now - ts > max_idle_s:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
                _last_use.pop(name, None)
                killed.append(name)
            except Exception:
                pass
    return killed

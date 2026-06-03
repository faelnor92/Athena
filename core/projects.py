"""Projets de code PAR UTILISATEUR.

Un projet = un dossier de travail nommé (codebase/repo) sous workspace/projects/<user>/.
Le projet ACTIF (mémorisé dans user_config) pilote get_workspace_dir() → tous les outils
codeur (read/edit/run_checks/git_*) et l'explorateur de fichiers s'y scopent
automatiquement. Sans projet sélectionné : workspace de base (rétro-compatible).
"""
import os
import re
import time
import uuid

from core import user_config


def _base_workspace() -> str:
    return os.path.abspath(os.environ.get(
        "ACTIVE_WORKSPACE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")))


def projects_root() -> str:
    """Racine des projets de l'utilisateur courant."""
    return os.path.join(_base_workspace(), "projects", user_config.user_slug())


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", (name or "").strip()).strip("-")[:60] or "projet"


def list_projects() -> list:
    return user_config.get("projects", []) or []


def get_active():
    pid = user_config.get("active_project")
    if not pid:
        return None
    return next((p for p in list_projects() if p.get("id") == pid), None)


def active_path():
    p = get_active()
    path = p.get("path") if p else None
    # Sécurité : le projet doit rester sous la racine projets de l'utilisateur.
    if path:
        real = os.path.realpath(path)
        if os.path.commonpath([real, os.path.realpath(projects_root())]) == os.path.realpath(projects_root()):
            return real
    return None


def create_project(name: str):
    name = (name or "").strip()
    if not name:
        return None
    pid = uuid.uuid4().hex[:8]
    root = projects_root()
    os.makedirs(root, exist_ok=True)
    path = os.path.abspath(os.path.join(root, f"{_slug(name)}-{pid}"))
    os.makedirs(path, exist_ok=True)
    projs = list_projects()
    proj = {"id": pid, "name": name, "path": path, "created_at": time.time()}
    projs.append(proj)
    user_config.set_many({"projects": projs, "active_project": pid})
    return proj


def select(pid: str) -> bool:
    if any(p.get("id") == pid for p in list_projects()):
        user_config.set("active_project", pid)
        return True
    return False


def delete(pid: str, remove_files: bool = False) -> bool:
    projs = list_projects()
    proj = next((p for p in projs if p.get("id") == pid), None)
    if not proj:
        return False
    projs = [p for p in projs if p.get("id") != pid]
    updates = {"projects": projs}
    if user_config.get("active_project") == pid:
        updates["active_project"] = (projs[0]["id"] if projs else "")
    user_config.set_many(updates)
    if remove_files:
        import shutil
        # Confiné à la racine projets de l'utilisateur (anti-traversée).
        real = os.path.realpath(proj.get("path", ""))
        root = os.path.realpath(projects_root())
        if real and os.path.commonpath([real, root]) == root:
            shutil.rmtree(real, ignore_errors=True)
    return True

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

import contextvars

from core import user_config
from core import shared_projects

# Override de projet PAR CONTEXTE D'EXÉCUTION (ContextVar) : permet à la console codeur
# de cibler un projet précis pour SON run, sans modifier le projet global de l'utilisateur
# (donc le chat et le vocal continuent sur le leur). Se propage aux threads via to_thread.
_project_override = contextvars.ContextVar("project_override", default=None)


def set_override(pid):
    """Force le projet actif pour le contexte courant. Renvoie un token à passer à reset_override."""
    return _project_override.set(pid or None)


def reset_override(token):
    try:
        _project_override.reset(token)
    except Exception:
        pass


def _effective_pid():
    """Projet actif effectif : override de contexte s'il existe, sinon celui de l'utilisateur."""
    return _project_override.get() or user_config.get("active_project")


def _base_workspace() -> str:
    return os.path.abspath(os.environ.get(
        "ACTIVE_WORKSPACE_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")))


def _projects_base() -> str:
    """Racine GLOBALE des projets (tous utilisateurs). HORS du workspace de base par défaut
    (sinon les projets fuient dans l'explorateur du workspace général). Configurable via
    PROJECTS_DIR."""
    env = os.getenv("PROJECTS_DIR", "").strip()
    if env:
        return os.path.abspath(env)
    return os.path.join(os.path.dirname(_base_workspace()), "athena_projects")


def _legacy_projects_base() -> str:
    """Ancienne racine (sous le workspace de base) — acceptée pour ne pas casser les
    projets déjà créés avant le déplacement."""
    return os.path.join(_base_workspace(), "projects")


def projects_root() -> str:
    """Racine des projets de l'utilisateur courant (nouveaux projets)."""
    return os.path.join(_projects_base(), user_config.user_slug())


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", (name or "").strip()).strip("-")[:60] or "projet"


def _own_projects() -> list:
    return user_config.get("projects", []) or []


def list_projects() -> list:
    """Projets de l'utilisateur courant : les SIENS (role 'owner') + ceux PARTAGÉS avec lui."""
    own = [{**p, "role": "owner", "shared": False} for p in _own_projects()]
    user = user_config.current_user_key()
    return own + shared_projects.projects_for(user)


def get_active():
    pid = user_config.get("active_project")
    if not pid:
        return None
    return next((p for p in list_projects() if p.get("id") == pid), None)


def active_path():
    pid = _effective_pid()
    if not pid:
        return None
    user = user_config.current_user_key()
    path = None
    own = next((p for p in _own_projects() if p.get("id") == pid), None)
    if own:
        path = own.get("path")
    else:
        # Projet PARTAGÉ : autorisé si l'utilisateur en est membre (ou propriétaire).
        if shared_projects.role_for(pid, user):
            e = shared_projects.get(pid)
            path = e.get("path") if e else None
    # Anti-traversée : le projet doit rester sous une racine de projets autorisée
    # (nouvelle racine OU racine héritée, pour ne pas casser l'existant).
    if path:
        real = os.path.realpath(path)
        for base in (os.path.realpath(_projects_base()), os.path.realpath(_legacy_projects_base())):
            try:
                if os.path.commonpath([real, base]) == base:
                    return real
            except ValueError:
                continue
    return None


def current_role():
    """Rôle de l'utilisateur sur le projet ACTIF : None (workspace de base) | owner | editor | viewer."""
    pid = _effective_pid()
    if not pid:
        return None
    if any(p.get("id") == pid for p in _own_projects()):
        return "owner"
    return shared_projects.role_for(pid, user_config.current_user_key())


def can_write() -> bool:
    """Droit d'écriture sur le projet actif (base/own/editor = oui ; viewer = non)."""
    return current_role() in (None, "owner", "editor")


def create_project(name: str):
    name = (name or "").strip()
    if not name:
        return None
    pid = uuid.uuid4().hex[:8]
    root = projects_root()
    os.makedirs(root, exist_ok=True)
    path = os.path.abspath(os.path.join(root, f"{_slug(name)}-{pid}"))
    os.makedirs(path, exist_ok=True)
    projs = _own_projects()
    proj = {"id": pid, "name": name, "path": path, "created_at": time.time()}
    projs.append(proj)
    user_config.set_many({"projects": projs, "active_project": pid})
    return proj


def select(pid: str) -> bool:
    # Autorise un projet propre OU partagé (membre).
    if any(p.get("id") == pid for p in list_projects()):
        user_config.set("active_project", pid)
        return True
    return False


def delete(pid: str, remove_files: bool = False) -> bool:
    # On ne supprime QUE ses propres projets (un projet partagé se quitte, pas se supprime).
    projs = _own_projects()
    proj = next((p for p in projs if p.get("id") == pid), None)
    if not proj:
        return False
    shared_projects.remove_project(pid)  # retire tout partage associé
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

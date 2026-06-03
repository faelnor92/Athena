"""Gestion de projets de code PAR UTILISATEUR (chacun les siens — pas admin).
Le projet actif scope automatiquement les outils codeur et l'explorateur de fichiers.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import projects

router = APIRouter(tags=["Projects"])


@router.get("/api/projects")
async def list_projects():
    return {"projects": projects.list_projects(),
            "active": projects.get_active(),
            "active_path": projects.active_path()}


class ProjectCreateRequest(BaseModel):
    name: str


@router.post("/api/projects")
async def create_project(req: ProjectCreateRequest):
    proj = projects.create_project(req.name)
    if not proj:
        raise HTTPException(status_code=400, detail="Nom de projet requis.")
    return {"status": "success", "project": proj}


class ProjectSelectRequest(BaseModel):
    id: str


@router.post("/api/projects/select")
async def select_project(req: ProjectSelectRequest):
    # id vide = revenir au workspace de base.
    if not req.id:
        from core import user_config
        user_config.set("active_project", "")
        return {"status": "success", "active": None}
    if not projects.select(req.id):
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    return {"status": "success", "active": projects.get_active()}


@router.delete("/api/projects/{pid}")
async def delete_project(pid: str, remove_files: bool = False):
    if not projects.delete(pid, remove_files=remove_files):
        raise HTTPException(status_code=404, detail="Projet introuvable.")
    return {"status": "success"}


# --- Partage (collaboration) : le PROPRIÉTAIRE gère les membres ------------
def _own_project_or_404(pid: str):
    from core import user_config
    proj = next((p for p in (user_config.get("projects", []) or []) if p.get("id") == pid), None)
    if not proj:
        raise HTTPException(status_code=404, detail="Projet introuvable (ou non possédé).")
    return proj


class ShareRequest(BaseModel):
    username: str
    role: str = "viewer"


@router.get("/api/projects/{pid}/members")
async def project_members(pid: str):
    _own_project_or_404(pid)
    from core import shared_projects
    return {"members": shared_projects.members(pid)}


@router.post("/api/projects/{pid}/share")
async def share_project(pid: str, req: ShareRequest):
    from core import user_config, shared_projects
    from core.users import user_store
    proj = _own_project_or_404(pid)
    member = (req.username or "").strip()
    # Le membre doit être un compte existant et différent du propriétaire.
    if not any(u["username"] == member for u in user_store.list()):
        raise HTTPException(status_code=404, detail="Utilisateur destinataire inconnu.")
    owner = user_config.current_user_key()
    if not shared_projects.share(pid, owner, proj["name"], proj["path"], member, req.role):
        raise HTTPException(status_code=400, detail="Partage impossible (membre invalide ?).")
    return {"status": "success", "members": shared_projects.members(pid)}


@router.delete("/api/projects/{pid}/share/{username}")
async def unshare_project(pid: str, username: str):
    _own_project_or_404(pid)
    from core import shared_projects
    shared_projects.unshare(pid, username)
    return {"status": "success", "members": shared_projects.members(pid)}

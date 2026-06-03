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

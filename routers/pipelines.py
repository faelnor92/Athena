"""API des Workflows / Pipelines déterministes (mode chaîne de montage type CrewAI).

Chaque utilisateur gère SES propres pipelines (owner-scopé, comme les routines). Le
swarm organique reste le défaut ; un pipeline ne s'exécute que sur demande explicite
(ce routeur, ou une routine qui le déclenche).
"""
import asyncio
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.pipelines import pipeline_store
from tools.pipeline_tools import run_pipeline

router = APIRouter(tags=["Pipelines / Workflows"])


def _is_admin(request: Request) -> bool:
    """True si l'appelant est admin OU si l'auth n'est pas active (mode local de confiance)."""
    from core.users import user_store
    auth_active = bool(os.getenv("ADMIN_PASSWORD", "").strip()) or user_store.count() > 0
    if not auth_active:
        return True
    u = getattr(request.state, "user", None)
    return bool(u and u.get("role") == "admin")


class StepModel(BaseModel):
    agent: str
    instruction: str
    expected_output: str = ""


class PipelineRequest(BaseModel):
    id: str = None
    name: str = "Workflow"
    steps: List[StepModel] = []


class RunRequest(BaseModel):
    input: str = ""


@router.get("/api/pipelines")
async def list_pipelines() -> Dict[str, Any]:
    return {"pipelines": pipeline_store.list()}


@router.post("/api/pipelines")
async def save_pipeline(req: PipelineRequest, request: Request) -> Dict[str, Any]:
    # Validation admin : un admin (ou le mode local) valide d'emblée ; sinon le pipeline
    # est créé « en attente » et devra être validé par un admin avant de pouvoir s'exécuter.
    try:
        p = pipeline_store.upsert(req.model_dump(), approved=_is_admin(request))
    except PermissionError:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return {"status": "success", "pipeline": p}


@router.delete("/api/pipelines/{pid}")
async def delete_pipeline(pid: str) -> Dict[str, str]:
    if not pipeline_store.delete(pid):
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return {"status": "success"}


@router.post("/api/pipelines/{pid}/run")
async def run_pipeline_now(pid: str, request: Request, req: RunRequest = None) -> Dict[str, Any]:
    p = pipeline_store.get_owned(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    if not p.get("approved") and not _is_admin(request):
        raise HTTPException(status_code=403,
                            detail="Workflow en attente de validation par un administrateur.")
    initial = (req.input if req else "") or ""
    result = await asyncio.to_thread(run_pipeline, p, initial)
    return result


# --- Validation par l'administrateur ----------------------------------------
@router.get("/api/pipelines/pending")
async def list_pending_pipelines(request: Request) -> Dict[str, Any]:
    """Pipelines de TOUS les utilisateurs en attente de validation (admin)."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
    return {"pending": pipeline_store.pending()}


@router.post("/api/pipelines/{pid}/approve")
async def approve_pipeline(pid: str, request: Request) -> Dict[str, str]:
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")
    if not pipeline_store.set_approved(pid, True):
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return {"status": "success"}

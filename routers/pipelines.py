"""API des Workflows / Pipelines déterministes (mode chaîne de montage type CrewAI).

Chaque utilisateur gère SES propres pipelines (owner-scopé, comme les routines). Le
swarm organique reste le défaut ; un pipeline ne s'exécute que sur demande explicite
(ce routeur, ou une routine qui le déclenche).
"""
import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.pipelines import pipeline_store
from tools.pipeline_tools import run_pipeline

router = APIRouter(tags=["Pipelines / Workflows"])


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
async def save_pipeline(req: PipelineRequest) -> Dict[str, Any]:
    try:
        p = pipeline_store.upsert(req.model_dump())
    except PermissionError:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return {"status": "success", "pipeline": p}


@router.delete("/api/pipelines/{pid}")
async def delete_pipeline(pid: str) -> Dict[str, str]:
    if not pipeline_store.delete(pid):
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    return {"status": "success"}


@router.post("/api/pipelines/{pid}/run")
async def run_pipeline_now(pid: str, req: RunRequest = None) -> Dict[str, Any]:
    p = pipeline_store.get_owned(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Pipeline introuvable.")
    initial = (req.input if req else "") or ""
    result = await asyncio.to_thread(run_pipeline, p, initial)
    return result

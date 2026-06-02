"""Routeur : plan d'action persistant & éditable (/api/plan). Autonome — core.plan_store."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class PlanSetRequest(BaseModel):
    client_id: str = "web"
    items: List[Any] = []  # str ou {text, status} — normalisé par plan_store.set_plan


class PlanStepRequest(BaseModel):
    client_id: str = "web"
    op: str                      # set_status | add | edit | delete
    index: int = -1
    text: str = ""
    status: str = "done"


@router.get("/api/plan")
async def api_get_plan(client_id: str = "web"):
    from core import plan_store
    return {"items": plan_store.get_plan(client_id)}


@router.post("/api/plan")
async def api_set_plan(req: PlanSetRequest):
    from core import plan_store
    items = plan_store.set_plan(req.client_id, req.items)
    return {"status": "success", "items": items}


@router.post("/api/plan/step")
async def api_plan_step(req: PlanStepRequest):
    from core import plan_store
    op = (req.op or "").strip().lower()
    ok = False
    if op == "set_status":
        ok = plan_store.update_step(req.client_id, req.index, req.status)
    elif op == "add":
        ok = plan_store.add_step(req.client_id, req.text)
    elif op == "edit":
        ok = plan_store.edit_step(req.client_id, req.index, req.text)
    elif op == "delete":
        ok = plan_store.remove_step(req.client_id, req.index)
    else:
        raise HTTPException(status_code=400, detail="op invalide (set_status|add|edit|delete).")
    if not ok:
        raise HTTPException(status_code=400, detail="Opération refusée (index hors limites ou texte vide).")
    return {"status": "success", "items": plan_store.get_plan(req.client_id)}

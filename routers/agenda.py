"""Routeur : agenda / rendez-vous (/api/agenda). Autonome — tools.agenda_tools."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class AgendaEventRequest(BaseModel):
    title: str
    datetime_str: str
    duration_minutes: int = 60
    description: str = ""


@router.get("/api/agenda")
async def get_agenda_api():
    # Agenda de l'utilisateur courant (résolu dans load_agenda via user_config).
    from tools.agenda_tools import load_agenda
    return load_agenda()


@router.post("/api/agenda")
async def add_agenda_api(req: AgendaEventRequest):
    from tools.agenda_tools import add_calendar_event
    res = add_calendar_event(
        title=req.title,
        datetime_str=req.datetime_str,
        duration_minutes=req.duration_minutes,
        description=req.description,
    )
    if "Erreur" in res:
        raise HTTPException(status_code=400, detail=res)
    return {"message": res}


@router.delete("/api/agenda/{event_id}")
async def delete_agenda_api(event_id: str):
    from tools.agenda_tools import delete_calendar_event
    res = delete_calendar_event(event_id)
    if "Erreur" in res:
        raise HTTPException(status_code=404, detail=res)
    return {"message": res}

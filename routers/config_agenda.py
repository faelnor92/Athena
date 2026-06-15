import os
import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from core import user_config

router = APIRouter(tags=["Config Agenda"])


class SaveAgendaConfigRequest(BaseModel):
    external_ical_url: str = ""
    google_calendar_id: str = ""
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""
    write_target: str = "auto"   # où créer les événements : auto | local | google | caldav


@router.get("/api/config/agenda")
async def get_config_agenda() -> Dict[str, Any]:
    """Config agenda de l'UTILISATEUR COURANT (chacun branche son propre calendrier)."""
    try:
        from tools.agenda_tools import google_creds_path
        caldav_pwd = user_config.get("CALDAV_PASSWORD", "") or ""
        masked = ""
        if caldav_pwd:
            masked = f"{caldav_pwd[:2]}...{caldav_pwd[-2:]}" if len(caldav_pwd) > 4 else "***"
        return {
            "external_ical_url": user_config.get("EXTERNAL_ICAL_URL", "") or "",
            "google_calendar_id": user_config.get("GOOGLE_CALENDAR_ID", "") or "",
            "caldav_url": user_config.get("CALDAV_URL", "") or "",
            "caldav_username": user_config.get("CALDAV_USERNAME", "") or "",
            "caldav_password": masked,
            "write_target": user_config.get("AGENDA_WRITE_TARGET", "auto") or "auto",
            "has_google_credentials": os.path.exists(google_creds_path()),
        }
    except Exception as e:
        import logging
        logging.exception("Erreur récupération config agenda")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/config/agenda")
async def save_config_agenda(req: SaveAgendaConfigRequest) -> Dict[str, str]:
    """Enregistre la config agenda de l'utilisateur courant (store par-utilisateur, pas .env)."""
    try:
        _wt = (req.write_target or "auto").strip().lower()
        if _wt not in ("auto", "local", "google", "caldav"):
            _wt = "auto"
        updates = {
            "EXTERNAL_ICAL_URL": req.external_ical_url,
            "GOOGLE_CALENDAR_ID": req.google_calendar_id,
            "CALDAV_URL": req.caldav_url,
            "CALDAV_USERNAME": req.caldav_username,
            "AGENDA_WRITE_TARGET": _wt,
        }
        # Ne pas écraser le mot de passe s'il est masqué (non modifié dans l'UI).
        if req.caldav_password and "..." not in req.caldav_password and req.caldav_password != "***":
            updates["CALDAV_PASSWORD"] = req.caldav_password
        user_config.set_many(updates)

        try:
            from tools.agenda_tools import sync_all_external_calendars
            sync_all_external_calendars()
        except Exception as e:
            import logging
            logging.warning(f"Impossible de synchroniser les calendriers après sauvegarde : {e}")

        return {"status": "success", "message": "Agenda personnel mis à jour et synchronisé !"}
    except Exception as e:
        import logging
        logging.exception("Erreur sauvegarde config agenda")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/config/agenda/google-key")
async def upload_google_key(file: UploadFile = File(...)) -> Dict[str, str]:
    """Téléverse la clé de service Google de l'utilisateur courant (fichier par-utilisateur)."""
    try:
        from tools.agenda_tools import google_creds_path, sync_all_external_calendars
        os.makedirs("workspace", exist_ok=True)
        content = await file.read()
        json_data = json.loads(content)
        if "client_email" not in json_data or "private_key" not in json_data:
            raise HTTPException(status_code=400, detail="Fichier JSON Google non valide (client_email/private_key manquants).")
        with open(google_creds_path(), "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)
        try:
            sync_all_external_calendars()
        except Exception as e:
            import logging
            logging.warning(f"Impossible de synchroniser après upload : {e}")
        return {"status": "success", "message": "Clé Google téléversée pour votre compte !"}
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Le fichier téléversé n'est pas un JSON valide.")
    except Exception as e:
        import logging
        logging.exception("Erreur upload clé google")
        raise HTTPException(status_code=500, detail=f"Erreur interne : {str(e)}")


@router.post("/api/agenda/sync")
async def force_agenda_sync() -> Dict[str, str]:
    try:
        from tools.agenda_tools import sync_all_external_calendars
        imported = sync_all_external_calendars()
        return {"status": "success", "message": f"Synchronisation forcée réussie. {imported} événements externes importés."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

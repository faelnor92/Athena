import os
import json
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from routers.config_system import parse_env

router = APIRouter(tags=["Config Agenda"])

class SaveAgendaConfigRequest(BaseModel):
    external_ical_url: str = ""
    google_calendar_id: str = ""
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""

@router.get("/api/config/agenda")
async def get_config_agenda() -> Dict[str, Any]:
    try:
        env = parse_env()
        has_google_credentials = os.path.exists("workspace/google_credentials.json")
        
        caldav_pwd = env.get("CALDAV_PASSWORD", "")
        masked_caldav_pwd = ""
        if caldav_pwd:
            masked_caldav_pwd = f"{caldav_pwd[:2]}...{caldav_pwd[-2:]}" if len(caldav_pwd) > 4 else "***"
            
        return {
            "external_ical_url": env.get("EXTERNAL_ICAL_URL", ""),
            "google_calendar_id": env.get("GOOGLE_CALENDAR_ID", ""),
            "caldav_url": env.get("CALDAV_URL", ""),
            "caldav_username": env.get("CALDAV_USERNAME", ""),
            "caldav_password": masked_caldav_pwd,
            "has_google_credentials": has_google_credentials
        }
    except Exception as e:
        import logging
        logging.exception("Erreur récupération config agenda")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/config/agenda")
async def save_config_agenda(req: SaveAgendaConfigRequest) -> Dict[str, str]:
    try:
        current_env = parse_env()
        
        current_env["EXTERNAL_ICAL_URL"] = req.external_ical_url
        current_env["GOOGLE_CALENDAR_ID"] = req.google_calendar_id
        current_env["CALDAV_URL"] = req.caldav_url
        current_env["CALDAV_USERNAME"] = req.caldav_username
        
        if req.caldav_password and "..." not in req.caldav_password and req.caldav_password != "***":
            current_env["CALDAV_PASSWORD"] = req.caldav_password
            
        with open(".env", "w", encoding="utf-8") as f:
            f.write("# Configuration de l'essaim Jarvis v2 (Générée via Dashboard)\n")
            for k, v in current_env.items():
                f.write(f'{k}="{v}"\n')
                os.environ[k] = v
                
        try:
            from tools.agenda_tools import sync_all_external_calendars
            sync_all_external_calendars()
        except Exception as e:
            import logging
            logging.warning(f"Impossible de synchroniser les calendriers après sauvegarde : {e}")
            
        return {"status": "success", "message": "Paramètres d'agenda et synchronisation à chaud mis à jour avec succès !"}
    except Exception as e:
        import logging
        logging.exception("Erreur sauvegarde config agenda")
        raise HTTPException(status_code=500, detail=f"Erreur d'écriture dans le .env : {str(e)}")

@router.post("/api/config/agenda/google-key")
async def upload_google_key(file: UploadFile = File(...)) -> Dict[str, str]:
    try:
        os.makedirs("workspace", exist_ok=True)
        content = await file.read()
        
        json_data = json.loads(content)
        if "client_email" not in json_data or "private_key" not in json_data:
            raise HTTPException(status_code=400, detail="Fichier JSON Google non valide. Propriétés client_email ou private_key manquantes.")
            
        with open("workspace/google_credentials.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)
            
        try:
            from tools.agenda_tools import sync_all_external_calendars
            sync_all_external_calendars()
        except Exception as e:
            import logging
            logging.warning(f"Impossible de synchroniser les calendriers après upload : {e}")
            
        return {"status": "success", "message": "Fichier de clé Google Cloud credentials.json téléversé avec succès !"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Le fichier téléversé n'est pas un fichier JSON valide.")
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

"""Routeur : sauvegarde/restauration (/api/backup), infos plateforme (/api/platform),
pairing Telegram (/api/telegram/pairing). Groupes autonomes (core.*).
"""
import asyncio
import os

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()


# --- Sauvegarde / restauration --------------------------------------------
@router.get("/api/backup")
async def backup_download():
    """Télécharge une archive ZIP de tout l'état (conversations, mémoire, runs…)."""
    import datetime
    from core.backup import make_backup
    data = await asyncio.to_thread(make_backup)
    fname = f"athena-backup-{datetime.date.today().isoformat()}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/api/backup/restore")
async def backup_restore(file: UploadFile = File(...)):
    """Restaure l'état depuis une archive ZIP (écrase l'état actuel)."""
    from core.backup import restore_backup
    data = await file.read()
    try:
        res = await asyncio.to_thread(restore_backup, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restauration impossible : {e}")
    return {"status": "success", **res, "note": "Redémarre le serveur pour recharger entièrement la mémoire."}


# --- Plateforme -------------------------------------------------------------
@router.get("/api/platform")
async def get_platform():
    """Détection automatique de l'OS hôte et de l'environnement d'exécution."""
    from core.platform_info import get_platform_info, sandbox_active, get_version
    info = get_platform_info()
    info["sandbox_active"] = sandbox_active()
    info["app_name"] = os.getenv("APP_NAME", "Athena").strip() or "Athena"
    return info

@router.get("/api/system/version")
async def get_system_version():
    """Retourne la version actuelle du framework."""
    from core.platform_info import get_version
    return {"version": get_version()}

@router.get("/api/system/update_check")
async def check_system_update():
    """Vérifie si une nouvelle version est disponible sur GitHub.
    Échec silencieux si le dépôt est privé / hors-ligne (pas d'erreur alarmante côté UI)."""
    import urllib.request
    from core.platform_info import get_version
    current_version = get_version().strip()
    try:
        url = "https://raw.githubusercontent.com/faelnor92/Athena/main/VERSION"
        req = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=5) as response:
            latest_version = response.read().decode('utf-8').strip()
        has_update = (latest_version != current_version and latest_version != "")
        return {
            "update_available": has_update,
            "current_version": current_version,
            "latest_version": latest_version
        }
    except Exception:
        # Dépôt privé / hors-ligne : vérification impossible en anonyme → on n'alarme pas l'UI.
        return {"update_available": False, "current_version": current_version, "check_unavailable": True}

@router.post("/api/system/update_run")
async def run_system_update():
    """Lance le script de mise à jour en arrière-plan."""
    import subprocess
    import os
    from core.platform_info import get_platform_info
    info = get_platform_info()
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        if info.get("is_windows"):
            script_path = os.path.join(root_dir, "update.ps1")
            kwargs = {}
            if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP')
            subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path],
                cwd=root_dir,
                start_new_session=True,
                **kwargs
            )
        else:
            script_path = os.path.join(root_dir, "update.sh")
            subprocess.Popen(
                ["bash", script_path],
                cwd=root_dir,
                start_new_session=True,
                preexec_fn=os.setsid
            )
        return {"status": "success", "message": "Mise à jour lancée, redémarrage imminent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lancement de la maj : {str(e)}")

# --- Pairing Telegram -------------------------------------------------------
class PairingActionRequest(BaseModel):
    code: str = ""
    chat_id: str = ""


@router.get("/api/telegram/pairing")
async def telegram_pairing_status():
    """État du DM pairing Telegram (demandes en attente, contacts approuvés)."""
    from core import telegram_pairing
    return telegram_pairing.status()


@router.post("/api/telegram/pairing/approve")
async def telegram_pairing_approve(req: PairingActionRequest):
    from core import telegram_pairing
    cid = None
    if req.code:
        cid = telegram_pairing.approve_code(req.code)
    elif req.chat_id:
        telegram_pairing.approve_chat(req.chat_id); cid = req.chat_id
    return {"status": "success" if cid else "not_found", "chat_id": cid, "pairing": telegram_pairing.status()}


@router.post("/api/telegram/pairing/revoke")
async def telegram_pairing_revoke(req: PairingActionRequest):
    from core import telegram_pairing
    ok = telegram_pairing.revoke_chat(req.chat_id) if req.chat_id else False
    return {"status": "success" if ok else "not_found", "pairing": telegram_pairing.status()}

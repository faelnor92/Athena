"""Configuration de l'intégration OnlyOffice Document Server (éditeur .docx embarqué).

GET  /api/config/onlyoffice   → réglages courants (secret masqué) + état
POST /api/config/onlyoffice   → enregistre URL DS / secret JWT / base publique
"""
import os
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["Config OnlyOffice"])


class SaveOnlyOfficeRequest(BaseModel):
    url: str = ""              # base du Document Server
    jwt_secret: str = ""       # secret JWT du DS (vide = inchangé)
    public_base: str = ""      # URL d'Athena vue par le DS (optionnel)


@router.get("/api/config/onlyoffice")
async def get_onlyoffice() -> Dict[str, Any]:
    secret = (os.getenv("ONLYOFFICE_JWT_SECRET", "") or "").strip()
    return {
        "url": (os.getenv("ONLYOFFICE_URL", "") or "").strip(),
        "public_base": (os.getenv("ONLYOFFICE_PUBLIC_BASE", "") or "").strip(),
        "has_secret": bool(secret),
        "configured": bool((os.getenv("ONLYOFFICE_URL", "") or "").strip()),
    }


@router.post("/api/config/onlyoffice")
async def set_onlyoffice(req: SaveOnlyOfficeRequest) -> Dict[str, Any]:
    url = (req.url or "").strip().rstrip("/")
    public_base = (req.public_base or "").strip().rstrip("/")
    try:
        from setup_wizard import set_env_var
        set_env_var("ONLYOFFICE_URL", url)
        set_env_var("ONLYOFFICE_PUBLIC_BASE", public_base)
        # Secret : on ne l'écrase que si une nouvelle valeur est fournie (sinon on garde).
        if (req.jwt_secret or "").strip():
            set_env_var("ONLYOFFICE_JWT_SECRET", req.jwt_secret.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Écriture .env impossible : {e}")
    os.environ["ONLYOFFICE_URL"] = url
    os.environ["ONLYOFFICE_PUBLIC_BASE"] = public_base
    if (req.jwt_secret or "").strip():
        os.environ["ONLYOFFICE_JWT_SECRET"] = req.jwt_secret.strip()
    return {"status": "success", "configured": bool(url)}

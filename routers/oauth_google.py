"""Endpoints OAuth Google (Calendar + Gmail), par-utilisateur.

- GET  /api/oauth/google/status     → état (configuré / connecté / email)        [authentifié]
- GET  /api/oauth/google/start      → URL de consentement à ouvrir               [authentifié]
- GET  /api/oauth/google/callback   → retour de Google (sans Bearer → PUBLIC)    [public]
- POST /api/oauth/google/disconnect → révoque + efface le refresh_token          [authentifié]

Le callback est PUBLIC (le navigateur revient de Google sans en-tête d'auth) : l'utilisateur
est résolu via le `state` (lié à l'utilisateur au moment du start, vérifié anti-CSRF/rejeu).
"""
import asyncio
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from core import google_oauth

router = APIRouter(tags=["OAuth Google"])


@router.get("/api/oauth/google/status")
async def google_status() -> Dict[str, Any]:
    """État de la connexion Google de l'utilisateur courant (pour l'UI)."""
    return google_oauth.status()


@router.get("/api/oauth/google/start")
async def google_start(request: Request) -> Dict[str, str]:
    """Renvoie l'URL de consentement Google (le front fait window.location = auth_url)."""
    if not google_oauth.is_configured():
        raise HTTPException(status_code=400,
                            detail="OAuth Google non configuré : renseigne GOOGLE_OAUTH_CLIENT_ID "
                                   "et GOOGLE_OAUTH_CLIENT_SECRET (Réglages → .env).")
    try:
        url = google_oauth.build_auth_url(str(request.base_url))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"auth_url": url}


@router.get("/api/oauth/google/callback", include_in_schema=False)
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Retour de Google : échange le code, persiste le refresh_token, renvoie au SPA."""
    if error:
        return RedirectResponse(f"/?google_oauth=error&detail={error}#settings", status_code=302)
    if not code or not state:
        return RedirectResponse("/?google_oauth=error&detail=missing_code#settings", status_code=302)
    try:
        res = await asyncio.to_thread(google_oauth.exchange_code, code, state)
    except Exception as e:
        # Pas de détail sensible dans l'URL ; message générique côté UI.
        import logging
        logging.warning("Échec OAuth Google : %s", e)
        return RedirectResponse("/?google_oauth=error#settings", status_code=302)
    email = res.get("email", "")
    return RedirectResponse(f"/?google_oauth=connected&email={email}#settings", status_code=302)


@router.post("/api/oauth/google/disconnect")
async def google_disconnect() -> Dict[str, str]:
    """Déconnecte le compte Google de l'utilisateur courant (révoque + efface)."""
    await asyncio.to_thread(google_oauth.disconnect)
    return {"status": "success", "message": "Compte Google déconnecté."}

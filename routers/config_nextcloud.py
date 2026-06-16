"""Configuration Nextcloud par utilisateur (Fichiers/Tâches/Contacts via WebDAV/CalDAV/CardDAV).

GET  /api/config/nextcloud        → config courante (mot de passe masqué) + état
POST /api/config/nextcloud        → enregistre URL / utilisateur / mot de passe (par-utilisateur)
GET  /api/config/nextcloud/test   → teste la connexion (PROPFIND sur la racine des fichiers)
"""
import ipaddress
import urllib.parse
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import user_config, nextcloud

router = APIRouter(tags=["Config Nextcloud"])


class SaveNextcloudRequest(BaseModel):
    url: str = ""
    username: str = ""
    password: str = ""
    lists_sync: bool = False        # synchroniser listes/tâches avec Nextcloud Notes
    lists_folder: str = "Notes"     # dossier de l'app Notes


def _allowlist_hint(url: str) -> str:
    """Avertit si l'hôte est une IP privée non autorisée par net_guard (cas homelab)."""
    try:
        host = (urllib.parse.urlparse(url).hostname or "").strip()
        ip = ipaddress.ip_address(host)
    except ValueError:
        return ""   # nom de domaine : on ne peut pas trancher ici
    except Exception:
        return ""
    if ip.is_private or ip.is_loopback:
        from tools.net_guard import _host_allowlisted
        if not _host_allowlisted(host):
            return (f" ⚠️ {host} est une IP privée bloquée par l'anti-SSRF : ajoute-la à "
                    "NET_GUARD_ALLOW_HOSTS (Réglages → .env) pour que ça fonctionne.")
    return ""


@router.get("/api/config/nextcloud")
async def get_config_nextcloud() -> Dict[str, Any]:
    pwd = user_config.get(nextcloud.K_PASSWORD, "") or ""
    masked = (f"{pwd[:2]}...{pwd[-2:]}" if len(pwd) > 4 else ("***" if pwd else ""))
    return {
        "url": user_config.get(nextcloud.K_URL, "") or "",
        "username": user_config.get(nextcloud.K_USER, "") or "",
        "password": masked,
        "configured": nextcloud.is_configured(),
        "lists_sync": str(user_config.get("LISTS_SYNC_NEXTCLOUD", "") or "").strip().lower() in ("1", "true", "yes", "on"),
        "lists_folder": user_config.get("LISTS_NEXTCLOUD_FOLDER", "") or "Notes",
    }


@router.post("/api/config/nextcloud")
async def save_config_nextcloud(req: SaveNextcloudRequest) -> Dict[str, str]:
    updates = {
        nextcloud.K_URL: (req.url or "").strip().rstrip("/"),
        nextcloud.K_USER: (req.username or "").strip(),
        "LISTS_SYNC_NEXTCLOUD": "true" if req.lists_sync else "false",
        "LISTS_NEXTCLOUD_FOLDER": (req.lists_folder or "Notes").strip().strip("/") or "Notes",
    }
    # Ne pas écraser le mot de passe s'il est masqué (non modifié).
    if req.password and "..." not in req.password and req.password != "***":
        updates[nextcloud.K_PASSWORD] = req.password
    user_config.set_many(updates)
    msg = "Configuration Nextcloud enregistrée."
    hint = _allowlist_hint(updates[nextcloud.K_URL])
    return {"status": "success", "message": msg + hint}


@router.get("/api/config/nextcloud/test")
async def test_config_nextcloud() -> Dict[str, Any]:
    if not nextcloud.is_configured():
        return {"ok": False, "detail": "Nextcloud non configuré (URL/utilisateur/mot de passe)."}
    import requests
    from tools.net_guard import is_blocked_url
    url = nextcloud.files_base()
    if is_blocked_url(url):
        return {"ok": False, "detail": _allowlist_hint(url).strip() or
                "Hôte interne bloqué (anti-SSRF) : ajoute-le à NET_GUARD_ALLOW_HOSTS."}
    try:
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                '<d:resourcetype/></d:prop></d:propfind>')
        r = requests.request("PROPFIND", url, auth=nextcloud.auth(),
                             headers={"Depth": "0", "Content-Type": "application/xml"},
                             data=body, timeout=10)
        if r.status_code in (207, 200):
            return {"ok": True, "detail": "Connexion Nextcloud réussie ✅"}
        if r.status_code == 401:
            return {"ok": False, "detail": "Identifiants refusés (401) — vérifie l'utilisateur / "
                                           "le mot de passe d'application."}
        return {"ok": False, "detail": f"Réponse inattendue ({r.status_code})."}
    except Exception as e:
        return {"ok": False, "detail": f"Connexion impossible : {e}"}

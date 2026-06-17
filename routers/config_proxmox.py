"""Configuration Proxmox VE (par-utilisateur, repli .env).

GET  /api/config/proxmox       → config courante (secret masqué)
POST /api/config/proxmox       → enregistre URL / token id / secret / verify_tls
GET  /api/config/proxmox/test  → teste la connexion (GET /version)
"""
import ipaddress
import urllib.parse
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import user_config, proxmox

router = APIRouter(tags=["Config Proxmox"])


class SaveProxmoxRequest(BaseModel):
    url: str = ""
    token_id: str = ""
    token_secret: str = ""
    verify_tls: bool = False


def _allowlist_hint(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").strip()
        ip = ipaddress.ip_address(host)
    except Exception:
        return ""
    if ip.is_private or ip.is_loopback:
        from tools.net_guard import _host_allowlisted
        if not _host_allowlisted(host):
            return (f" ⚠️ {host} est une IP privée bloquée par l'anti-SSRF : ajoute-la à "
                    "NET_GUARD_ALLOW_HOSTS (Réglages → Nextcloud) pour que ça fonctionne.")
    return ""


@router.get("/api/config/proxmox")
async def get_config_proxmox() -> Dict[str, Any]:
    sec = user_config.get(proxmox.K_TOKEN_SECRET, "") or ""
    masked = (f"{sec[:2]}…{sec[-2:]}" if len(sec) > 4 else ("***" if sec else ""))
    return {
        "url": user_config.get(proxmox.K_URL, "") or "",
        "token_id": user_config.get(proxmox.K_TOKEN_ID, "") or "",
        "token_secret": masked,
        "verify_tls": proxmox.verify_tls(),
        "configured": proxmox.is_configured(),
    }


@router.post("/api/config/proxmox")
async def save_config_proxmox(req: SaveProxmoxRequest) -> Dict[str, str]:
    updates = {
        proxmox.K_URL: (req.url or "").strip().rstrip("/"),
        proxmox.K_TOKEN_ID: (req.token_id or "").strip(),
        proxmox.K_VERIFY_TLS: "true" if req.verify_tls else "false",
    }
    if req.token_secret and "…" not in req.token_secret and req.token_secret != "***":
        updates[proxmox.K_TOKEN_SECRET] = req.token_secret.strip()
    user_config.set_many(updates)
    hint = _allowlist_hint(updates[proxmox.K_URL])
    return {"status": "success", "message": "Configuration Proxmox enregistrée." + hint}


@router.get("/api/config/proxmox/test")
async def test_config_proxmox() -> Dict[str, Any]:
    if not proxmox.is_configured():
        return {"ok": False, "detail": "Proxmox non configuré (URL / token id / secret)."}
    import requests
    from tools.net_guard import is_blocked_url
    url = proxmox.api_base() + "/version"
    if is_blocked_url(url):
        return {"ok": False, "detail": _allowlist_hint(proxmox.base_url()).strip()
                or "Hôte interne bloqué (anti-SSRF) : ajoute-le à NET_GUARD_ALLOW_HOSTS."}
    try:
        r = requests.get(url, headers=proxmox.auth_header(), verify=proxmox.verify_tls(), timeout=10)
        if r.status_code == 200:
            ver = (r.json().get("data") or {}).get("version", "?")
            return {"ok": True, "detail": f"Connexion Proxmox réussie ✅ (version {ver})"}
        if r.status_code == 401:
            return {"ok": False, "detail": "Jeton refusé (401) — vérifie l'ID de jeton et le secret."}
        return {"ok": False, "detail": f"Réponse inattendue ({r.status_code})."}
    except Exception as e:
        return {"ok": False, "detail": f"Connexion impossible : {e} "
                "(TLS auto-signé ? décoche « Vérifier le certificat TLS ».)"}

"""Configuration Proxmox VE (hyperviseur) — par-utilisateur avec repli .env.

Athena lit l'état du cluster (nœuds, VM QEMU, conteneurs LXC) et peut agir dessus
(démarrer/arrêter/redémarrer) via l'API REST native de Proxmox — pas de SDK.

Auth par JETON d'API (recommandé) : Proxmox → Datacenter → Permissions → API Tokens.
Le jeton se présente comme `USER@REALM!TOKENID` + un secret. En-tête envoyé :
    Authorization: PVEAPIToken=USER@REALM!TOKENID=SECRET

⚠️ Un Proxmox en IP privée (homelab) n'est joignable que si son hôte est dans
`NET_GUARD_ALLOW_HOSTS`. TLS auto-signé fréquent → PROXMOX_VERIFY_TLS=false par défaut.
"""
import os
from core import user_config

K_URL = "PROXMOX_URL"               # ex. https://192.168.1.20:8006
K_TOKEN_ID = "PROXMOX_TOKEN_ID"     # ex. root@pam!athena
K_TOKEN_SECRET = "PROXMOX_TOKEN_SECRET"
K_VERIFY_TLS = "PROXMOX_VERIFY_TLS"  # "true"/"false" (défaut false : homelab auto-signé)


def _get(key: str) -> str:
    v = user_config.get(key)
    if v:
        return str(v).strip()
    return (os.getenv(key, "") or "").strip()


def base_url() -> str:
    """Racine de l'API (sans slash final). Tolère qu'on saisisse l'URL sans port :8006."""
    u = _get(K_URL).rstrip("/")
    return u


def api_base() -> str:
    return base_url() + "/api2/json"


def token_id() -> str:
    return _get(K_TOKEN_ID)


def token_secret() -> str:
    return _get(K_TOKEN_SECRET)


def verify_tls() -> bool:
    return _get(K_VERIFY_TLS).lower() in ("true", "1", "yes")


def auth_header() -> dict:
    return {"Authorization": f"PVEAPIToken={token_id()}={token_secret()}"}


def is_configured() -> bool:
    return bool(base_url() and token_id() and token_secret())

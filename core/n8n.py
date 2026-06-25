"""Configuration n8n (automatisation) — par-utilisateur avec repli .env.

Athena pilote ton instance n8n via son API REST v1 : découvrir les workflows, les déclencher,
lire les exécutions, (dés)activer, et créer/éditer (sous validation HITL). Auth par CLÉ API
(n8n → Settings → n8n API → Create API key), en-tête `X-N8N-API-KEY`.

Sécurité : anti-SSRF (net_guard) sur chaque URL ; toute MUTATION (activer, créer, éditer,
supprimer, déclencher) est un outil SENSIBLE → validation utilisateur (HITL). En IP privée
(homelab), l'hôte n8n doit être dans `NET_GUARD_ALLOW_HOSTS`.
"""
import os
from core import user_config

K_URL = "N8N_API_URL"          # racine, ex. https://n8n.local (sans /api/v1)
K_KEY = "N8N_API_KEY"
K_VERIFY_TLS = "N8N_VERIFY_TLS"  # "true"/"false" — défaut true (n8n est en général derrière du TLS valide)


def _get(key: str) -> str:
    v = user_config.get(key)
    if v:
        return str(v).strip()
    return (os.getenv(key, "") or "").strip()


def base_url() -> str:
    return _get(K_URL).rstrip("/")


def api_base() -> str:
    return base_url() + "/api/v1"


def api_key() -> str:
    return _get(K_KEY)


def verify_tls() -> bool:
    # Défaut TRUE (contrairement à Proxmox) : on n'accepte l'auto-signé que si explicitement demandé.
    return _get(K_VERIFY_TLS).lower() not in ("false", "0", "no")


def auth_header() -> dict:
    return {"X-N8N-API-KEY": api_key(), "Accept": "application/json"}


def is_configured() -> bool:
    return bool(base_url() and api_key())

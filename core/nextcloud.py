"""Configuration Nextcloud PAR UTILISATEUR + dérivation des URLs DAV.

Un seul jeu d'identifiants (URL de base + utilisateur + mot de passe d'application) suffit
pour les trois services standards de Nextcloud :
  - Fichiers   (WebDAV)  : {base}/remote.php/dav/files/{user}/
  - Calendrier (CalDAV)  : {base}/remote.php/dav/calendars/{user}/
  - Contacts   (CardDAV) : {base}/remote.php/dav/addressbooks/users/{user}/

Stockage par-utilisateur (`user_config`, gitignoré) avec repli `.env` pour le mono-utilisateur.
⚠️ Un Nextcloud en IP privée (homelab) n'est joignable que si son hôte est dans
`NET_GUARD_ALLOW_HOSTS` (cf. tools/net_guard.py).

Bonnes pratiques : utiliser un **mot de passe d'application** Nextcloud (Réglages → Sécurité),
PAS le mot de passe principal.
"""
import os
from typing import Optional, Tuple
from core import user_config

# Clés de stockage (mêmes noms côté user_config et .env).
K_URL = "NEXTCLOUD_URL"
K_USER = "NEXTCLOUD_USERNAME"
K_PASSWORD = "NEXTCLOUD_PASSWORD"


def _get(key: str) -> str:
    v = user_config.get(key)
    if v:
        return str(v).strip()
    return (os.getenv(key, "") or "").strip()


def base_url() -> str:
    return _get(K_URL).rstrip("/")


def username() -> str:
    return _get(K_USER)


def auth() -> Tuple[str, str]:
    return (username(), _get(K_PASSWORD))


def is_configured() -> bool:
    return bool(base_url() and username() and _get(K_PASSWORD))


def files_base() -> str:
    """Racine WebDAV des fichiers de l'utilisateur (avec slash final)."""
    return f"{base_url()}/remote.php/dav/files/{username()}/"


def calendars_base() -> str:
    return f"{base_url()}/remote.php/dav/calendars/{username()}/"


def addressbooks_base() -> str:
    return f"{base_url()}/remote.php/dav/addressbooks/users/{username()}/"

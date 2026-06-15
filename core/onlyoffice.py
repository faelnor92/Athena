"""Intégration OnlyOffice Document Server : permet d'OUVRIR/ÉDITER un .docx du workspace
(notamment un roman révisé en modifications suivies) dans l'éditeur OnlyOffice embarqué dans
l'onglet Écriture.

Principe :
- L'éditeur (navigateur) charge api.js depuis le Document Server (DS) et reçoit une CONFIG
  signée en JWT (le DS exige JWT par défaut depuis la v7).
- La config contient une URL où le DS va TÉLÉCHARGER le fichier (server-to-server) et une URL
  de CALLBACK où il POSTera le document sauvegardé. Ces deux URLs sont protégées par un JETON
  à usage limité (court TTL) → on n'expose pas le workspace en clair.

Réglages (.env) :
  ONLYOFFICE_URL            base du Document Server (ex: http://192.168.1.50:8080)
  ONLYOFFICE_JWT_SECRET     secret JWT configuré dans le DS (obligatoire si JWT activé)
  ONLYOFFICE_PUBLIC_BASE    URL d'Athena VUE PAR LE DS (ex: http://192.168.1.50:8000) ; si vide,
                            on dérive de la requête (OK en LAN simple).
"""
import os
import time
import secrets
import threading

import jwt  # PyJWT

_LOCK = threading.Lock()
_TOKENS = {}          # token -> {"path": abs, "exp": ts, "mode": "edit|view"}
_TTL = 6 * 3600       # un document ouvert peut rester édité quelques heures


def is_configured() -> bool:
    return bool((os.getenv("ONLYOFFICE_URL", "") or "").strip())


def ds_url() -> str:
    return (os.getenv("ONLYOFFICE_URL", "") or "").strip().rstrip("/")


def _secret() -> str:
    return (os.getenv("ONLYOFFICE_JWT_SECRET", "") or "").strip()


def public_base(request_base: str = "") -> str:
    """URL d'Athena que le Document Server doit appeler (callback + download). Réglage explicite
    sinon dérivée de la requête (LAN). On retire le slash final."""
    b = (os.getenv("ONLYOFFICE_PUBLIC_BASE", "") or "").strip()
    return (b or (request_base or "")).rstrip("/")


def sign(payload: dict) -> str:
    """Signe un payload en JWT HS256 (vide si pas de secret → DS sans JWT)."""
    sec = _secret()
    return jwt.encode(payload, sec, algorithm="HS256") if sec else ""


def verify(token: str) -> dict:
    """Vérifie un JWT reçu du DS (callback). Renvoie le payload ou lève."""
    sec = _secret()
    if not sec:
        return {}
    return jwt.decode(token, sec, algorithms=["HS256"])


def register_token(abs_path: str, mode: str = "edit") -> str:
    """Crée un jeton à usage limité pointant vers un fichier (téléchargement DS + callback)."""
    tok = secrets.token_urlsafe(24)
    with _LOCK:
        _purge_locked()
        _TOKENS[tok] = {"path": abs_path, "exp": time.time() + _TTL, "mode": mode}
    return tok


def resolve_token(tok: str):
    """Renvoie le chemin absolu associé au jeton (ou None si inconnu/expiré)."""
    with _LOCK:
        e = _TOKENS.get(tok)
        if not e or e["exp"] < time.time():
            return None
        return e["path"]


def _purge_locked():
    now = time.time()
    for k in [k for k, v in _TOKENS.items() if v["exp"] < now]:
        _TOKENS.pop(k, None)

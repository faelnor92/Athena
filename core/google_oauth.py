"""OAuth2 Google PAR UTILISATEUR (Calendar + Gmail) — implémentation NATIVE.

But : permettre à chaque utilisateur de connecter SON compte Google (consentement OAuth)
pour que l'agent lise/écrive dans SON agenda et lise SES mails — SANS partage de calendrier
ni compte de service (cf. DEV_NOTES 2026-06-14, point 5).

Doctrine : zéro nouvelle dépendance (pas de google-auth/oauthlib). On parle directement aux
endpoints OAuth de Google en HTTP (comme `tools/agenda_sync.py` le fait déjà pour le JWT de
compte de service). Le `refresh_token` est stocké PAR UTILISATEUR dans `user_config` (gitignoré,
en clair comme .env — à protéger au niveau FS). Les `access_token` sont mis en cache en mémoire
avec leur expiration et renouvelés à la demande.

Distinct de `core/oidc.py` (SSO de LOGIN à Athena) : ici c'est l'autorisation d'APPELER les
API Google au nom de l'utilisateur.
"""
import os
import time
import json
import secrets
import threading
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

import requests

from core import user_config, shared_store

# --- Endpoints Google -------------------------------------------------------
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# --- Étendues demandées (Calendar lecture+écriture, Gmail lecture, identité) -
SCOPES: List[str] = [
    "https://www.googleapis.com/auth/calendar.events",  # lire ET écrire des événements
    "https://www.googleapis.com/auth/gmail.readonly",   # lecture seule des mails (doctrine mail)
    "openid",
    "email",
]

# Clés de stockage par-utilisateur (user_config) ----------------------------
_K_REFRESH = "GOOGLE_OAUTH_REFRESH_TOKEN"
_K_EMAIL = "GOOGLE_OAUTH_EMAIL"
_K_SCOPES = "GOOGLE_OAUTH_SCOPES"
_K_AT = "GOOGLE_OAUTH_CONNECTED_AT"

_STATE_NS = "google_oauth_state"      # state CSRF éphémère : token -> {user, redirect_uri, ts}
_STATE_TTL = 600                      # 10 min

# Cache mémoire des access_token : user -> (token, expiry_epoch)
_AT_CACHE: Dict[str, Tuple[str, float]] = {}
_AT_LOCK = threading.RLock()


# --- Configuration applicative (identifiants OAuth de l'app) -----------------
def client_id() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID", "") or "").strip()


def client_secret() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "") or "").strip()


def is_configured() -> bool:
    """L'app a-t-elle des identifiants OAuth (client_id+secret) ? Sinon bouton masqué."""
    return bool(client_id() and client_secret())


def redirect_uri(request_base_url: str = "") -> str:
    """URI de redirection OAuth.

    Priorité à GOOGLE_OAUTH_REDIRECT_URI (indispensable en homelab : Google REFUSE
    d'enregistrer une URI http:// sur une IP non-localhost → l'utilisateur doit fournir
    une URI HTTPS via domaine/tunnel). À défaut, on la dérive de l'URL de la requête."""
    env = (os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "") or "").strip()
    if env:
        return env
    base = (request_base_url or "").rstrip("/")
    return f"{base}/api/oauth/google/callback"


def _user() -> str:
    return user_config.current_user_key()


# --- Flux d'autorisation ----------------------------------------------------
def build_auth_url(request_base_url: str = "", user: Optional[str] = None) -> str:
    """Construit l'URL de consentement Google + enregistre un state CSRF lié à l'utilisateur."""
    if not is_configured():
        raise RuntimeError("OAuth Google non configuré (GOOGLE_OAUTH_CLIENT_ID/SECRET manquants).")
    user = user or _user()
    ruri = redirect_uri(request_base_url)
    state = secrets.token_urlsafe(24)
    shared_store.set(_STATE_NS, state, {"user": user, "redirect_uri": ruri, "ts": time.time()})
    params = {
        "client_id": client_id(),
        "redirect_uri": ruri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",       # → refresh_token
        "prompt": "consent",            # force le refresh_token même si déjà consenti
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"


def _pop_state(state: str) -> Optional[Dict[str, Any]]:
    """Vérifie + consomme un state (anti-rejeu, anti-CSRF). None si invalide/expiré."""
    if not state:
        return None
    data = shared_store.get(_STATE_NS, state)
    shared_store.delete(_STATE_NS, state)
    if not isinstance(data, dict):
        return None
    if time.time() - float(data.get("ts", 0)) > _STATE_TTL:
        return None
    return data


def exchange_code(code: str, state: str) -> Dict[str, Any]:
    """Échange le code d'autorisation contre des jetons et persiste le refresh_token.

    Renvoie {user, email}. Lève en cas d'échec (state invalide, refus, etc.)."""
    st = _pop_state(state)
    if not st:
        raise RuntimeError("État OAuth invalide ou expiré (CSRF).")
    user = st["user"]
    ruri = st["redirect_uri"]
    r = requests.post(_TOKEN_URL, data={
        "code": code,
        "client_id": client_id(),
        "client_secret": client_secret(),
        "redirect_uri": ruri,
        "grant_type": "authorization_code",
    }, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Échec d'échange du code ({r.status_code}) : {r.text[:300]}")
    tok = r.json()
    refresh = tok.get("refresh_token")
    access = tok.get("access_token")
    if not refresh:
        # Sans refresh_token, la connexion n'est pas durable. Cause habituelle : un consentement
        # antérieur sans prompt=consent. On a forcé prompt=consent → ne devrait pas arriver.
        raise RuntimeError("Google n'a pas renvoyé de refresh_token. Révoque l'accès dans ton "
                           "compte Google puis réessaie (le consentement doit être redonné).")
    email = ""
    if access:
        try:
            ui = requests.get(_USERINFO_URL, headers={"Authorization": f"Bearer {access}"}, timeout=10)
            if ui.status_code == 200:
                email = ui.json().get("email", "") or ""
        except Exception:
            pass
    user_config.set_many({
        _K_REFRESH: refresh,
        _K_EMAIL: email,
        _K_SCOPES: tok.get("scope", " ".join(SCOPES)),
        _K_AT: time.time(),
    }, user=user)
    # Amorce le cache d'access_token.
    if access:
        with _AT_LOCK:
            _AT_CACHE[user] = (access, time.time() + int(tok.get("expires_in", 3600)) - 60)
    return {"user": user, "email": email}


# --- Utilisation : jeton d'accès frais --------------------------------------
def get_access_token(user: Optional[str] = None) -> Optional[str]:
    """Renvoie un access_token valide pour l'utilisateur (renouvelé via refresh_token),
    ou None s'il n'a pas connecté son compte Google."""
    user = user or _user()
    now = time.time()
    with _AT_LOCK:
        cached = _AT_CACHE.get(user)
        if cached and cached[1] > now:
            return cached[0]
    refresh = user_config.get(_K_REFRESH, user=user)
    if not refresh:
        return None
    try:
        r = requests.post(_TOKEN_URL, data={
            "refresh_token": refresh,
            "client_id": client_id(),
            "client_secret": client_secret(),
            "grant_type": "refresh_token",
        }, timeout=15)
    except Exception as e:
        print(f"[Google OAuth] échec de rafraîchissement réseau : {e}")
        return None
    if r.status_code != 200:
        # refresh_token révoqué/expiré → on déconnecte proprement.
        print(f"[Google OAuth] refresh refusé ({r.status_code}) : {r.text[:200]}")
        if r.status_code in (400, 401):
            user_config.delete(_K_REFRESH, user=user)
            with _AT_LOCK:
                _AT_CACHE.pop(user, None)
        return None
    tok = r.json()
    access = tok.get("access_token")
    if not access:
        return None
    with _AT_LOCK:
        _AT_CACHE[user] = (access, now + int(tok.get("expires_in", 3600)) - 60)
    return access


def is_connected(user: Optional[str] = None) -> bool:
    return bool(user_config.get(_K_REFRESH, user=user or _user()))


def status(user: Optional[str] = None) -> Dict[str, Any]:
    user = user or _user()
    return {
        "configured": is_configured(),
        "connected": is_connected(user),
        "email": user_config.get(_K_EMAIL, default="", user=user) or "",
        "scopes": user_config.get(_K_SCOPES, default="", user=user) or "",
    }


def disconnect(user: Optional[str] = None) -> bool:
    """Révoque côté Google (best-effort) et efface le refresh_token local."""
    user = user or _user()
    refresh = user_config.get(_K_REFRESH, user=user)
    if refresh:
        try:
            requests.post(_REVOKE_URL, data={"token": refresh}, timeout=10)
        except Exception:
            pass
    for k in (_K_REFRESH, _K_EMAIL, _K_SCOPES, _K_AT):
        user_config.delete(k, user=user)
    with _AT_LOCK:
        _AT_CACHE.pop(user, None)
    return True

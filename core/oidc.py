"""Connexion OIDC / OAuth2 OPTIONNELLE (SSO entreprise : Google, Azure AD, Keycloak…).

Désactivée tant que OIDC_ISSUER / OIDC_CLIENT_ID / OIDC_CLIENT_SECRET ne sont pas
définis. Implémente le flux Authorization Code : redirection vers l'IdP, échange du
code, vérification de l'ID token (signature JWKS via PyJWT), puis provisionnement du
compte + session. Coexiste avec le login par mot de passe.

Env :
  OIDC_ISSUER          ex. https://accounts.google.com ou https://kc.exemple/realms/r
  OIDC_CLIENT_ID / OIDC_CLIENT_SECRET
  OIDC_REDIRECT_URI    (optionnel ; sinon déduit de la requête + /api/auth/oidc/callback)
  OIDC_SCOPES          (défaut "openid email profile")
  OIDC_DEFAULT_ROLE    (défaut "user")
  OIDC_ADMIN_EMAILS    CSV d'emails promus admin
"""
import os
import time
import secrets
import threading
import urllib.parse

import requests

_DISCOVERY = {}
_DISCOVERY_TS = 0
_STATES = {}          # state -> exp
_LOCK = threading.Lock()
_STATE_TTL = 600      # 10 min


def enabled() -> bool:
    return bool(os.getenv("OIDC_ISSUER", "").strip()
               and os.getenv("OIDC_CLIENT_ID", "").strip()
               and os.getenv("OIDC_CLIENT_SECRET", "").strip())


def discovery() -> dict:
    """Métadonnées OIDC (.well-known), mises en cache 1h."""
    global _DISCOVERY, _DISCOVERY_TS
    if _DISCOVERY and (time.time() - _DISCOVERY_TS) < 3600:
        return _DISCOVERY
    issuer = os.getenv("OIDC_ISSUER", "").strip().rstrip("/")
    url = issuer + "/.well-known/openid-configuration"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    _DISCOVERY = r.json()
    _DISCOVERY_TS = time.time()
    return _DISCOVERY


def _redirect_uri(request_base: str = "") -> str:
    fixed = os.getenv("OIDC_REDIRECT_URI", "").strip()
    if fixed:
        return fixed
    return request_base.rstrip("/") + "/api/auth/oidc/callback"


def new_state() -> str:
    state = secrets.token_urlsafe(24)
    now = time.time()
    with _LOCK:
        # purge des states expirés
        for s in [s for s, exp in _STATES.items() if exp < now]:
            _STATES.pop(s, None)
        _STATES[state] = now + _STATE_TTL
    return state


def check_state(state: str) -> bool:
    with _LOCK:
        exp = _STATES.pop(state, None)
    return bool(exp and exp >= time.time())


def authorization_url(request_base: str = "") -> str:
    conf = discovery()
    state = new_state()
    params = {
        "client_id": os.getenv("OIDC_CLIENT_ID", "").strip(),
        "response_type": "code",
        "scope": os.getenv("OIDC_SCOPES", "openid email profile").strip(),
        "redirect_uri": _redirect_uri(request_base),
        "state": state,
    }
    return conf["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)


def exchange_and_verify(code: str, request_base: str = "") -> dict:
    """Échange le code, vérifie l'ID token, renvoie les claims (sub, email, name…)."""
    conf = discovery()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _redirect_uri(request_base),
        "client_id": os.getenv("OIDC_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("OIDC_CLIENT_SECRET", "").strip(),
    }
    r = requests.post(conf["token_endpoint"], data=data, timeout=10)
    r.raise_for_status()
    tok = r.json()
    id_token = tok.get("id_token")
    if not id_token:
        raise RuntimeError("Réponse OIDC sans id_token.")

    import jwt
    from jwt import PyJWKClient
    jwks = PyJWKClient(conf["jwks_uri"])
    signing_key = jwks.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token, signing_key.key, algorithms=["RS256", "ES256"],
        audience=os.getenv("OIDC_CLIENT_ID", "").strip(),
        issuer=conf.get("issuer", os.getenv("OIDC_ISSUER", "").strip().rstrip("/")),
        options={"verify_aud": True},
    )
    return claims


def resolve_account(claims: dict):
    """Détermine (username, role) à partir des claims OIDC."""
    email = (claims.get("email") or "").strip().lower()
    username = email or claims.get("preferred_username") or ("oidc_" + str(claims.get("sub", ""))[:12])
    admins = [e.strip().lower() for e in os.getenv("OIDC_ADMIN_EMAILS", "").split(",") if e.strip()]
    role = "admin" if email and email in admins else (os.getenv("OIDC_DEFAULT_ROLE", "user").strip() or "user")
    return username, role

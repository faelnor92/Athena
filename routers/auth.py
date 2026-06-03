import os
import time
import secrets
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.users import user_store
from core.state import ACTIVE_SESSIONS, _current_username, _scope_cid

router = APIRouter(tags=["Auth"])

_SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "168") or 168) * 3600

# Anti-brute-force du login : IP -> [timestamps des échecs récents].
_LOGIN_FAILURES = {}
_LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "8") or 8)
_LOGIN_WINDOW = int(os.getenv("LOGIN_WINDOW_SECONDS", "300") or 300)


def _is_exposed_host(host: str) -> bool:
    """Vrai si le bind n'est pas strictement local (loopback)."""
    return host not in ("127.0.0.1", "localhost", "::1")


def _enforce_network_security():
    """Refuse une exposition réseau (0.0.0.0/IP publique) sans ADMIN_PASSWORD.
    Appelé AU CHARGEMENT DU MODULE pour couvrir aussi `uvicorn server:app`
    (et pas seulement `python server.py`)."""
    if os.getenv("ALLOW_INSECURE_NETWORK", "").lower() in ("true", "1", "yes"):
        return
    host = os.getenv("HOST", "0.0.0.0").strip()
    if _is_exposed_host(host) and not os.getenv("ADMIN_PASSWORD", "").strip() and user_store.count() == 0:
        raise RuntimeError(
            f"[SÉCURITÉ] Bind exposé ('{host}') sans ADMIN_PASSWORD ni utilisateur. "
            "Définissez ADMIN_PASSWORD, OU lancez en HOST=127.0.0.1, OU "
            "forcez ALLOW_INSECURE_NETWORK=true (déconseillé)."
        )


_enforce_network_security()


def _auth_active() -> bool:
    """L'auth est active s'il y a un mot de passe admin OU des utilisateurs."""
    return bool(os.getenv("ADMIN_PASSWORD", "").strip()) or user_store.count() > 0


def _new_session(username: str, role: str) -> str:
    """Crée un jeton de session horodaté (expire après _SESSION_TTL)."""
    token = secrets.token_hex(24)
    ACTIVE_SESSIONS[token] = {"username": username, "role": role, "exp": time.time() + _SESSION_TTL}
    return token


# --- Autorisation par rôle : endpoints réservés à l'administrateur -----------
# (config système, exécution de code, secrets, sauvegardes). Un compte de rôle
# « user » authentifié reçoit 403. Vérifié de façon CENTRALISÉE dans le
# middleware pour ne dépendre d'aucun oubli au niveau d'un endpoint.
_ADMIN_EXACT = {
    ("POST", "/api/terminal/coder"),
    ("POST", "/api/reset"),
    ("POST", "/api/workspace/config"),
    ("GET", "/api/workspace/dirs"),  # parcourir l'arborescence hôte = admin (anti-fuite)
    ("POST", "/api/config/agents"),
    ("GET", "/api/config/env"), ("POST", "/api/config/env"),
    ("GET", "/api/config/mcp"), ("POST", "/api/config/mcp"),
    ("GET", "/api/config/mcp/servers"), ("POST", "/api/config/mcp/servers"),
    ("POST", "/api/config/voice-wake"),
    ("GET", "/api/backup"), ("POST", "/api/backup/restore"),
    # NB: /api/config/agenda* n'est PLUS admin-only : la config agenda est désormais
    # PAR UTILISATEUR (chacun ne touche que la sienne via user_config). Cf. config_agenda.py.
    ("POST", "/api/telegram/pairing/approve"),
    ("POST", "/api/telegram/pairing/revoke"),
    ("POST", "/api/pricing"), ("POST", "/api/pricing/reset"),
    ("GET", "/api/logs"), ("POST", "/api/logs/level"),
}
_ADMIN_PREFIX = (
    ("POST", "/api/config/satellites"),
    ("DELETE", "/api/config/satellites/"),
    ("DELETE", "/api/config/skills/"),
    ("DELETE", "/api/config/mcp/servers/"),
    ("GET", "/api/users"), ("POST", "/api/users"), ("DELETE", "/api/users/"),
)


def _is_admin_only(method: str, path: str) -> bool:
    if (method, path) in _ADMIN_EXACT:
        return True
    return any(method == m and path.startswith(pfx) for m, pfx in _ADMIN_PREFIX)


class LoginRequest(BaseModel):
    password: str
    username: str = None



async def auth_middleware(request: Request, call_next):
    # Endpoints PUBLICS (pas de session requise) : login, inscription par invitation,
    # flux OIDC, et webhooks entrants (protégés par leur propre secret).
    path = request.url.path
    public = (path == "/api/login" or path == "/api/register"
              or path.startswith("/api/auth/oidc/") or path.startswith("/api/hooks/"))
    if _auth_active() and path.startswith("/api/") and not public:
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Non autorisé. Jeton de session manquant."})
        token = auth_header.split(" ")[1]
        sess = ACTIVE_SESSIONS.get(token)
        if not sess:
            return JSONResponse(status_code=401, content={"detail": "Non autorisé. Session expirée ou invalide."})
        if sess.get("exp", 0) < time.time():
            ACTIVE_SESSIONS.pop(token, None)
            return JSONResponse(status_code=401, content={"detail": "Session expirée. Reconnectez-vous."})
        request.state.user = sess
        _current_username.set(sess.get("username"))
        # Garde-fou d'autorisation : endpoints sensibles réservés aux admins.
        if _is_admin_only(request.method, request.url.path) and sess.get("role") != "admin":
            return JSONResponse(status_code=403, content={"detail": "Réservé à l'administrateur."})
    response = await call_next(request)
    return response


@router.get("/api/auth/oidc/status")
async def oidc_status():
    """Indique si le SSO OIDC est configuré (pour afficher le bouton dans l'UI)."""
    from core import oidc
    return {"enabled": oidc.enabled()}


@router.get("/api/auth/oidc/login")
async def oidc_login(request: Request):
    """Démarre le flux SSO : redirige vers l'IdP."""
    from core import oidc
    from fastapi.responses import RedirectResponse
    if not oidc.enabled():
        raise HTTPException(status_code=400, detail="SSO OIDC non configuré.")
    try:
        base = str(request.base_url)
        return RedirectResponse(oidc.authorization_url(base), status_code=302)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OIDC indisponible : {e}")


@router.get("/api/auth/oidc/callback")
async def oidc_callback(request: Request, code: str = "", state: str = ""):
    """Retour de l'IdP : vérifie, provisionne le compte, ouvre une session, renvoie au SPA."""
    from core import oidc
    from fastapi.responses import RedirectResponse
    if not oidc.enabled():
        raise HTTPException(status_code=400, detail="SSO OIDC non configuré.")
    if not code or not oidc.check_state(state):
        raise HTTPException(status_code=403, detail="État OIDC invalide ou expiré (CSRF).")
    try:
        claims = oidc.exchange_and_verify(code, str(request.base_url))
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"Échec de la vérification OIDC : {e}")
    username, role = oidc.resolve_account(claims)
    # Provisionne le compte s'il n'existe pas (mot de passe aléatoire inutilisable : login via SSO).
    if not any(u["username"] == username for u in user_store.list()):
        user_store.create(username, secrets.token_urlsafe(24), role)
    token = _new_session(username, role)
    # Renvoie au SPA avec le jeton (le frontend le stocke puis nettoie l'URL).
    return RedirectResponse(f"/?sso_token={token}", status_code=302)


@router.post("/api/login")
async def login(req: LoginRequest, request: Request):
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    # Anti-brute-force : throttle par IP au-delà de N échecs dans la fenêtre.
    client_ip = request.client.host if request.client else "?"
    now = time.time()
    fails = [t for t in _LOGIN_FAILURES.get(client_ip, []) if now - t < _LOGIN_WINDOW]
    if len(fails) >= _LOGIN_MAX_FAILS:
        _LOGIN_FAILURES[client_ip] = fails
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez plus tard.")

    def _fail():
        fails.append(now)
        _LOGIN_FAILURES[client_ip] = fails

    # 1. Multi-utilisateur : si des comptes existent et un username est fourni.
    if user_store.count() > 0 and req.username:
        role = user_store.verify(req.username, req.password)
        if role:
            _LOGIN_FAILURES.pop(client_ip, None)
            token = _new_session(req.username, role)
            return {"status": "success", "token": token, "username": req.username, "role": role}

    # 2. Admin « bootstrap » via ADMIN_PASSWORD (toujours valable pour l'owner).
    if admin_password and secrets.compare_digest(req.password, admin_password):
        _LOGIN_FAILURES.pop(client_ip, None)
        token = _new_session(req.username or "admin", "admin")
        return {"status": "success", "token": token, "username": req.username or "admin", "role": "admin"}

    # 3. Aucune auth configurée.
    if not _auth_active():
        return {"status": "success", "token": "no-auth-required", "username": "local", "role": "admin"}

    _fail()
    raise HTTPException(status_code=401, detail="Identifiants incorrects")


def _current_user(request: Request) -> dict:
    return getattr(request.state, "user", None) or {"username": "local", "role": "admin"}


def _require_admin(request: Request):
    # Si l'auth n'est pas active (local de confiance) ou rôle admin → autorisé.
    if not _auth_active():
        return
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé à l'administrateur.")


@router.get("/api/me")
async def get_me(request: Request):
    return _current_user(request)


class PasswordChangeRequest(BaseModel):
    current_password: str = ""
    new_password: str


@router.post("/api/me/password")
async def change_my_password(request: Request, req: PasswordChangeRequest):
    """Change le mot de passe du COMPTE COURANT (vérifie l'ancien). Self-service."""
    if len((req.new_password or "")) < 4:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe trop court (min. 4 caractères).")
    username = _current_user(request).get("username")
    if not username or user_store.verify(username, req.current_password) is None:
        raise HTTPException(status_code=403,
                            detail="Mot de passe actuel incorrect (ou compte sans mot de passe propre, ex. admin bootstrap).")
    if not user_store.set_password(username, req.new_password):
        raise HTTPException(status_code=400, detail="Changement impossible.")
    return {"status": "success"}


class InviteRequest(BaseModel):
    role: str = "user"
    expires_hours: int = 168


@router.post("/api/users/invites")
async def create_invite(request: Request, req: InviteRequest):
    """Génère une invitation d'inscription (ADMIN). Renvoie le code à partager."""
    _require_admin(request)
    from core.invites import invite_store
    inv = invite_store.create(role=req.role, expires_hours=req.expires_hours,
                              created_by=_current_user(request).get("username", ""))
    return {"status": "success", "invite": inv}


@router.get("/api/users/invites")
async def list_invites(request: Request):
    _require_admin(request)
    from core.invites import invite_store
    return {"invites": invite_store.list()}


@router.delete("/api/users/invites/{code}")
async def revoke_invite(request: Request, code: str):
    _require_admin(request)
    from core.invites import invite_store
    if not invite_store.revoke(code):
        raise HTTPException(status_code=404, detail="Invitation introuvable.")
    return {"status": "success"}


class RegisterRequest(BaseModel):
    code: str
    username: str
    password: str


@router.post("/api/register")
async def register(req: RegisterRequest):
    """Inscription PUBLIQUE via un code d'invitation valide → crée le compte + connecte."""
    from core.invites import invite_store
    username = (req.username or "").strip()
    if not username or len((req.password or "")) < 4:
        raise HTTPException(status_code=400, detail="username requis et mot de passe d'au moins 4 caractères.")
    inv = invite_store.check(req.code)
    if not inv:
        raise HTTPException(status_code=403, detail="Invitation invalide, expirée ou déjà utilisée.")
    if user_store.verify(username, "") is not None or any(u["username"] == username for u in user_store.list()):
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà.")
    # Consommer l'invitation AVANT de créer (atomique : évite la double-utilisation).
    if not invite_store.consume(req.code, username):
        raise HTTPException(status_code=403, detail="Invitation déjà utilisée.")
    if not user_store.create(username, req.password, inv["role"]):
        raise HTTPException(status_code=400, detail="Création du compte impossible.")
    token = _new_session(username, inv["role"])
    return {"status": "success", "token": token, "username": username, "role": inv["role"]}


class AdminPasswordResetRequest(BaseModel):
    new_password: str


@router.post("/api/users/{username}/password")
async def admin_reset_password(request: Request, username: str, req: AdminPasswordResetRequest):
    """Réinitialise le mot de passe d'un utilisateur (ADMIN ; sans l'ancien)."""
    _require_admin(request)
    if len((req.new_password or "")) < 4:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (min. 4 caractères).")
    if not user_store.set_password(username, req.new_password):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return {"status": "success"}


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


@router.get("/api/users")
async def list_users(request: Request):
    _require_admin(request)
    return {"users": user_store.list(), "auth_active": _auth_active()}


@router.post("/api/users")
async def create_user(request: Request, req: UserCreateRequest):
    _require_admin(request)
    if not user_store.create(req.username, req.password, req.role):
        raise HTTPException(status_code=400, detail="username/password requis.")
    return {"status": "success"}


@router.delete("/api/users/{username}")
async def delete_user(request: Request, username: str, purge: bool = True):
    _require_admin(request)
    # Empêcher de supprimer le dernier admin restant.
    users = user_store.list()
    admins = [u for u in users if u["role"] == "admin"]
    target = next((u for u in users if u["username"] == username), None)
    if target and target["role"] == "admin" and len(admins) <= 1:
        raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur.")
    if not user_store.delete(username):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    report = None
    if purge:
        # RGPD : efface toutes les données propres au compte (best-effort).
        try:
            from core.user_data import purge_user
            report = purge_user(username)
        except Exception:
            import logging
            logging.exception("Purge des données utilisateur échouée")
    return {"status": "success", "purged": report}


import os
import time
import secrets
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.users import user_store
from core.state import ACTIVE_SESSIONS, _current_username, _current_role, _scope_cid
from core import audit

router = APIRouter(tags=["Auth"])

_SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "168") or 168) * 3600

# Anti-brute-force du login : IP -> [timestamps des échecs récents].
_LOGIN_MAX_FAILS = int(os.getenv("LOGIN_MAX_FAILS", "8") or 8)
_LOGIN_WINDOW = int(os.getenv("LOGIN_WINDOW_SECONDS", "300") or 300)
_MIN_PASSWORD_LEN = int(os.getenv("MIN_PASSWORD_LENGTH", "8") or 8)


# Throttle anti-brute-force partagé entre workers (ns "login_fail" du store SQLite),
# au lieu d'un dict par-process inefficace en multi-worker.
def _recent_fails(ip: str) -> list:
    from core import shared_store
    now = time.time()
    return [t for t in (shared_store.get("login_fail", ip) or []) if now - t < _LOGIN_WINDOW]


def _record_login_fail(ip: str):
    from core import shared_store
    now = time.time()
    shared_store.update("login_fail", ip,
                        lambda l: [t for t in (l or []) if now - t < _LOGIN_WINDOW] + [now])


def _clear_login_fails(ip: str):
    from core import shared_store
    shared_store.delete("login_fail", ip)


def _bearer_token(request: Request) -> str:
    h = request.headers.get("Authorization", "")
    return h.split(" ", 1)[1].strip() if h.startswith("Bearer ") else ""


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
    ("GET", "/api/usage"),
    ("GET", "/api/audit"),
    ("GET", "/api/pipelines/pending"), ("GET", "/api/routines/pending"),
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
        _current_role.set(sess.get("role"))
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

    # Anti-brute-force : throttle par IP au-delà de N échecs dans la fenêtre (partagé
    # entre workers via le store SQLite).
    client_ip = audit.client_ip(request)
    if len(_recent_fails(client_ip)) >= _LOGIN_MAX_FAILS:
        audit.log("login_blocked", actor=req.username or "?", ip=client_ip, detail="throttle brute-force")
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez plus tard.")

    def _ok(username, role):
        _clear_login_fails(client_ip)
        try:
            ACTIVE_SESSIONS.purge_expired()  # hygiène opportuniste du store de sessions
        except Exception:
            pass
        audit.log("login", actor=username, role=role, ip=client_ip)
        return {"status": "success", "token": _new_session(username, role),
                "username": username, "role": role}

    # 1. Multi-utilisateur : si des comptes existent et un username est fourni.
    if user_store.count() > 0 and req.username:
        role = user_store.verify(req.username, req.password)
        if role:
            return _ok(req.username, role)

    # 2. Admin « bootstrap » via ADMIN_PASSWORD (toujours valable pour l'owner).
    if admin_password and secrets.compare_digest(req.password, admin_password):
        return _ok(req.username or "admin", "admin")

    # 3. Aucune auth configurée.
    if not _auth_active():
        return {"status": "success", "token": "no-auth-required", "username": "local", "role": "admin"}

    _record_login_fail(client_ip)
    audit.log("login_failed", actor=req.username or "?", ip=client_ip)
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
    """Change le mot de passe du COMPTE COURANT (vérifie l'ancien). Self-service.
    Révoque les AUTRES sessions du compte (la session courante est conservée)."""
    if len((req.new_password or "")) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"Nouveau mot de passe trop court (min. {_MIN_PASSWORD_LEN} caractères).")
    username = _current_user(request).get("username")
    if not username or user_store.verify(username, req.current_password) is None:
        raise HTTPException(status_code=403,
                            detail="Mot de passe actuel incorrect (ou compte sans mot de passe propre, ex. admin bootstrap).")
    if not user_store.set_password(username, req.new_password):
        raise HTTPException(status_code=400, detail="Changement impossible.")
    ACTIVE_SESSIONS.revoke_user(username, keep_token=_bearer_token(request))
    audit.log("password_change", actor=username, ip=audit.client_ip(request))
    return {"status": "success"}


@router.post("/api/logout")
async def logout(request: Request):
    """Invalide le jeton de session courant."""
    tok = _bearer_token(request)
    if tok:
        ACTIVE_SESSIONS.pop(tok, None)
    audit.log("logout", actor=_current_user(request).get("username"), ip=audit.client_ip(request))
    return {"status": "success"}


@router.get("/api/audit")
async def get_audit(request: Request, limit: int = 200, action: str = None):
    """Journal d'audit des événements de sécurité (ADMIN)."""
    _require_admin(request)
    return {"events": audit.recent(limit=min(int(limit or 200), 1000), action=action)}


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
async def register(req: RegisterRequest, request: Request):
    """Inscription PUBLIQUE via un code d'invitation valide → crée le compte + connecte."""
    from core.invites import invite_store
    username = (req.username or "").strip()
    if not username or len((req.password or "")) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"username requis et mot de passe d'au moins {_MIN_PASSWORD_LEN} caractères.")
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
    audit.log("register", actor=username, role=inv["role"], ip=audit.client_ip(request),
              detail=f"invitation de {inv.get('created_by', '?')}")
    return {"status": "success", "token": token, "username": username, "role": inv["role"]}


class AdminPasswordResetRequest(BaseModel):
    new_password: str


@router.post("/api/users/{username}/password")
async def admin_reset_password(request: Request, username: str, req: AdminPasswordResetRequest):
    """Réinitialise le mot de passe d'un utilisateur (ADMIN ; sans l'ancien)."""
    _require_admin(request)
    if len((req.new_password or "")) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"Mot de passe trop court (min. {_MIN_PASSWORD_LEN} caractères).")
    if not user_store.set_password(username, req.new_password):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    # Reset admin → on déconnecte l'utilisateur de TOUTES ses sessions.
    ACTIVE_SESSIONS.revoke_user(username)
    audit.log("password_reset", actor=_current_user(request).get("username"),
              role="admin", target=username, ip=audit.client_ip(request))
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
    if len((req.password or "")) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"Mot de passe trop court (min. {_MIN_PASSWORD_LEN} caractères).")
    if not user_store.create(req.username, req.password, req.role):
        raise HTTPException(status_code=400, detail="username/password requis.")
    audit.log("user_create", actor=_current_user(request).get("username"), role="admin",
              target=req.username, ip=audit.client_ip(request), detail=f"rôle={req.role}")
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
    ACTIVE_SESSIONS.revoke_user(username)  # invalide ses sessions immédiatement
    report = None
    if purge:
        # RGPD : efface toutes les données propres au compte (best-effort).
        try:
            from core.user_data import purge_user
            report = purge_user(username)
        except Exception:
            import logging
            logging.exception("Purge des données utilisateur échouée")
    audit.log("user_delete", actor=_current_user(request).get("username"), role="admin",
              target=username, ip=audit.client_ip(request), detail=f"purge={purge}")
    return {"status": "success", "purged": report}


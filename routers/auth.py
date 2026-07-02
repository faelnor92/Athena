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
# Plafond ABSOLU d'une session depuis le login (expiration glissante : l'usage régulier
# prolonge la session dans la limite de ce plafond — un jeton volé n'est jamais éternel).
_SESSION_ABSOLUTE = max(
    int(os.getenv("SESSION_ABSOLUTE_HOURS", "720") or 720) * 3600, _SESSION_TTL)

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
    """Crée un jeton de session horodaté (fenêtre d'inactivité _SESSION_TTL,
    prolongée à l'usage jusqu'au plafond absolu _SESSION_ABSOLUTE)."""
    token = secrets.token_hex(24)
    now = time.time()
    ACTIVE_SESSIONS[token] = {"username": username, "role": role,
                              "exp": now + _SESSION_TTL, "created": now}
    return token


def maybe_extend_session(token: str, sess: dict, now: float = None) -> bool:
    """Expiration GLISSANTE : le TTL est une fenêtre d'INACTIVITÉ — chaque requête
    authentifiée repousse l'expiration, dans la limite du plafond absolu depuis le
    login. Le store n'est réécrit que si ≥10 % du TTL est consommé (amortit les
    écritures SQLite : au plus ~10 écritures par fenêtre, pas une par requête).
    Renvoie True si la session a été prolongée."""
    now = time.time() if now is None else now
    exp = sess.get("exp", 0)
    if exp - now >= _SESSION_TTL * 0.9:
        return False
    # Sessions d'avant la migration (sans "created") : on estime le login au début
    # de la fenêtre courante — prudent (jamais plus permissif que le plafond réel).
    hard_cap = sess.get("created", exp - _SESSION_TTL) + _SESSION_ABSOLUTE
    new_exp = min(now + _SESSION_TTL, hard_cap)
    if new_exp <= exp:
        return False
    sess["exp"] = new_exp
    ACTIVE_SESSIONS[token] = sess
    return True


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
    # Registre multi-hôtes SSH (surface sensible) : admin uniquement.
    ("GET", "/api/ssh/hosts"), ("POST", "/api/ssh/hosts"), ("DELETE", "/api/ssh/hosts/"),
    # Plugins : activer/désactiver est un changement GLOBAL (ex. Claude Code = exécution de
    # code) → admin uniquement (sans effet en mode local : rôle admin par défaut).
    ("POST", "/api/plugins/"),
)


def _is_admin_only(method: str, path: str) -> bool:
    if (method, path) in _ADMIN_EXACT:
        return True
    return any(method == m and path.startswith(pfx) for m, pfx in _ADMIN_PREFIX)


class LoginRequest(BaseModel):
    password: str
    username: str | None = None
    totp: str | None = None  # code 2FA (si activé pour le compte)


# Endpoints qui déclenchent un run LLM (throttlés par compte/IP dans le middleware).
_LLM_THROTTLED_PREFIXES = ("/api/chat", "/api/structured", "/api/terminal/coder")



async def auth_middleware(request: Request, call_next):
    # Endpoints PUBLICS (pas de session requise) : login, inscription par invitation,
    # flux OIDC, et webhooks entrants (protégés par leur propre secret).
    path = request.url.path
    # Langue d'interface (en-tête posé par le front) → ContextVar, pour faire répondre les
    # agents dans la langue de l'utilisateur. Indépendant de l'auth (vaut aussi en mode local).
    try:
        from core.state import _current_lang, LANG_NAMES
        _hl = (request.headers.get("X-Athena-Lang") or "").strip().lower()[:2]
        _current_lang.set(_hl if _hl in LANG_NAMES else "fr")
    except Exception:
        pass
    public = (path == "/api/login" or path == "/api/register"
              or path.startswith("/api/auth/oidc/") or path.startswith("/api/hooks/")
              # Version + vérification de mise à jour : non sensibles, affichées aussi sur
              # l'écran de connexion (sinon « v0.0.0 » et « Vérification… » restent figés).
              or path == "/api/system/version"
              or path == "/api/system/update_check"
              # Ingress d'événements externes (monitoring) : pas de session, jeton dédié
              # validé DANS l'endpoint (cf. routers/config_events.py).
              or (request.method == "POST" and path == "/api/events")
              # Partage AthenaDesign en lecture seule par jeton (non énumérable).
              or path.startswith("/api/athenadesign/shared/")
              # OnlyOffice Document Server (server-to-server) : ne porte pas de session ; ces
              # deux endpoints sont protégés par un JETON à usage limité + JWT (cf. core.onlyoffice).
              or path == "/api/redaction/onlyoffice/file"
              or path == "/api/redaction/onlyoffice/callback")
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
        maybe_extend_session(token, sess)  # expiration glissante (bornée par le plafond absolu)
        request.state.user = sess
        _current_username.set(sess.get("username"))
        _current_role.set(sess.get("role"))
        # Garde-fou d'autorisation : endpoints sensibles réservés aux admins.
        if _is_admin_only(request.method, request.url.path) and sess.get("role") != "admin":
            return JSONResponse(status_code=403, content={"detail": "Réservé à l'administrateur."})
    # Rate-limit des endpoints qui CONSOMMENT du LLM (anti déni-de-portefeuille sur les
    # clés API si un compte « user » est compromis, ou bot derrière le reverse proxy).
    # Par compte authentifié, sinon par IP. LLM_RATE_LIMIT_PER_MIN=0 pour désactiver.
    llm_limit = int(os.getenv("LLM_RATE_LIMIT_PER_MIN", "60") or 0)
    if (llm_limit > 0 and request.method == "POST"
            and any(path == p or path.startswith(p + "/") for p in _LLM_THROTTLED_PREFIXES)):
        from core import throttle
        sess = getattr(request.state, "user", None) or {}
        who = sess.get("username") or audit.client_ip(request)
        if not throttle.allow("llm", who, llm_limit, 60):
            audit.log("llm_throttled", actor=who, ip=audit.client_ip(request), detail=path)
            return JSONResponse(status_code=429,
                                content={"detail": "Trop de requêtes. Réessayez dans une minute."})
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
    # Renvoie au SPA avec le jeton dans le FRAGMENT (#), jamais en query string :
    # le fragment n'est jamais envoyé au serveur (ni au reverse proxy, ni dans
    # un header Referer), contrairement à ?sso_token=... qui finirait dans les
    # logs et l'historique navigateur.
    return RedirectResponse(f"/#sso_token={token}", status_code=302)


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
            # 2FA : si activée, exiger un code TOTP valide (mot de passe déjà vérifié).
            mfa = user_store.get_mfa(req.username)
            if mfa and mfa.get("enabled"):
                if not req.totp:
                    # Mot de passe correct mais 2FA requise → l'UI doit demander le code.
                    raise HTTPException(status_code=401,
                                        detail={"mfa_required": True, "message": "Code 2FA requis."})
                from core import totp
                from core.state import _decrypt
                if not totp.verify(_decrypt(mfa.get("secret", "")), req.totp):
                    _record_login_fail(client_ip)
                    audit.log("login_failed", actor=req.username, ip=client_ip, detail="2FA invalide")
                    raise HTTPException(status_code=401, detail="Code 2FA invalide.")
            return _ok(req.username, role)

    # 2. Admin « bootstrap » via ADMIN_PASSWORD (toujours valable pour l'owner).
    # Username FORCÉ à "admin" (jamais req.username) : sinon quiconque connaît
    # ADMIN_PASSWORD peut ouvrir une session sous l'identité d'un autre compte,
    # polluant l'audit et contournant sa 2FA.
    if admin_password and secrets.compare_digest(req.password, admin_password):
        return _ok("admin", "admin")

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


# --- 2FA / TOTP (self-service) ----------------------------------------------
class MfaCodeRequest(BaseModel):
    code: str = ""


@router.get("/api/me/mfa")
async def my_mfa_status(request: Request):
    username = _current_user(request).get("username")
    return {"enabled": user_store.mfa_enabled(username)}


@router.post("/api/me/mfa/setup")
async def my_mfa_setup(request: Request):
    """Génère un secret TOTP (en attente d'activation) et renvoie l'URI otpauth + le secret."""
    from core import totp
    from core.state import _encrypt
    username = _current_user(request).get("username")
    if not username or username == "local":
        raise HTTPException(status_code=400, detail="2FA indisponible pour ce compte.")
    secret = totp.generate_secret()
    user_store.set_mfa(username, _encrypt(secret), enabled=False)  # pas encore actif
    return {"secret": secret, "otpauth_uri": totp.provisioning_uri(secret, username)}


@router.post("/api/me/mfa/enable")
async def my_mfa_enable(request: Request, req: MfaCodeRequest):
    """Active la 2FA après vérification d'un premier code (preuve que l'app est configurée)."""
    from core import totp
    from core.state import _decrypt
    username = _current_user(request).get("username")
    mfa = user_store.get_mfa(username)
    if not mfa or not mfa.get("secret"):
        raise HTTPException(status_code=400, detail="Lancez d'abord la configuration 2FA.")
    if not totp.verify(_decrypt(mfa["secret"]), req.code):
        raise HTTPException(status_code=403, detail="Code 2FA invalide.")
    user_store.set_mfa(username, mfa["secret"], enabled=True)
    audit.log("mfa_enable", actor=username, ip=audit.client_ip(request))
    return {"status": "success"}


@router.post("/api/me/mfa/disable")
async def my_mfa_disable(request: Request, req: MfaCodeRequest):
    """Désactive la 2FA (exige un code valide pour éviter une désactivation par session volée)."""
    from core import totp
    from core.state import _decrypt
    username = _current_user(request).get("username")
    mfa = user_store.get_mfa(username)
    if not mfa or not mfa.get("enabled"):
        return {"status": "success"}  # déjà désactivée
    if not totp.verify(_decrypt(mfa["secret"]), req.code):
        raise HTTPException(status_code=403, detail="Code 2FA invalide.")
    user_store.clear_mfa(username)
    audit.log("mfa_disable", actor=username, ip=audit.client_ip(request))
    return {"status": "success"}


@router.post("/api/users/{username}/mfa/reset")
async def admin_reset_mfa(request: Request, username: str):
    """Réinitialise (désactive) la 2FA d'un compte — récupération si appareil perdu (ADMIN)."""
    _require_admin(request)
    user_store.clear_mfa(username)
    audit.log("mfa_reset", actor=_current_user(request).get("username"), role="admin",
              target=username, ip=audit.client_ip(request))
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
    from core import throttle
    from core.invites import invite_store
    # Anti-brute-force des CODES D'INVITATION (endpoint public) : même politique que le login.
    client_ip = audit.client_ip(request)
    if throttle.too_many("register_fail", client_ip, _LOGIN_MAX_FAILS, _LOGIN_WINDOW):
        audit.log("register_blocked", actor=req.username or "?", ip=client_ip, detail="throttle brute-force")
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez plus tard.")
    username = (req.username or "").strip()
    if not username or len((req.password or "")) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"username requis et mot de passe d'au moins {_MIN_PASSWORD_LEN} caractères.")
    inv = invite_store.check(req.code)
    if not inv:
        throttle.record("register_fail", client_ip, _LOGIN_WINDOW)
        audit.log("register_failed", actor=username, ip=client_ip, detail="code d'invitation invalide")
        raise HTTPException(status_code=403, detail="Invitation invalide, expirée ou déjà utilisée.")
    if user_store.verify(username, "") is not None or any(u["username"] == username for u in user_store.list()):
        raise HTTPException(status_code=409, detail="Ce nom d'utilisateur existe déjà.")
    # Consommer l'invitation AVANT de créer (atomique : évite la double-utilisation).
    if not invite_store.consume(req.code, username):
        raise HTTPException(status_code=403, detail="Invitation déjà utilisée.")
    if not user_store.create(username, req.password, inv["role"]):
        raise HTTPException(status_code=400, detail="Création du compte impossible.")
    throttle.clear("register_fail", client_ip)
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


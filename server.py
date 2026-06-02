import os
import re
import json
import time
import uuid
import shlex
import tempfile
import secrets
import asyncio
import threading
import contextvars
from fastapi import FastAPI, HTTPException, File, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from dotenv import load_dotenv

# Chargement du .env
load_dotenv()

# Confiner par défaut l'espace de travail des agents (explorateur de fichiers,
# sandbox, outils shell/code) au sous-dossier workspace/ — évite d'exposer le
# code source et le .env de l'installation. Surchargeable via ACTIVE_WORKSPACE_DIR.
if not os.environ.get("ACTIVE_WORKSPACE_DIR", "").strip():
    _default_ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
    os.makedirs(_default_ws, exist_ok=True)
    os.environ["ACTIVE_WORKSPACE_DIR"] = _default_ws

from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger("jarvis.server")

from core.swarm import Swarm
from core.tracing import run_store
from core.run_context import registry as run_registry, current_run_id
from core import channels, approvals
from core.routines import routine_store, start_scheduler as start_routine_scheduler
from core.users import user_store
from tools.memory_tools import core_mem

app = FastAPI(title="Jarvis Multi-Agent Dashboard")

# Restriction stricte du CORS (sécurité VPS / CSRF)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gestion des sessions d'authentification : token -> {username, role, exp}.
ACTIVE_SESSIONS = {}

# Utilisateur authentifié du requête courante (pour cloisonner les données par
# utilisateur en mode multi-comptes). Posé par le middleware, lu par SessionManager.
_current_username = contextvars.ContextVar("current_username", default=None)


def _scope_cid(client_id: str) -> str:
    """Préfixe le client_id par l'utilisateur authentifié (cloisonnement multi-comptes).
    En mode local sans auth (aucun utilisateur), renvoie le client_id inchangé."""
    client_id = (client_id or "web").strip() or "web"
    if client_id.startswith("u:"):
        return client_id  # déjà scopé
    user = _current_username.get()
    if user:
        return f"u:{user}:{client_id}"
    return client_id
_SESSION_TTL = int(os.getenv("SESSION_TTL_HOURS", "168") or 168) * 3600  # défaut 7 jours

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
    ("POST", "/api/config/agents"),
    ("GET", "/api/config/env"), ("POST", "/api/config/env"),
    ("GET", "/api/config/mcp"), ("POST", "/api/config/mcp"),
    ("POST", "/api/config/voice-wake"),
    ("GET", "/api/backup"), ("POST", "/api/backup/restore"),
    ("POST", "/api/config/agenda/google-key"),
    ("POST", "/api/telegram/pairing/approve"),
    ("POST", "/api/telegram/pairing/revoke"),
    ("POST", "/api/pricing"), ("POST", "/api/pricing/reset"),
}
_ADMIN_PREFIX = (
    ("POST", "/api/config/satellites"),
    ("DELETE", "/api/config/satellites/"),
    ("DELETE", "/api/config/skills/"),
    ("GET", "/api/users"), ("POST", "/api/users"), ("DELETE", "/api/users/"),
)


def _is_admin_only(method: str, path: str) -> bool:
    if (method, path) in _ADMIN_EXACT:
        return True
    return any(method == m and path.startswith(pfx) for m, pfx in _ADMIN_PREFIX)


class LoginRequest(BaseModel):
    password: str
    username: str = None


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Webhooks entrants exemptés (protégés par leur propre secret).
    is_hook = request.url.path.startswith("/api/hooks/")
    if _auth_active() and request.url.path.startswith("/api/") and request.url.path != "/api/login" and not is_hook:
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


@app.post("/api/login")
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


@app.get("/api/me")
async def get_me(request: Request):
    return _current_user(request)


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


@app.get("/api/users")
async def list_users(request: Request):
    _require_admin(request)
    return {"users": user_store.list(), "auth_active": _auth_active()}


@app.post("/api/users")
async def create_user(request: Request, req: UserCreateRequest):
    _require_admin(request)
    if not user_store.create(req.username, req.password, req.role):
        raise HTTPException(status_code=400, detail="username/password requis.")
    return {"status": "success"}


@app.delete("/api/users/{username}")
async def delete_user(request: Request, username: str):
    _require_admin(request)
    # Empêcher de supprimer le dernier admin restant.
    users = user_store.list()
    admins = [u for u in users if u["role"] == "admin"]
    target = next((u for u in users if u["username"] == username), None)
    if target and target["role"] == "admin" and len(admins) <= 1:
        raise HTTPException(status_code=400, detail="Impossible de supprimer le dernier administrateur.")
    if not user_store.delete(username):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    return {"status": "success"}

# Initialisation du Swarm
swarm = Swarm("agents.yaml")


def _orch_name() -> str:
    """Nom de l'orchestrateur (renommable via agents.yaml ; défaut 'Jarvis')."""
    return getattr(swarm, "orchestrator_name", None) or "Jarvis"


def _app_name() -> str:
    """Nom de l'application (branding), pour tout texte visible par l'utilisateur
    (notifications, messages Telegram…). Suit APP_NAME, sinon le nom de l'orchestrateur."""
    return os.getenv("APP_NAME", "").strip() or _orch_name()


def _orch_agent():
    """Renvoie l'agent orchestrateur, avec repli sur le 1er agent disponible."""
    a = swarm.agents.get(_orch_name())
    if a is None and swarm.agents:
        a = next(iter(swarm.agents.values()))
    return a


# Démarrage des serveurs MCP configurés (no-op si mcp_servers.json absent).
try:
    from tools.mcp_manager import mcp_manager
    mcp_manager.start()
except Exception as _e:
    print(f"[MCP] Démarrage ignoré : {_e}")

# Gestionnaire de conversations persistantes
class ConversationManager:
    def __init__(self, filepath=None):
        # Chemin configurable : variable d'env CONVERSATIONS_PATH, sinon
        # conversations.json à la racine du projet (chemin du présent fichier).
        if filepath is None:
            filepath = os.environ.get("CONVERSATIONS_PATH", "").strip() or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "conversations.json"
            )
        self.filepath = filepath
        self.conversations = {} # id -> {"name": str, "messages": list, "active_node_id": str, "active_agent": str}
        self.active_id = "default"
        self._save_lock = threading.Lock()
        self.load()
        
    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.conversations = json.load(f)
            except Exception as e:
                print(f"Error loading conversations: {e}")
                self.conversations = {}
        if "default" not in self.conversations:
            self.conversations["default"] = {
                "name": "Discussion principale",
                "messages": [],
                "active_node_id": None,
                "active_agent": _orch_name()
            }
            
    def save(self):
        # Écriture ATOMIQUE et VERROUILLÉE : on écrit dans un fichier temporaire du
        # même répertoire puis on le bascule via os.replace (atomique). Un crash ou
        # deux sauvegardes concurrentes ne peuvent plus tronquer/corrompre le JSON.
        try:
            with self._save_lock:
                directory = os.path.dirname(os.path.abspath(self.filepath)) or "."
                os.makedirs(directory, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix=".conv-", suffix=".tmp", dir=directory)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(self.conversations, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self.filepath)
                except Exception:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise
        except Exception as e:
            print(f"Error saving conversations: {e}")
            
    def new_conversation(self, name=None):
        import uuid
        conv_id = uuid.uuid4().hex[:8]
        if not name:
            name = f"Discussion {len(self.conversations) + 1}"
        self.conversations[conv_id] = {
            "name": name,
            "messages": [],
            "active_node_id": None,
            "active_agent": _orch_name()
        }
        self.active_id = conv_id
        self.save()
        return conv_id
        
    def delete_conversation(self, conv_id):
        if conv_id in self.conversations:
            del self.conversations[conv_id]
            if not self.conversations or self.active_id == conv_id:
                self.active_id = "default"
                if "default" not in self.conversations:
                    self.conversations["default"] = {
                        "name": "Discussion principale",
                        "messages": [],
                        "active_node_id": None,
                        "active_agent": _orch_name()
                    }
            self.save()
            
    def get_active(self):
        if self.active_id not in self.conversations:
            self.active_id = "default"
            if "default" not in self.conversations:
                self.conversations["default"] = {
                    "name": "Discussion principale",
                    "messages": [],
                    "active_node_id": None,
                    "active_agent": _orch_name()
                }
        return self.conversations[self.active_id]

def _session_file(client_id: str) -> str:
    """Chemin du fichier de conversations pour un canal/client donné.
    Le canal 'web' conserve le conversations.json historique ; les autres
    canaux (voice, cli, telegram:<id>...) ont leur propre fichier."""
    base = os.environ.get("CONVERSATIONS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "conversations.json"
    )
    if client_id == "web":
        return base
    root, ext = os.path.splitext(base)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", client_id)
    return f"{root}_{safe}{ext or '.json'}"


class ChatSession:
    def __init__(self, client_id: str = "web"):
        self.client_id = client_id
        self.manager = ConversationManager(filepath=_session_file(client_id))

    @property
    def messages(self):
        return self.manager.get_active()["messages"]
        
    @messages.setter
    def messages(self, value):
        self.manager.get_active()["messages"] = value
        self.manager.save()
        
    @property
    def active_node_id(self):
        return self.manager.get_active()["active_node_id"]
        
    @active_node_id.setter
    def active_node_id(self, value):
        self.manager.get_active()["active_node_id"] = value
        self.manager.save()
        
    @property
    def active_agent(self):
        agent_name = self.manager.get_active().get("active_agent", _orch_name())
        return swarm.agents.get(agent_name) or _orch_agent()
        
    @active_agent.setter
    def active_agent(self, agent_obj):
        self.manager.get_active()["active_agent"] = agent_obj.name if agent_obj else _orch_name()
        # Générer un titre de discussion automatique s'il s'agit du premier message
        active_conv = self.manager.get_active()
        if len(active_conv["messages"]) > 0 and active_conv["name"].startswith("Discussion "):
            for msg in active_conv["messages"]:
                if msg["role"] == "user":
                    summary = msg["content"][:25] + "..." if len(msg["content"]) > 25 else msg["content"]
                    active_conv["name"] = summary
                    break
        self.manager.save()
        
    def reset(self):
        active_conv = self.manager.get_active()
        active_conv["messages"] = []
        active_conv["active_node_id"] = None
        active_conv["active_agent"] = _orch_name()
        self.manager.save()

class SessionManager:
    """Sessions par canal/client (web, cli, voice, telegram:<id>...). Chaque
    client a sa propre conversation/agent actif, isolés des autres canaux."""
    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def get(self, client_id: str = "web") -> "ChatSession":
        # Cloisonnement par utilisateur authentifié (no-op en mode local sans auth).
        client_id = _scope_cid(client_id)
        with self._lock:
            if client_id not in self._sessions:
                self._sessions[client_id] = ChatSession(client_id=client_id)
            return self._sessions[client_id]


sessions = SessionManager()


# Rétro-compatibilité : `session` = canal web. Proxy qui résout la session web
# À CHAQUE ACCÈS (et non une fois pour toutes) afin d'appliquer le cloisonnement
# par utilisateur (cf. _scope_cid) aux endpoints utilisant le `session` global.
class _WebSessionProxy:
    def __getattr__(self, name):
        return getattr(sessions.get("web"), name)

    def __setattr__(self, name, value):
        setattr(sessions.get("web"), name, value)


session = _WebSessionProxy()

# Télémétrie en mémoire pour le cockpit de l'essaim
TELEMETRY = {
    "total_queries": 0,
    "tool_calls": 0,
    "total_tokens": 0,
    "total_cost": 0.0
}

# Le suivi temps réel des étapes est désormais isolé PAR RUN dans
# core.run_context.registry (sûr en concurrence : web + Telegram + agents
# parallèles ne s'écrasent plus mutuellement).

# Répertoire de travail du terminal "coder". Remplace os.chdir() (qui mutait le
# cwd de TOUT le process, affectant les threads Telegram/scheduler et provoquant
# des courses entre utilisateurs). Toujours confiné à l'intérieur du workspace.
CODER_CWD = None


def get_coder_cwd() -> str:
    global CODER_CWD
    base = get_workspace_dir()
    if CODER_CWD is None or not os.path.isdir(CODER_CWD):
        CODER_CWD = base
    return CODER_CWD


def set_coder_cwd(target: str) -> str:
    """Change le cwd du terminal coder en restant confiné au workspace.
    Renvoie un message d'erreur, ou une chaîne vide si OK."""
    global CODER_CWD
    base = get_workspace_dir()
    if target in ("", "~"):
        CODER_CWD = base
        return ""
    candidate = os.path.abspath(os.path.join(get_coder_cwd(), os.path.expanduser(target)))
    if os.path.commonpath([candidate, base]) != base:
        return f"cd: accès interdit hors du workspace : {target}"
    if not os.path.isdir(candidate):
        return f"cd: {target}: répertoire introuvable"
    CODER_CWD = candidate
    return ""

def get_model_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    try:
        # Vérifier si l'utilisateur utilise un endpoint LLM privé/local (gratuit)
        env_vars = parse_env()
        custom_base = env_vars.get("CUSTOM_LLM_API_BASE")
        if custom_base:
            # Si le modèle est redirigé vers l'endpoint privé car aucune clé officielle n'est configurée, c'est gratuit (0.0)
            has_official_key = False
            model_lower = model_name.lower()
            if "gpt-" in model_lower or "text-davinci" in model_lower:
                has_official_key = bool(env_vars.get("OPENAI_API_KEY"))
            elif "claude" in model_lower:
                has_official_key = bool(env_vars.get("ANTHROPIC_API_KEY"))
            elif "gemini" in model_lower:
                has_official_key = bool(env_vars.get("GEMINI_API_KEY"))
            elif "qwen" in model_lower:
                has_official_key = bool(env_vars.get("QWEN_API_KEY") or env_vars.get("DASHSCOPE_API_KEY"))
            elif "deepseek" in model_lower:
                has_official_key = bool(env_vars.get("DEEPSEEK_API_KEY"))
            
            # Si aucune clé officielle n'existe, ou si c'est le modèle qwen3 par défaut redirigé, le coût est gratuit (0.0)
            if not has_official_key or model_lower in ["qwen3", "custom-model"]:
                return 0.0

        pricing_path = "workspace/pricing_config.json"
        if not os.path.exists(pricing_path):
            return 0.0
        with open(pricing_path, "r", encoding="utf-8") as f:
            pricing = json.load(f)
            
        def _norm(m: str) -> str:
            # Ignore le préfixe fournisseur (openai/, custom_openai/, anthropic/, ...)
            return m.lower().split("/")[-1].strip()

        matched = None
        # 1. Correspondance exacte
        if model_name in pricing:
            matched = pricing[model_name]
        else:
            # 2. Correspondance normalisée (sans préfixe fournisseur)
            target = _norm(model_name)
            norm_index = {_norm(k): v for k, v in pricing.items() if k != "default"}
            if target in norm_index:
                matched = norm_index[target]
            else:
                # 3. Repli : inclusion mutuelle sur les noms normalisés
                for k_norm, v in norm_index.items():
                    if k_norm and (k_norm in target or target in k_norm):
                        matched = v
                        break
        if not matched:
            matched = pricing.get("default", {"input_cost_per_million": 0.50, "output_cost_per_million": 1.50})
            
        in_cost = (prompt_tokens / 1_000_000.0) * matched.get("input_cost_per_million", 0.50)
        out_cost = (completion_tokens / 1_000_000.0) * matched.get("output_cost_per_million", 1.50)
        return in_cost + out_cost
    except Exception as e:
        print(f"[Pricing Error] {e}")
        return 0.0

class ChatRequest(BaseModel):
    message: str
    parent_id: str = None
    client_id: str = "web"  # canal/session : web (défaut), cli, voice, ...

class ChatResponse(BaseModel):
    agent: str
    response: str
    steps: List[Dict[str, Any]]

def _resolve_starting_agent(sess, req):
    """Agent de départ : actif de session, ou ciblé par une mention @agent."""
    starting_agent = sess.active_agent or _orch_agent()
    last_user_content = req.message.strip().lower()
    if not last_user_content:
        return starting_agent
    first_mention_idx = len(last_user_content)
    mentioned_agent = None
    for name, agent in swarm.agents.items():
        aliases = [name.lower()]
        if agent.display_name:
            aliases.extend([p.lower() for p in agent.display_name.split() if len(p) > 2])
        if name == "CommunityManager":
            aliases.extend(["cm", "communitymanager", "lucas"])
        elif name == "Auteur":
            aliases.extend(["emilie", "éamilie", "auteur"])
        elif name == "Correcteur":
            aliases.extend(["marc", "correcteur"])
        elif name == "Codeur":
            aliases.extend(["robert", "codeur"])
        elif name == "Traducteur":
            aliases.extend(["sofia", "traducteur"])
        import re as _re
        for alias in aliases:
            # On accepte « @correcteur » MAIS aussi le nom seul comme MOT entier
            # (« demande au correcteur… ») → l'agent nommé prend la main directement.
            m = _re.search(r"@?\b" + _re.escape(alias) + r"\b", last_user_content)
            if m and m.start() < first_mention_idx:
                first_mention_idx = m.start()
                mentioned_agent = agent
    if mentioned_agent:
        return mentioned_agent
    if any(last_user_content.startswith(x) for x in ["bonjour jarvis", "jarvis,", "dis jarvis", "hey jarvis", "salut jarvis"]):
        return _orch_agent()
    return starting_agent


def _chat_prepare(sess, req, run_id):
    """Ajoute le message utilisateur, reconstruit la chaîne et choisit l'agent.
    Renvoie (chain, starting_agent, original_chain_len)."""
    parent_id = req.parent_id if req.parent_id is not None else sess.active_node_id
    user_msg_id = uuid.uuid4().hex
    sess.messages.append({"id": user_msg_id, "parent_id": parent_id, "role": "user", "content": req.message})
    sess.active_node_id = user_msg_id

    chain = []
    curr_id = sess.active_node_id
    # Tolérant aux messages legacy sans 'id' (sinon KeyError casse tout le chat).
    node_map = {m["id"]: m for m in sess.messages if m.get("id")}
    while curr_id:
        node = node_map.get(curr_id)
        if not node:
            break
        chain.insert(0, {k: v for k, v in node.items() if k not in ["id", "parent_id"]})
        curr_id = node["parent_id"]

    starting_agent = _resolve_starting_agent(sess, req)
    run_registry.append_step(run_id, {"type": "activation", "agent": starting_agent.name})
    return chain, starting_agent, len(chain)


def _chat_finalize(sess, req, run_id, run_started, new_chain, steps, original_chain_len):
    """Persiste les nouveaux nœuds, calcule la télémétrie et sauvegarde le run.
    Renvoie (final_response, run_agent)."""
    global TELEMETRY
    sess.active_agent = _orch_agent()
    prev_id = sess.active_node_id
    for msg in new_chain[original_chain_len:]:
        new_id = uuid.uuid4().hex
        sess.messages.append({"id": new_id, "parent_id": prev_id, **msg})
        prev_id = new_id
    sess.active_node_id = prev_id

    final_response = ""
    for step in reversed(steps):
        if step["type"] == "message":
            final_response = step["content"]
            break
    if not final_response:
        final_response = "Tâche traitée en arrière-plan sans réponse formulée."

    total_tokens_in_turn = 0
    total_cost_in_turn = 0.0
    for step in steps:
        if step.get("type") == "tool_call":
            TELEMETRY["tool_calls"] += 1
        elif step.get("type") == "usage":
            p_tok = step.get("prompt_tokens", 0)
            c_tok = step.get("completion_tokens", 0)
            total_tokens_in_turn += p_tok + c_tok
            total_cost_in_turn += get_model_cost(step.get("model", "default"), p_tok, c_tok)
    if total_tokens_in_turn == 0:
        total_tokens_in_turn = (len(req.message) + len(final_response)) // 4 + 800
        total_cost_in_turn = get_model_cost("default", total_tokens_in_turn, 0)
    TELEMETRY["total_tokens"] += total_tokens_in_turn
    TELEMETRY["total_cost"] += total_cost_in_turn

    run_agent = sess.active_agent.name if sess.active_agent else _orch_name()
    run_store.save(
        run_id=run_id, agent=run_agent, status="success",
        user_message=req.message, final_response=final_response,
        duration_ms=int((time.time() - run_started) * 1000),
        total_tokens=total_tokens_in_turn, total_cost=total_cost_in_turn,
        steps=steps, created_at=run_started,
    )
    logger.info("run %s ok | agent=%s tokens=%s coût=%.4f", run_id, run_agent,
                total_tokens_in_turn, total_cost_in_turn)
    _check_budget()
    return final_response, run_agent


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    global TELEMETRY
    TELEMETRY["total_queries"] += 1
    run_id = run_store.new_run_id()
    run_started = time.time()
    run_registry.start(run_id)
    token = current_run_id.set(run_id)
    chan_token = channels.current_channel.set(req.client_id)
    appr_token = approvals.auto_approve_var.set(channels.auto_approve_for(req.client_id))
    sess = sessions.get(req.client_id)
    try:
        if not sess.active_agent:
            raise HTTPException(status_code=500, detail=f"{_app_name()} n'est pas initialisé.")
        chain, starting_agent, original_chain_len = _chat_prepare(sess, req, run_id)
        # swarm.run est bloquant : exécuté dans un thread (contexte copié) pour
        # ne pas bloquer la boucle asyncio (concurrence des requêtes).
        _next, new_chain, steps = await asyncio.to_thread(swarm.run, starting_agent, chain)
        final_response, run_agent = _chat_finalize(sess, req, run_id, run_started, new_chain, steps, original_chain_len)
        return ChatResponse(agent=run_agent, response=final_response, steps=steps)
    except Exception as e:
        logger.exception("Erreur Chat (run %s)", run_id)
        run_store.save(
            run_id=run_id, agent=_orch_name(), status="error",
            user_message=req.message, error=str(e),
            duration_ms=int((time.time() - run_started) * 1000),
            steps=run_registry.status(run_id)["steps"], created_at=run_started,
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        run_registry.finish(run_id)
        current_run_id.reset(token)
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)


# =========================================================================
# INTÉGRATION : sorties structurées (JSON) & exécution asynchrone (callbacks)
# Pour piloter Athena depuis n8n/Zapier/Make ou tout pipeline automatisé.
# =========================================================================

def _extract_json(text: str):
    """Extrait le premier objet/tableau JSON équilibré d'un texte (tolère le bavardage
    et les blocs ```json). Renvoie (obj, None) ou (None, raison)."""
    if not text:
        return None, "réponse vide"
    s = text.strip()
    # Retirer une éventuelle clôture ```json … ```
    fence = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    start = next((i for i, c in enumerate(s) if c in "{["), -1)
    if start < 0:
        return None, "aucun JSON détecté"
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1]), None
                except Exception as e:
                    return None, f"JSON invalide ({e})"
    return None, "JSON non terminé"


def _run_swarm_ephemeral(message: str):
    """Exécute l'essaim sur un message UNIQUE sans persister de conversation
    (pour les appels d'intégration). Renvoie (réponse_texte, agent, steps)."""
    run_id = run_store.new_run_id()
    run_started = time.time()
    run_registry.start(run_id)
    token = current_run_id.set(run_id)
    chan_token = channels.current_channel.set("api")
    appr_token = approvals.auto_approve_var.set(channels.auto_approve_for("api"))
    try:
        chain = [{"role": "user", "content": message, "id": uuid.uuid4().hex[:8]}]
        starting = _orch_agent()
        _next, new_chain, steps = swarm.run(starting, chain)
        # Dernière réponse d'assistant.
        final = ""
        agent = _orch_name()
        for m in reversed(new_chain):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                final = m["content"].strip()
                agent = m.get("name") or agent
                break
        run_store.save(run_id=run_id, agent=agent, status="success",
                       user_message=message, final_response=final,
                       duration_ms=int((time.time() - run_started) * 1000),
                       steps=steps, created_at=run_started)
        return final, agent, steps
    finally:
        run_registry.finish(run_id)
        current_run_id.reset(token)
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)


class StructuredRequest(BaseModel):
    # alias "schema" côté JSON (n8n-friendly), attribut Python "output_schema"
    # pour ne pas masquer BaseModel.schema.
    model_config = {"populate_by_name": True}
    message: str
    output_schema: Dict[str, Any] = Field(default=None, alias="schema")


@app.post("/api/structured")
async def chat_structured(req: StructuredRequest):
    """Renvoie une réponse JSON STRICTE (validée par schéma si fourni), pour intégration
    n8n/Zapier. Exécute l'essaim (outils compris) puis extrait/valide le JSON, avec une
    relance corrective si nécessaire. Réponse : {data, raw, agent, valid}."""
    schema = req.output_schema
    instruct = ("\n\nRÉPONDS UNIQUEMENT par un objet JSON valide, sans texte autour, "
                "sans bloc de code.")
    if schema:
        instruct += " Le JSON doit respecter ce schéma JSON :\n" + json.dumps(schema, ensure_ascii=False)
    prompt = req.message + instruct

    last_err = None
    for attempt in range(2):
        text, agent, _steps = await asyncio.to_thread(_run_swarm_ephemeral, prompt)
        obj, err = _extract_json(text)
        if obj is not None and schema:
            try:
                import jsonschema
                jsonschema.validate(obj, schema)
            except Exception as ve:
                err = f"non conforme au schéma : {ve}".split("\n")[0]
                obj = None
        if obj is not None:
            return {"data": obj, "raw": text, "agent": agent, "valid": True}
        last_err = err
        prompt = (req.message + instruct +
                  f"\n\n⚠️ Ta réponse précédente était invalide ({err}). Renvoie UNIQUEMENT "
                  "le JSON corrigé.")
    raise HTTPException(status_code=422, detail=f"Sortie JSON invalide après 2 tentatives : {last_err}")


ASYNC_TASKS = {}  # task_id -> {status, result, error, created}
_ASYNC_LOCK = threading.Lock()


class AsyncChatRequest(BaseModel):
    message: str
    callback_url: str = None
    client_id: str = "web"
    structured_schema: Dict[str, Any] = None


def _async_worker(task_id: str, req_message: str, client_id: str, callback_url: str, schema):
    result = None
    error = None
    try:
        if schema is not None:
            text, agent, _ = _run_swarm_ephemeral(
                req_message + "\n\nRÉPONDS UNIQUEMENT par un objet JSON valide."
                + (" Schéma : " + json.dumps(schema, ensure_ascii=False) if schema else ""))
            obj, _err = _extract_json(text)
            result = {"agent": agent, "data": obj, "raw": text}
        else:
            # Conversation persistante normale.
            run_id = run_store.new_run_id()
            run_started = time.time()
            run_registry.start(run_id)
            t = current_run_id.set(run_id)
            ch = channels.current_channel.set(client_id)
            ap = approvals.auto_approve_var.set(channels.auto_approve_for(client_id))
            try:
                req = ChatRequest(message=req_message, client_id=client_id)
                sess = sessions.get(client_id)
                chain, starting, orig = _chat_prepare(sess, req, run_id)
                _n, new_chain, steps = swarm.run(starting, chain)
                final, agent = _chat_finalize(sess, req, run_id, run_started, new_chain, steps, orig)
                result = {"agent": agent, "response": final, "steps": steps}
            finally:
                run_registry.finish(run_id)
                current_run_id.reset(t)
                channels.current_channel.reset(ch)
                approvals.auto_approve_var.reset(ap)
    except Exception as e:
        error = str(e)
        logger.exception("Tâche async %s en échec", task_id)

    with _ASYNC_LOCK:
        ASYNC_TASKS[task_id] = {"status": "error" if error else "done",
                                "result": result, "error": error, "created": time.time()}
        # Purge basique des vieilles tâches.
        if len(ASYNC_TASKS) > 200:
            for k in sorted(ASYNC_TASKS, key=lambda k: ASYNC_TASKS[k]["created"])[:50]:
                ASYNC_TASKS.pop(k, None)

    if callback_url:
        try:
            import requests as _rq
            payload = {"task_id": task_id, "status": "error" if error else "done",
                       "result": result, "error": error}
            _rq.post(callback_url, json=payload, timeout=20)
        except Exception as e:
            logger.warning("Callback %s échoué (%s)", callback_url, e)


@app.post("/api/chat/async")
async def chat_async(req: AsyncChatRequest):
    """Lance une tâche EN ARRIÈRE-PLAN et renvoie immédiatement un task_id (évite les
    timeouts n8n sur les tâches longues). Si callback_url est fourni, le résultat y est
    POSTé en JSON une fois terminé ; sinon, interroger GET /api/chat/async/{task_id}."""
    task_id = uuid.uuid4().hex[:16]
    with _ASYNC_LOCK:
        ASYNC_TASKS[task_id] = {"status": "running", "result": None, "error": None, "created": time.time()}
    threading.Thread(
        target=_async_worker,
        args=(task_id, req.message, req.client_id, req.callback_url, req.structured_schema),
        daemon=True,
    ).start()
    return {"task_id": task_id, "status": "accepted"}


@app.get("/api/chat/async/{task_id}")
async def chat_async_status(task_id: str):
    with _ASYNC_LOCK:
        task = ASYNC_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche inconnue ou expirée.")
    return {"task_id": task_id, **task}


# --- Plan d'action persistant & éditable par l'humain ----------------------
class PlanSetRequest(BaseModel):
    client_id: str = "web"
    items: List[Any] = []  # str ou {text, status} — normalisé par plan_store.set_plan


class PlanStepRequest(BaseModel):
    client_id: str = "web"
    op: str                      # set_status | add | edit | delete
    index: int = -1
    text: str = ""
    status: str = "done"


@app.get("/api/plan")
async def api_get_plan(client_id: str = "web"):
    from core import plan_store
    return {"items": plan_store.get_plan(client_id)}


@app.post("/api/plan")
async def api_set_plan(req: PlanSetRequest):
    from core import plan_store
    items = plan_store.set_plan(req.client_id, req.items)
    return {"status": "success", "items": items}


@app.post("/api/plan/step")
async def api_plan_step(req: PlanStepRequest):
    from core import plan_store
    op = (req.op or "").strip().lower()
    ok = False
    if op == "set_status":
        ok = plan_store.update_step(req.client_id, req.index, req.status)
    elif op == "add":
        ok = plan_store.add_step(req.client_id, req.text)
    elif op == "edit":
        ok = plan_store.edit_step(req.client_id, req.index, req.text)
    elif op == "delete":
        ok = plan_store.remove_step(req.client_id, req.index)
    else:
        raise HTTPException(status_code=400, detail="op invalide (set_status|add|edit|delete).")
    if not ok:
        raise HTTPException(status_code=400, detail="Opération refusée (index hors limites ou texte vide).")
    return {"status": "success", "items": plan_store.get_plan(req.client_id)}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming SSE : diffuse les étapes de l'essaim au fil de l'eau (events
    'step'), puis un event 'done' avec la réponse finale. Idéal pour la latence
    vocale (TTS au fil des messages) et l'affichage progressif côté UI."""
    global TELEMETRY
    TELEMETRY["total_queries"] += 1
    run_id = run_store.new_run_id()
    run_started = time.time()
    run_registry.start(run_id)
    sess = sessions.get(req.client_id)

    async def gen():
        token = current_run_id.set(run_id)
        chan_token = channels.current_channel.set(req.client_id)
        appr_token = approvals.auto_approve_var.set(channels.auto_approve_for(req.client_id))
        try:
            if not sess.active_agent:
                yield _sse("error", {"detail": f"{_app_name()} n'est pas initialisé."})
                return
            chain, starting_agent, original_chain_len = _chat_prepare(sess, req, run_id)

            # Exécuter swarm.run dans un thread en propageant le contexte
            # (run_id + canal + auto_approve).
            ctx = contextvars.copy_context()
            holder = {}

            def _work():
                holder["result"] = swarm.run(starting_agent, chain)

            loop = asyncio.get_event_loop()
            fut = loop.run_in_executor(None, lambda: ctx.run(_work))

            yield _sse("run", {"run_id": run_id, "agent": starting_agent.name})
            sent = 0
            while True:
                live = run_registry.status(run_id)["steps"]
                while sent < len(live):
                    yield _sse("step", live[sent])
                    sent += 1
                if fut.done():
                    break
                await asyncio.sleep(0.08)
            # Drain des dernières étapes + propagation d'une éventuelle exception.
            live = run_registry.status(run_id)["steps"]
            while sent < len(live):
                yield _sse("step", live[sent])
                sent += 1
            exc = fut.exception()
            if exc:
                raise exc

            _next, new_chain, steps = holder["result"]
            final_response, run_agent = _chat_finalize(sess, req, run_id, run_started, new_chain, steps, original_chain_len)
            yield _sse("done", {"agent": run_agent, "response": final_response})
        except Exception as e:
            logger.exception("Erreur Chat stream (run %s)", run_id)
            run_store.save(
                run_id=run_id, agent=_orch_name(), status="error",
                user_message=req.message, error=str(e),
                duration_ms=int((time.time() - run_started) * 1000),
                steps=run_registry.status(run_id)["steps"], created_at=run_started,
            )
            yield _sse("error", {"detail": str(e)})
        finally:
            run_registry.finish(run_id)
            current_run_id.reset(token)
            channels.current_channel.reset(chan_token)
            approvals.auto_approve_var.reset(appr_token)

    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/api/chat/status")
async def get_chat_status(run_id: str = None):
    # Sans run_id : renvoie le dernier run (compat. frontend mono-session).
    # Avec run_id : statut/étapes de ce run précis (utile en concurrence).
    return run_registry.status(run_id)


class ClientReq(BaseModel):
    client_id: str = "web"


@app.post("/api/chat/undo")
async def chat_undo(req: ClientReq):
    """Annule le dernier échange : retire la dernière réponse (et outils) + la question."""
    sess = sessions.get(req.client_id)
    msgs = sess.messages
    while msgs and msgs[-1].get("role") in ("assistant", "tool"):
        msgs.pop()
    removed_user = None
    if msgs and msgs[-1].get("role") == "user":
        removed_user = msgs.pop().get("content")
    sess.messages = msgs  # déclenche la sauvegarde
    # IMPORTANT : recaler le pointeur d'arbre, sinon il pointe vers un nœud supprimé
    # et le chat se redessine VIDE.
    ids = [m.get("id") for m in msgs if m.get("id")]
    sess.active_node_id = ids[-1] if ids else None
    return {"status": "success", "removed_user": removed_user, "remaining": len(msgs)}


@app.post("/api/chat/retry")
async def chat_retry(req: ClientReq):
    """Réessaie : retire la dernière réponse ET la dernière question, et renvoie cette
    question pour que le client la rejoue via /api/chat/stream (réponse régénérée)."""
    sess = sessions.get(req.client_id)
    msgs = sess.messages
    while msgs and msgs[-1].get("role") in ("assistant", "tool"):
        msgs.pop()
    last_user = None
    if msgs and msgs[-1].get("role") == "user":
        last_user = msgs.pop().get("content")
    sess.messages = msgs
    ids = [m.get("id") for m in msgs if m.get("id")]
    sess.active_node_id = ids[-1] if ids else None
    return {"status": "success", "user": last_user}


@app.get("/api/sessions/search")
async def sessions_search(q: str, client_id: str = "web"):
    """Recherche plein-texte dans les conversations enregistrées (rappel inter-sessions)."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "count": 0, "results": []}
    sess = sessions.get(client_id)
    ql = q.lower()
    results = []
    for cid, c in sess.manager.conversations.items():
        for m in c.get("messages", []):
            content = str(m.get("content", "") or "")
            if ql in content.lower():
                idx = content.lower().find(ql)
                start = max(0, idx - 60)
                results.append({
                    "conversation": c.get("name", cid),
                    "conversation_id": cid,
                    "role": m.get("role", "?"),
                    "snippet": ("…" if start else "") + content[start:idx + len(q) + 100],
                })
    return {"query": q, "count": len(results), "results": results[:50]}


@app.get("/api/doctor")
async def doctor():
    """Auto-diagnostic : config, dépendances et services (équivalent 'hermes doctor')."""
    from core.diagnostics import run_diagnostics
    checks = run_diagnostics(swarm)
    ok_count = sum(1 for c in checks if c["ok"])
    return {"checks": checks, "ok": ok_count, "total": len(checks)}


@app.post("/api/chat/attach")
async def chat_attach(file: UploadFile = File(...)):
    """Reçoit une pièce jointe, l'enregistre dans workspace/uploads/ et en extrait
    le texte (texte/code/PDF, OCR image si dispo) à injecter dans le message."""
    from tools.attachments import extract
    base = os.path.join(get_workspace_dir(), "uploads")
    os.makedirs(base, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(file.filename or "fichier"))
    dest = os.path.join(base, f"{uuid.uuid4().hex[:8]}_{safe}")
    try:
        content = await file.read()
        with open(dest, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enregistrement impossible : {e}")
    info = extract(dest, safe)

    # Vision (opt-in) : si l'image n'a pas donné de texte, la faire décrire par un
    # modèle multimodal. Repli sur la note si désactivé ou en erreur.
    if info["kind"] == "image" and not (info["text"] or "").strip() \
            and os.getenv("VISION_ENABLED", "false").lower() in ("true", "1", "yes"):
        try:
            import base64
            mime = file.content_type or "image/png"
            data_url = f"data:{mime};base64,{base64.b64encode(content).decode()}"
            jarvis = _orch_agent()
            vmodel = os.getenv("VISION_MODEL", "").strip() or (jarvis.model if jarvis else "gpt-4o")
            vmsg = [{"role": "user", "content": [
                {"type": "text", "text": "Décris cette image en détail et retranscris tout texte visible."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}]
            resp = await asyncio.to_thread(swarm._complete, vmodel, vmsg, None, False)
            desc = (resp.choices[0].message.content or "").strip()
            if desc:
                info["text"] = desc
                info["note"] = "Analyse visuelle par le modèle."
        except Exception as e:
            info["note"] = (info.get("note", "") + f" (vision indisponible : {e})").strip()

    return {
        "filename": safe,
        "kind": info["kind"],
        "text": info["text"],
        "truncated": info["truncated"],
        "note": info["note"],
        "path": os.path.relpath(dest, get_workspace_dir()),
    }

@app.get("/api/runs")
async def list_runs(limit: int = 50, status: str = None):
    """Liste les derniers runs persistés (résumés) pour le cockpit / debug."""
    return {"runs": run_store.list(limit=limit, status=status)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Détail complet d'un run (étapes incluses) pour inspection/rejeu."""
    run = run_store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run introuvable.")
    return run


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: str):
    """Demande l'annulation d'un run en cours (barge-in vocal / bouton stop).
    L'arrêt est effectif au prochain tour de l'essaim."""
    ok = run_registry.cancel(run_id)
    return {"run_id": run_id, "cancellation_requested": ok}


@app.post("/api/runs/{run_id}/replay")
async def replay_run_endpoint(run_id: str):
    """Rejoue le message d'un run et renvoie la comparaison ancien/nouveau."""
    from core.eval import replay_run
    result = await asyncio.to_thread(replay_run, swarm, run_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/chat/tree")
async def get_chat_tree():
    return {
        "messages": session.messages,
        "active_node_id": session.active_node_id,
        "active_agent": session.active_agent.name if session.active_agent else _orch_name()
    }

@app.get("/api/conversations")
async def list_conversations():
    return {
        "conversations": [
            {"id": cid, "name": c["name"], "active": cid == session.manager.active_id}
            for cid, c in session.manager.conversations.items()
        ],
        "active_id": session.manager.active_id
    }

class SelectConvRequest(BaseModel):
    id: str

@app.post("/api/conversations/select")
async def select_conversation(req: SelectConvRequest):
    if req.id in session.manager.conversations:
        session.manager.active_id = req.id
        session.manager.save()
        return {"status": "success", "active_id": session.manager.active_id}
    raise HTTPException(status_code=404, detail="Conversation not found")

class NewConvRequest(BaseModel):
    name: str = None

@app.post("/api/conversations/new")
async def create_conversation(req: NewConvRequest = None):
    name = req.name if req else None
    cid = session.manager.new_conversation(name)
    return {"status": "success", "id": cid, "name": session.manager.conversations[cid]["name"]}

@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    session.manager.delete_conversation(conv_id)
    return {"status": "success", "active_id": session.manager.active_id}

class ForkRequest(BaseModel):
    message_id: str

@app.post("/api/chat/fork")
async def fork_chat(req: ForkRequest):
    node_map = {m["id"]: m for m in session.messages if m.get("id")}
    if req.message_id not in node_map:
        raise HTTPException(status_code=404, detail="Checkpoint non trouvé.")
        
    session.active_node_id = req.message_id
    
    # Retrouver intelligemment quel agent était actif à ce moment précis de l'historique
    active_agent_name = _orch_name()
    curr_id = req.message_id
    while curr_id:
        node = node_map.get(curr_id)
        if not node:
            break
        if node.get("role") == "assistant" and node.get("name"):
            active_agent_name = node["name"]
            break
        curr_id = node.get("parent_id")
        
    # Mettre à jour l'agent actif de la session
    session.active_agent = swarm.agents.get(active_agent_name, _orch_agent())
    
    return {
        "status": "success",
        "active_node_id": session.active_node_id,
        "active_agent": active_agent_name,
        "message": f"Curseur actif déplacé sur {req.message_id}. Agent synchronisé sur {active_agent_name}."
    }

class TerminalRequest(BaseModel):
    command: str

@app.post("/api/terminal/coder")
async def terminal_coder(req: TerminalRequest):
    if not session.active_agent:
        raise HTTPException(status_code=500, detail=f"{_app_name()} n'est pas initialisé.")
        
    coder_agent = swarm.agents.get("Codeur")
    if not coder_agent:
        raise HTTPException(status_code=404, detail="Agent Codeur introuvable.")
        
    # Reconstruire la chaîne linéaire de messages existante pour donner le contexte à l'IA
    chain = []
    curr_id = session.active_node_id
    node_map = {m["id"]: m for m in session.messages if m.get("id")}
    while curr_id:
        node = node_map.get(curr_id)
        if not node:
            break
        standard_msg = {k: v for k, v in node.items() if k not in ["id", "parent_id"]}
        chain.insert(0, standard_msg)
        curr_id = node["parent_id"]
        
    # Détecter si la commande doit être exécutée directement dans le shell système
    import subprocess
    import os
    
    cmd_stripped = req.command.strip()
    is_direct_bash = False
    raw_bash_cmd = ""
    
    if cmd_stripped.startswith("$"):
        is_direct_bash = True
        raw_bash_cmd = cmd_stripped[1:].strip()
    elif cmd_stripped.startswith("!"):
        is_direct_bash = True
        raw_bash_cmd = cmd_stripped[1:].strip()
    elif cmd_stripped.startswith("/"):
        is_direct_bash = True
        if cmd_stripped.startswith("/bash"):
            raw_bash_cmd = cmd_stripped[5:].strip()
        else:
            raw_bash_cmd = cmd_stripped[1:].strip()
    else:
        # Détection automatique pour les commandes de shell courantes (Unix + Windows/PowerShell)
        first_word = cmd_stripped.split()[0].lower() if cmd_stripped.split() else ""
        shell_commands = {
            # Unix / Commandes universelles
            "ls", "pwd", "git", "cd", "mkdir", "rm", "cat", "pip", "python", "python3", 
            "npm", "node", "grep", "find", "whoami", "curl", "wget", "uname", "df", "free", 
            "ps", "top", "lsof", "chmod", "chown", "touch", "cp", "mv", "clear", "env", 
            "echo", "head", "tail", "less", "more", "history", "date", "tar", "zip", "unzip",
            # Windows / PowerShell spécifiques
            "dir", "ipconfig", "ping", "systeminfo", "tasklist", "taskkill", "cls",
            "get-process", "get-service", "get-content", "select-string", "get-item",
            "copy-item", "move-item", "remove-item", "get-childitem", "set-location"
        }
        if first_word in shell_commands:
            is_direct_bash = True
            raw_bash_cmd = cmd_stripped

    if is_direct_bash:
        # 1. Routage SSH si configuré
        if os.getenv("SSH_HOST"):
            from tools.system_tools import run_ssh_command
            
            if raw_bash_cmd.startswith("cd "):
                target_dir = raw_bash_cmd[3:].strip().strip("'\"")
                current_remote_cwd = os.getenv("SSH_REMOTE_CWD")
                # Échappement des chemins (issus d'entrée utilisateur) via shlex.quote.
                if current_remote_cwd:
                    remote_cmd = f"cd {shlex.quote(current_remote_cwd)} && cd {shlex.quote(target_dir)} && pwd"
                else:
                    remote_cmd = f"cd {shlex.quote(target_dir)} && pwd"
                
                stdout_content, stderr_content, rc = run_ssh_command(remote_cmd)
                if rc == 0 and stdout_content.strip():
                    new_remote_path = stdout_content.strip()
                    os.environ["SSH_REMOTE_CWD"] = new_remote_path
                    stdout_content = f"📂 Répertoire distant SSH changé : {new_remote_path}"
                    stderr_content = ""
                else:
                    stdout_content = ""
                    if not stderr_content:
                        stderr_content = f"cd: {target_dir}: Aucun fichier ou dossier de ce type sur l'hôte SSH"
            elif raw_bash_cmd == "cd":
                stdout_content, stderr_content, rc = run_ssh_command("cd ~ && pwd")
                if rc == 0 and stdout_content.strip():
                    new_remote_path = stdout_content.strip()
                    os.environ["SSH_REMOTE_CWD"] = new_remote_path
                    stdout_content = f"📂 Répertoire distant SSH changé : {new_remote_path}"
                    stderr_content = ""
            else:
                stdout_content, stderr_content, rc = run_ssh_command(raw_bash_cmd)
                
        # 2. Exécution locale par défaut
        else:
            if raw_bash_cmd.startswith("cd "):
                target_dir = raw_bash_cmd[3:].strip().strip("'\"")
                # Plus d'os.chdir() global : on suit un cwd dédié, confiné au workspace.
                err = set_coder_cwd(target_dir)
                if err:
                    stdout_content = ""
                    stderr_content = err
                else:
                    stdout_content = f"📂 Répertoire de travail changé : {get_coder_cwd()}"
                    stderr_content = ""
            elif raw_bash_cmd == "cd":
                set_coder_cwd("~")
                stdout_content = f"📂 Répertoire de travail changé : {get_coder_cwd()}"
                stderr_content = ""
            else:
                import sys
                from tools.system_tools import check_command_blacklist
                from tools import sandbox_runner

                # Filtrage de sécurité partagé (mêmes motifs que l'outil bash des agents).
                rejection = check_command_blacklist(raw_bash_cmd)
                if rejection:
                    stdout_content = ""
                    stderr_content = rejection
                else:
                    is_windows = (os.name == "nt" or sys.platform.startswith("win"))
                    try:
                        if is_windows:
                            # Pas de sandbox Docker Linux ici : exécution PowerShell locale filtrée.
                            res = subprocess.run(
                                raw_bash_cmd,
                                shell=True,
                                executable="powershell.exe",
                                text=True,
                                capture_output=True,
                                timeout=30
                            )
                            stdout_content = res.stdout
                            stderr_content = res.stderr
                        elif sandbox_runner.sandbox_mode() != "off" and sandbox_runner.docker_available():
                            # Exécution isolée en conteneur Docker jetable, dans le sous-dossier courant.
                            rel = os.path.relpath(get_coder_cwd(), get_workspace_dir())
                            stdout_content, stderr_content, _rc = sandbox_runner.run_bash(
                                raw_bash_cmd, timeout=30, workdir=rel
                            )
                        else:
                            # Repli local SANS shell=True (argv explicite via /bin/bash -c).
                            res = subprocess.run(
                                ["/bin/bash", "-c", raw_bash_cmd],
                                text=True,
                                capture_output=True,
                                timeout=30,
                                cwd=get_coder_cwd()
                            )
                            stdout_content = res.stdout
                            stderr_content = res.stderr
                    except subprocess.TimeoutExpired:
                        stdout_content = ""
                        stderr_content = "⏳ Erreur : La commande a dépassé le délai d'attente de 30 secondes."
                    except Exception as e:
                        stdout_content = ""
                        stderr_content = str(e)

        # Construire la réponse formatée
        output_block = ""
        if stdout_content:
            output_block += stdout_content
        if stderr_content:
            if output_block:
                output_block += "\n"
            output_block += stderr_content
            
        if not output_block.strip():
            output_block = "(Exécution terminée avec succès, aucun retour standard)"
            
        assistant_content = f"💻 **Exécution Directe du Shell**\n\n```bash\n$ {raw_bash_cmd}\n{output_block}\n```"
        
        # Créer les étapes visuelles pour la console de logs (sans polluer le chat)
        steps = [
            {"type": "activation", "agent": "Codeur"},
            {"type": "tool_call", "agent": "Codeur", "tool": "Direct Shell Execution", "args": {"command": raw_bash_cmd}}
        ]
        
        if stdout_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": "Codeur",
                "output": stdout_content,
                "stream": "stdout"
            })
            
        if stderr_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": "Codeur",
                "output": stderr_content,
                "stream": "stderr"
            })
            
        if not stdout_content and not stderr_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": "Codeur",
                "output": "(Exécution terminée avec succès, aucun retour standard)",
                "stream": "stdout"
            })
            
        return {
            "status": "success",
            "steps": steps,
            "active_node_id": session.active_node_id
        }

    # Sinon, on passe par l'exécution standard de l'Agent Codeur
    # On ajoute la commande de la console localement à la chaîne contextuelle
    chain.append({"role": "user", "content": f"[CLI] {req.command}"})
        
    run_id = run_store.new_run_id()
    run_registry.start(run_id)
    token = current_run_id.set(run_id)
    chan_token = channels.current_channel.set("web")
    appr_token = approvals.auto_approve_var.set(channels.auto_approve_for("web"))
    try:
        # Lancer l'exécution en ciblant directement l'Agent Codeur (dans un thread).
        next_agent, new_chain, steps = await asyncio.to_thread(swarm.run, coder_agent, chain)
        session.active_agent = _orch_agent()

        # Transformer les types "message" en "terminal_message" pour éviter de polluer le chat principal
        for step in steps:
            if step.get("type") == "message":
                step["type"] = "terminal_message"

        return {
            "status": "success",
            "steps": steps,
            "active_node_id": session.active_node_id
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        run_registry.finish(run_id)
        current_run_id.reset(token)
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)

# Endpoints mémoire / connaissances / agenda / listes : extraits en routeurs
# dédiés (Single Responsibility). Voir routers/{memory,agenda,lists}.py.
from routers import memory as _memory_router
from routers import agenda as _agenda_router
from routers import lists as _lists_router
app.include_router(_memory_router.router)
app.include_router(_agenda_router.router)
app.include_router(_lists_router.router)


@app.post("/api/reset")
async def reset_chat():
    session.reset()
    return {"status": "success", "message": "La conversation a été réinitialisée."}

# =========================================================================
# ENDPOINTS D'EXPLORATION DU WORKSPACE (Fichiers du projet)
# =========================================================================
import os

def get_workspace_dir() -> str:
    return os.path.abspath(os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd()))

@app.get("/api/workspace/config")
async def get_workspace_config():
    return {
        "active_workspace_dir": get_workspace_dir(),
        "default_dir": os.getcwd()
    }

class WorkspaceConfigRequest(BaseModel):
    path: str

@app.post("/api/workspace/config")
async def set_workspace_config(req: WorkspaceConfigRequest):
    target_path = os.path.abspath(req.path)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Le dossier cible spécifié n'existe pas.")
    if not os.path.isdir(target_path):
        raise HTTPException(status_code=400, detail="Le chemin cible doit être un dossier.")
        
    os.environ["ACTIVE_WORKSPACE_DIR"] = target_path
    print(f"📁 [Workspace] Changement de répertoire de travail : {target_path}")
    return {
        "status": "success",
        "active_workspace_dir": target_path,
        "message": f"Dossier de travail repositionné sur : {target_path}"
    }

@app.get("/api/workspace/dirs")
async def list_subdirectories(path: str = ""):
    try:
        if not path or path.strip() == "":
            target_path = os.getcwd()
        else:
            target_path = os.path.abspath(path)
            
        if not os.path.exists(target_path) or not os.path.isdir(target_path):
            target_path = os.getcwd()
            
        parent = os.path.dirname(target_path)
        subdirs = []
        try:
            for item in os.listdir(target_path):
                full_item = os.path.join(target_path, item)
                if os.path.isdir(full_item) and not item.startswith(".") and item not in ["node_modules", "venv", ".venv"]:
                    subdirs.append(item)
        except Exception:
            pass
            
        subdirs.sort()
        return {
            "current_path": target_path,
            "parent_path": parent,
            "subdirs": subdirs
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspace/files")
async def list_workspace_files():
    try:
        base_dir = get_workspace_dir()
        ignored_patterns = [".venv", "venv", "__pycache__", ".git", ".gemini", "static", ".env", "node_modules"]
        files = []
        for root, dirs, filenames in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in ignored_patterns and not d.startswith(".")]
            
            for f in filenames:
                if f.startswith("."):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, base_dir)
                
                size_bytes = os.path.getsize(full_path)
                files.append({
                    "name": f,
                    "path": rel_path,
                    "size": size_bytes
                })
        files.sort(key=lambda x: x["path"])
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspace/file")
async def get_workspace_file(path: str):
    try:
        base_dir = get_workspace_dir()
        clean_path = os.path.abspath(os.path.join(base_dir, path))
        # Empêche la traversée de répertoire : un simple startswith laisserait
        # passer un dossier frère partageant le préfixe (ex: base + "_secret").
        if os.path.commonpath([clean_path, base_dir]) != base_dir:
            raise HTTPException(status_code=403, detail="Accès interdit.")
            
        if not os.path.exists(clean_path) or os.path.isdir(clean_path):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
            
        with open(clean_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return {"path": path, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/workspace/download")
async def download_workspace_file(path: str):
    try:
        base_dir = get_workspace_dir()
        clean_path = os.path.abspath(os.path.join(base_dir, path))
        # Empêche la traversée de répertoire : un simple startswith laisserait
        # passer un dossier frère partageant le préfixe (ex: base + "_secret").
        if os.path.commonpath([clean_path, base_dir]) != base_dir:
            raise HTTPException(status_code=403, detail="Accès interdit.")
            
        if not os.path.exists(clean_path) or os.path.isdir(clean_path):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
            
        return FileResponse(
            clean_path,
            media_type="application/octet-stream",
            filename=os.path.basename(clean_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workspace/upload")
async def upload_workspace_file(file: UploadFile = File(...)):
    try:
        base_dir = get_workspace_dir()
        filename = os.path.basename(file.filename)
        if not filename or filename in (".", ".."):
            raise HTTPException(status_code=400, detail="Nom de fichier invalide.")
        dest_path = os.path.join(base_dir, filename)

        # Écriture en flux avec plafond de taille (anti-DoS mémoire/disque).
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "50") or 50)
        max_bytes = max_mb * 1024 * 1024
        written = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    f.close()
                    os.remove(dest_path)
                    raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {max_mb} Mo).")
                f.write(chunk)
            
        # Déclenchement automatique de l'ingestion sémantique intelligente si c'est un document texte ou code
        ext = os.path.splitext(filename)[1].lower()
        ingested = False
        report = ""
        
        # Formats textuels éligibles à la vectorisation RAG intelligente (découpe intelligente)
        if ext in ['.txt', '.md', '.markdown', '.py', '.js', '.json', '.html', '.css', '.csv']:
            try:
                from tools.memory_tools import ingest_file
                relative_path = os.path.join("workspace", filename)
                report = ingest_file(relative_path)
                ingested = True
            except Exception as ing_err:
                report = f"Erreur lors de l'ingestion automatique : {str(ing_err)}"
                print(f"[Ingestion Auto Error] {ing_err}")
                
        return {
            "status": "success", 
            "message": f"Fichier '{filename}' téléversé avec succès !", 
            "path": filename,
            "ingested": ingested,
            "report": report
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================================
# ENDPOINTS D'ADMINISTRATION NO-CODE (Géstion Agents & Clés API)
# =========================================================================
import yaml

@app.get("/api/config/agents")
async def get_config_agents():
    try:
        with open("agents.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("agents", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture de agents.yaml : {str(e)}")

class SaveAgentsRequest(BaseModel):
    agents: List[Dict[str, Any]]

@app.post("/api/config/agents")
async def save_config_agents(req: SaveAgentsRequest):
    try:
        # Garde-fou : l'orchestrateur ne doit jamais être supprimé (sinon plus de
        # routage/délégation). On autorise son RENOMMAGE (via orchestrator: true).
        agents = req.agents or []
        if not agents:
            raise HTTPException(status_code=400, detail="Au moins un agent (l'orchestrateur) est requis.")
        orch = _orch_name()
        names = {a.get("name") for a in agents}
        has_orch = any(a.get("orchestrator") is True for a in agents) or (orch in names)
        if not has_orch:
            raise HTTPException(status_code=400, detail=(
                f"Impossible de supprimer l'orchestrateur « {orch} ». "
                "Pour le renommer, change son nom en gardant « orchestrator: true »."))
        # Enregistrer dans agents.yaml
        with open("agents.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump({"agents": req.agents}, f, allow_unicode=True, sort_keys=False)
            
        # Hot-reload de l'essaim
        swarm.load_agents("agents.yaml")
        
        # Mettre à jour l'agent actif s'il a été supprimé ou renommé
        if session.active_agent.name not in swarm.agents:
            session.active_agent = _orch_agent() or list(swarm.agents.values())[0]
            
        return {"status": "success", "message": "Configuration des agents sauvegardée et rechargée avec succès !"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de agents.yaml : {str(e)}")

@app.get("/api/config/skills")
async def get_config_skills():
    try:
        from core.swarm import load_dynamic_skills
        skills_dict = load_dynamic_skills()
        skills_list = []
        for name, func in skills_dict.items():
            doc = func.__doc__ or "Aucune description fournie."
            skills_list.append({
                "name": name,
                "description": doc.strip()
            })
        return skills_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture des compétences : {str(e)}")


@app.get("/api/backup")
async def backup_download():
    """Télécharge une archive ZIP de tout l'état (conversations, mémoire, runs…)."""
    import datetime
    from core.backup import make_backup
    data = await asyncio.to_thread(make_backup)
    fname = f"jarvis-backup-{datetime.date.today().isoformat()}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/backup/restore")
async def backup_restore(file: UploadFile = File(...)):
    """Restaure l'état depuis une archive ZIP (écrase l'état actuel)."""
    from core.backup import restore_backup
    data = await file.read()
    try:
        res = await asyncio.to_thread(restore_backup, data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restauration impossible : {e}")
    return {"status": "success", **res, "note": "Redémarre le serveur pour recharger entièrement la mémoire."}


@app.get("/api/platform")
async def get_platform():
    """Détection automatique de l'OS hôte et de l'environnement d'exécution."""
    from core.platform_info import get_platform_info, sandbox_active
    info = get_platform_info()
    info["sandbox_active"] = sandbox_active()
    info["app_name"] = os.getenv("APP_NAME", "Jarvis").strip() or "Jarvis"
    return info


@app.get("/api/config/mcp")
async def get_config_mcp():
    """Configuration MCP (JSON brut) + état des serveurs/outils connectés."""
    from tools.mcp_manager import mcp_manager
    path = mcp_manager.config_path
    raw = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    return {"config": raw, "config_path": path, "status": mcp_manager.status()}


class SaveMcpRequest(BaseModel):
    config: str


@app.post("/api/config/mcp")
async def save_config_mcp(req: SaveMcpRequest):
    """Écrit mcp_servers.json et reconnecte les serveurs MCP à chaud."""
    from tools.mcp_manager import mcp_manager
    try:
        parsed = json.loads(req.config) if req.config.strip() else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON invalide : {e}")
    path = mcp_manager.config_path
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Écriture impossible : {e}")
    try:
        await asyncio.to_thread(mcp_manager.restart)
    except Exception as e:
        return {"status": "saved_with_error", "detail": str(e), "mcp": mcp_manager.status()}
    return {"status": "success", "mcp": mcp_manager.status()}


# --- Satellites vocaux ESP32-S3 (ESPHome, sans Home Assistant) ---------------
class SaveSatelliteRequest(BaseModel):
    name: str
    host: str = ""
    port: int = 6053
    encryption_key: str = ""
    password: str = ""
    wake_mode: str = "embedded"
    wake_word: str = "hey_jarvis"


@app.get("/api/config/satellites")
async def get_config_satellites():
    """Liste les satellites configurés (clé masquée) + état de connexion live."""
    from voice import esphome_satellites as es
    sats = es._load_satellites()
    safe = [{
        "name": s.get("name"),
        "host": s.get("host", ""),
        "port": int(s.get("port", 6053)),
        "key_set": bool(s.get("encryption_key") or s.get("password")),
        "wake_mode": s.get("wake_mode", "embedded"),
        "wake_word": s.get("wake_word", "hey_jarvis"),
    } for s in sats]
    return {"satellites": safe, "status": es.manager.status()}


@app.post("/api/config/satellites/genkey")
async def gen_satellite_key():
    """Génère une clé d'API ESPHome (base64) à recopier dans le YAML de l'ESP."""
    from voice import esphome_satellites as es
    return {"key": es.generate_encryption_key()}


@app.post("/api/config/satellites")
async def save_config_satellite(req: SaveSatelliteRequest):
    """Ajoute/met à jour un satellite puis reconnecte le listener."""
    from voice import esphome_satellites as es
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Le nom du satellite est requis.")
    if not req.host.strip():
        raise HTTPException(status_code=400, detail="L'adresse (IP/host) du satellite est requise.")
    try:
        es.upsert_satellite(req.dict())
        await asyncio.to_thread(es.manager.restart)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "satellites": es.manager.status()}


@app.delete("/api/config/satellites/{name}")
async def delete_config_satellite(name: str):
    """Supprime un satellite puis reconnecte le listener."""
    from voice import esphome_satellites as es
    es.delete_satellite(name)
    await asyncio.to_thread(es.manager.restart)
    return {"status": "success", "satellites": es.manager.status()}


@app.get("/api/user-profile")
async def get_user_profile():
    """Profil utilisateur évolutif (texte curé réinjecté dans le prompt)."""
    from core.user_profile import user_profile
    return {"profile": user_profile.get()}


class UserProfileRequest(BaseModel):
    profile: str = ""


@app.post("/api/user-profile")
async def set_user_profile(req: UserProfileRequest):
    """Édition manuelle du profil utilisateur."""
    from core.user_profile import user_profile
    user_profile.set(req.profile or "")
    return {"status": "success", "profile": user_profile.get()}


class VoiceWakeRequest(BaseModel):
    engine: str = "stt"
    word: str = "Athena"


@app.get("/api/config/voice-wake")
async def get_voice_wake():
    """Mot d'activation vocal courant (moteur + mot)."""
    return {"engine": os.getenv("VOICE_WAKE_ENGINE", "stt"),
            "word": os.getenv("VOICE_WAKE_WORD", "Athena")}


@app.post("/api/config/voice-wake")
async def set_voice_wake(req: VoiceWakeRequest):
    """Change le mot d'activation vocal : persiste dans .env, applique À CHAUD
    (os.environ) et reconnecte les satellites pour qu'ils l'utilisent."""
    engine = (req.engine or "stt").strip() or "stt"
    word = (req.word or "Athena").strip() or "Athena"
    try:
        from setup_wizard import set_env_var
        set_env_var("VOICE_WAKE_ENGINE", engine)
        set_env_var("VOICE_WAKE_WORD", word)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Écriture .env impossible : {e}")
    os.environ["VOICE_WAKE_ENGINE"] = engine
    os.environ["VOICE_WAKE_WORD"] = word
    try:
        from voice.esphome_satellites import manager as sat_mgr, _load_satellites
        if _load_satellites():
            await asyncio.to_thread(sat_mgr.restart)
    except Exception:
        pass
    return {"status": "success", "engine": engine, "word": word}


@app.get("/api/config/satellites/sensor-catalog")
async def get_sensor_catalog():
    """Catalogue capteurs + types audio (micro/sortie) proposés dans l'UI (source unique)."""
    from voice import esphome_satellites as es
    return {
        "catalog": es.SENSOR_CATALOG,
        "mic_types": es.MIC_TYPES,
        "speaker_types": es.SPEAKER_TYPES,
        "audio_defaults": es.DEFAULT_AUDIO,
        "activation_modes": es.ACTIVATION_MODES,
        "wake_words": es.WAKE_WORDS,
    }


class SatelliteYamlRequest(BaseModel):
    name: str
    encryption_key: str = ""
    modules: List[Dict[str, Any]] = []
    i2c_sda: str = "GPIO8"
    i2c_scl: str = "GPIO9"
    audio: Dict[str, Any] = {}
    activation: Dict[str, Any] = {}
    custom_yaml: str = ""


@app.post("/api/config/satellites/yaml")
async def gen_satellite_yaml(req: SatelliteYamlRequest):
    """Génère le YAML ESPHome prêt à compiler (voix Jarvis + capteurs + audio + YAML custom)."""
    from voice import esphome_satellites as es
    name = (req.name or "").strip() or "salon"
    key = (req.encryption_key or "").strip()
    # Si la clé n'est pas fournie mais que le satellite existe déjà, réutiliser la sienne.
    if not key:
        existing = next((s for s in es._load_satellites() if s.get("name") == name), None)
        if existing:
            key = (existing.get("encryption_key") or "").strip()
    yaml_text = es.generate_yaml(
        name, key, modules=req.modules,
        i2c_sda=req.i2c_sda, i2c_scl=req.i2c_scl, audio=req.audio,
        activation=req.activation, custom_yaml=req.custom_yaml,
    )
    return {"yaml": yaml_text, "filename": f"jarvis-satellite-{es._slug(name)}.yaml"}


@app.post("/api/config/satellites/connect")
async def connect_satellites():
    """(Re)connecte tous les satellites configurés."""
    from voice import esphome_satellites as es
    await asyncio.to_thread(es.manager.restart)
    return {"status": "success", "satellites": es.manager.status()}


@app.delete("/api/config/skills/{skill_name}")
async def delete_config_skill(skill_name: str):
    """Supprime une compétence permanente (fichier skills/<name>.py)."""
    from tools.skills_manager import delete_skill
    result = delete_skill(skill_name)
    if result.startswith("Erreur"):
        raise HTTPException(status_code=400, detail=result)
    return {"status": "success", "message": result}

def parse_env() -> dict:
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip("'\"")
                    env_vars[k.strip()] = v
    return env_vars

class NotifyTestRequest(BaseModel):
    channel: str = ""


@app.post("/api/notify/test")
async def notify_test(req: NotifyTestRequest):
    """Envoie un message de test sur les messageries (ou un canal précis)."""
    from core.notifications import notify, configured_channels
    ch = (req.channel or "").strip().lower() or None
    sent = notify(f"✅ Test de notification depuis {_app_name()}.", title=f"{_app_name()} — test", channel=ch)
    return {"sent": sent, "configured": configured_channels()}


@app.get("/api/notify/channels")
async def notify_channels():
    """Liste les canaux de messagerie actuellement configurés."""
    from core.notifications import configured_channels
    return {"configured": configured_channels()}


@app.get("/api/telegram/pairing")
async def telegram_pairing_status():
    """État du DM pairing Telegram (demandes en attente, contacts approuvés)."""
    from core import telegram_pairing
    return telegram_pairing.status()


class PairingActionRequest(BaseModel):
    code: str = ""
    chat_id: str = ""


@app.post("/api/telegram/pairing/approve")
async def telegram_pairing_approve(req: PairingActionRequest):
    from core import telegram_pairing
    cid = None
    if req.code:
        cid = telegram_pairing.approve_code(req.code)
    elif req.chat_id:
        telegram_pairing.approve_chat(req.chat_id); cid = req.chat_id
    return {"status": "success" if cid else "not_found", "chat_id": cid, "pairing": telegram_pairing.status()}


@app.post("/api/telegram/pairing/revoke")
async def telegram_pairing_revoke(req: PairingActionRequest):
    from core import telegram_pairing
    ok = telegram_pairing.revoke_chat(req.chat_id) if req.chat_id else False
    return {"status": "success" if ok else "not_found", "pairing": telegram_pairing.status()}


@app.get("/api/config/env")
async def get_config_env():
    raw_env = parse_env()
    masked_env = {}
    for k, v in raw_env.items():
        is_secret = "KEY" in k or "TOKEN" in k or "PASSWORD" in k or "SECRET" in k
        if is_secret:
            if len(v) > 8:
                masked_env[k] = f"{v[:4]}...{v[-4:]}"
            else:
                masked_env[k] = "***" if v else ""
        else:
            masked_env[k] = v
            
    # Assurer que les clés attendues sont toujours retournées
    typical_keys = [
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", 
        "OPENROUTER_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", 
        "DASHSCOPE_API_KEY", "QWEN_API_KEY", "OLLAMA_API_BASE", 
        "CUSTOM_LLM_API_BASE", "CUSTOM_LLM_API_KEY", "TELEGRAM_BOT_TOKEN", "HA_URL", "HA_TOKEN",
        "IMAGE_GENERATOR_PROVIDER", "STABILITY_API_KEY", 
        "CUSTOM_IMAGE_API_BASE", "CUSTOM_IMAGE_API_KEY", 
        "VIDEO_GENERATOR_PROVIDER", "FAL_API_KEY", "REPLICATE_API_TOKEN",
        "CUSTOM_VIDEO_API_BASE", "CUSTOM_VIDEO_API_KEY", "ADMIN_PASSWORD",
        "SSH_HOST", "SSH_PORT", "SSH_USERNAME", "SSH_PASSWORD", "SSH_KEY_PATH",
        # Comportement, sécurité & exécution
        "HOST", "PORT", "ALLOWED_ORIGINS", "ACTIVE_WORKSPACE_DIR",
        "SANDBOX_MODE", "SANDBOX_DOCKER_IMAGE",
        "SELF_IMPROVE", "AUTO_APPROVE_SENSITIVE", "SENSITIVE_TOOLS",
        "LLM_MAX_RETRIES", "SWARM_MAX_SECONDS", "SWARM_MAX_TOKENS", "SWARM_MAX_PARALLEL",
        "MEMORY_MAX_MESSAGES", "MEMORY_KEEP_RECENT", "LOG_LEVEL",
        # Sécurité réseau / sessions
        "SESSION_TTL_HOURS", "TELEGRAM_REQUIRE_PAIRING",
        # Voix expressive
        "VOICE_EMOTION_TAGS", "VOICE_TTS_HTTP_URL", "VOICE_TTS_VOICE",
        # Présence / follow-me (optionnel)
        "PRESENCE_ENTITY",
        # Automatisation n8n (allowlist de workflows, JSON {nom: url})
        "N8N_WORKFLOWS",
        # Orchestration & agents (avancé)
        "DELEGATION_ROUTER", "FAST_MODEL", "FALLBACK_MODELS", "AUTO_CRITIC",
        "USER_MODELING", "SELF_IMPROVE_SKILLS", "TOOL_SCRIPTS", "PROMPT_CACHE",
        "EXPERIENCE_MAX", "DOC_MAX_CHUNKS",
        # Messageries & notifications (canaux de livraison des résultats/alertes)
        "DISCORD_WEBHOOK_URL", "SLACK_WEBHOOK_URL", "NOTIFY_WEBHOOK_URL",
        "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
        "SMTP_FROM", "SMTP_SSL", "NOTIFY_EMAIL_TO",
    ]
    for k in typical_keys:
        if k not in masked_env:
            masked_env[k] = ""
    return masked_env

class SaveEnvRequest(BaseModel):
    env: Dict[str, str]

@app.post("/api/config/env")
async def save_config_env(req: SaveEnvRequest):
    try:
        current_env = parse_env()
        # Ne retenir que les valeurs réellement modifiées (exclut les masquées).
        updates = {}
        for k, v in req.env.items():
            if "..." in v or v == "***" or (not v and k in current_env and current_env[k]):
                continue
            updates[k] = v

        # Mise à jour EN PLACE : on préserve les commentaires et l'ordre du .env.
        lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

        seen = set()
        out = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    out.append(f'{key}="{updates[key]}"')
                    os.environ[key] = updates[key]
                    seen.add(key)
                    continue
            out.append(line)

        new_keys = [k for k in updates if k not in seen]
        if new_keys:
            if out and out[-1].strip():
                out.append("")
            out.append("# --- Ajouté via le dashboard ---")
            for k in new_keys:
                out.append(f'{k}="{updates[k]}"')
                os.environ[k] = updates[k]

        with open(".env", "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")

        return {"status": "success", "message": "Réglages sauvegardés (.env mis à jour à chaud, commentaires préservés)."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'écriture dans le .env : {str(e)}")

# =========================================================================
# ENDPOINTS DE CONFIGURATION DE L'AGENDA EXTERNE (NEW !)
# =========================================================================
class SaveAgendaConfigRequest(BaseModel):
    external_ical_url: str = ""
    google_calendar_id: str = ""
    caldav_url: str = ""
    caldav_username: str = ""
    caldav_password: str = ""

@app.get("/api/config/agenda")
async def get_config_agenda():
    env = parse_env()
    has_google_credentials = os.path.exists("workspace/google_credentials.json")
    
    # Masquer le mot de passe CalDAV pour la sécurité à l'affichage
    caldav_pwd = env.get("CALDAV_PASSWORD", "")
    masked_caldav_pwd = ""
    if caldav_pwd:
        masked_caldav_pwd = f"{caldav_pwd[:2]}...{caldav_pwd[-2:]}" if len(caldav_pwd) > 4 else "***"
        
    return {
        "external_ical_url": env.get("EXTERNAL_ICAL_URL", ""),
        "google_calendar_id": env.get("GOOGLE_CALENDAR_ID", ""),
        "caldav_url": env.get("CALDAV_URL", ""),
        "caldav_username": env.get("CALDAV_USERNAME", ""),
        "caldav_password": masked_caldav_pwd,
        "has_google_credentials": has_google_credentials
    }

@app.post("/api/config/agenda")
async def save_config_agenda(req: SaveAgendaConfigRequest):
    try:
        current_env = parse_env()
        
        # Enregistrer et mettre à chaud les variables d'environnement d'agenda
        current_env["EXTERNAL_ICAL_URL"] = req.external_ical_url
        current_env["GOOGLE_CALENDAR_ID"] = req.google_calendar_id
        current_env["CALDAV_URL"] = req.caldav_url
        current_env["CALDAV_USERNAME"] = req.caldav_username
        
        # Ne mettre à jour le mot de passe CalDAV que s'il a été changé et n'est pas masqué
        if req.caldav_password and "..." not in req.caldav_password and req.caldav_password != "***":
            current_env["CALDAV_PASSWORD"] = req.caldav_password
            
        with open(".env", "w", encoding="utf-8") as f:
            f.write("# Configuration de l'essaim Jarvis v2 (Générée via Dashboard)\n")
            for k, v in current_env.items():
                f.write(f'{k}="{v}"\n')
                os.environ[k] = v
                
        # Forcer immédiatement une synchronisation rapide
        from tools.agenda_tools import sync_all_external_calendars
        sync_all_external_calendars()
        
        return {"status": "success", "message": "Paramètres d'agenda et synchronisation à chaud mis à jour avec succès !"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'écriture dans le .env : {str(e)}")

@app.post("/api/config/agenda/google-key")
async def upload_google_key(file: UploadFile = File(...)):
    try:
        os.makedirs("workspace", exist_ok=True)
        content = await file.read()
        
        # Valider que c'est un JSON valide
        json_data = json.loads(content)
        if "client_email" not in json_data or "private_key" not in json_data:
            raise HTTPException(status_code=400, detail="Fichier JSON Google non valide. Propriétés client_email ou private_key manquantes.")
            
        with open("workspace/google_credentials.json", "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4)
            
        # Forcer la synchronisation Google si configuré
        from tools.agenda_tools import sync_all_external_calendars
        sync_all_external_calendars()
        
        return {"status": "success", "message": "Fichier de clé Google Cloud credentials.json téléversé avec succès !"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Le fichier téléversé n'est pas un fichier JSON valide.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur interne : {str(e)}")

@app.post("/api/agenda/sync")
async def force_agenda_sync():
    try:
        from tools.agenda_tools import sync_all_external_calendars
        imported = sync_all_external_calendars()
        return {"status": "success", "message": f"Synchronisation forcée réussie. {imported} événements externes importés."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/telemetry/reset")
async def reset_telemetry():
    """Remet à zéro les compteurs du cockpit (requêtes, outils, tokens, coût)."""
    global TELEMETRY
    TELEMETRY = {"total_queries": 0, "tool_calls": 0, "total_tokens": 0, "total_cost": 0.0}
    return {"status": "success", **TELEMETRY}


@app.get("/api/config/tools")
async def get_config_tools():
    """Tous les outils réellement disponibles (statiques + compétences + MCP) pour la
    checklist par agent — dynamique : tout outil enregistré apparaît automatiquement."""
    from core.swarm import AVAILABLE_TOOLS, load_dynamic_skills
    out = {}

    def add(name, fn, category):
        doc = " ".join((getattr(fn, "__doc__", "") or "").strip().split())
        out[name] = {"key": name, "desc": doc[:140], "category": category}

    for n, fn in AVAILABLE_TOOLS.items():
        add(n, fn, "standard")
    try:
        for n, fn in load_dynamic_skills().items():
            add(n, fn, "competence")
    except Exception:
        pass
    try:
        from tools.mcp_manager import mcp_manager
        for n, fn in mcp_manager.tool_functions().items():
            add(n, fn, "mcp")
    except Exception:
        pass
    return {"tools": sorted(out.values(), key=lambda t: t["key"])}


@app.get("/api/telemetry")
async def get_telemetry():
    try:
        env = parse_env()
        # Vérification Google Calendar credentials
        has_google = os.path.exists("workspace/google_credentials.json")
        
        # Vérification CalDAV credentials
        has_caldav = False
        agenda_config_path = "workspace/agenda_config.json"
        if os.path.exists(agenda_config_path):
            try:
                with open(agenda_config_path, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    if c.get("caldav_url"):
                        has_caldav = True
            except Exception:
                pass
                
        # Vérification Home Assistant
        has_ha = bool(env.get("HA_URL") and env.get("HA_TOKEN"))
        
        return {
            "total_queries": TELEMETRY["total_queries"],
            "tool_calls": TELEMETRY["tool_calls"],
            "total_tokens": TELEMETRY["total_tokens"],
            "total_cost": TELEMETRY.get("total_cost", 0.0),
            "services": {
                "home_assistant": {
                    "name": "Home Assistant (Domotique)",
                    "status": "online" if has_ha else "offline",
                    "icon": "🏠"
                },
                "google_calendar": {
                    "name": "Google Calendar Sync",
                    "status": "online" if has_google else "offline",
                    "icon": "📅"
                },
                "caldav": {
                    "name": "CalDAV / Nextcloud",
                    "status": "online" if has_caldav else "offline",
                    "icon": "🔗"
                },
                "code_sandbox": {
                    "name": "Bac à sable de Code (Python)",
                    "status": "online",
                    "icon": "🐍"
                },
                "web_search": {
                    "name": "Scraping & Recherche Web",
                    "status": "online",
                    "icon": "🌐"
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/gallery")
async def get_media_gallery():
    try:
        images_dir = "workspace/generated_images"
        videos_dir = "workspace/generated_videos"
        
        gallery = []
        
        # Images
        if os.path.exists(images_dir):
            for f in os.listdir(images_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    path = os.path.join(images_dir, f)
                    stat = os.stat(path)
                    gallery.append({
                        "name": f,
                        "path": f"workspace/generated_images/{f}",
                        "url": f"/api/workspace/download?path=workspace/generated_images/{f}",
                        "type": "image",
                        "time": stat.st_mtime
                    })
                    
        # Vidéos / Gifs animés
        if os.path.exists(videos_dir):
            for f in os.listdir(videos_dir):
                if f.lower().endswith(('.gif', '.mp4')):
                    path = os.path.join(videos_dir, f)
                    stat = os.stat(path)
                    gallery.append({
                        "name": f,
                        "path": f"workspace/generated_videos/{f}",
                        "url": f"/api/workspace/download?path=workspace/generated_videos/{f}",
                        "type": "video",
                        "time": stat.st_mtime
                    })
                    
        # Classer du plus récent au plus ancien
        gallery.sort(key=lambda x: x["time"], reverse=True)
        return gallery
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class DeleteMediaRequest(BaseModel):
    path: str

@app.post("/api/gallery/delete")
async def delete_gallery_media(req: DeleteMediaRequest):
    try:
        normalized = os.path.normpath(req.path)
        # SÉCURITÉ CRITIQUE : Interdire toute sortie des répertoires de la galerie
        if not (normalized.startswith("workspace/generated_images/") or normalized.startswith("workspace/generated_videos/")):
            raise HTTPException(status_code=400, detail="Chemin non autorisé pour la suppression.")
            
        if os.path.exists(normalized):
            os.remove(normalized)
            return {"status": "success", "message": "Fichier média supprimé avec succès."}
        else:
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

PRICING_CONFIG_PATH = "workspace/pricing_config.json"
DEFAULT_PRICING = {
    "gpt-4o": {"input_cost_per_million": 2.30, "output_cost_per_million": 9.20},
    "gpt-4o-mini": {"input_cost_per_million": 0.14, "output_cost_per_million": 0.55},
    "anthropic/claude-3-5-sonnet-20241022": {"input_cost_per_million": 2.76, "output_cost_per_million": 13.80},
    "anthropic/claude-3-5-haiku-20241022": {"input_cost_per_million": 0.74, "output_cost_per_million": 3.68},
    "gemini/gemini-2.5-flash": {"input_cost_per_million": 0.07, "output_cost_per_million": 0.28},
    "gemini/gemini-2.5-pro": {"input_cost_per_million": 1.15, "output_cost_per_million": 4.60},
    "qwen/qwen-2.5-72b-instruct": {"input_cost_per_million": 0.37, "output_cost_per_million": 0.37},
    "default": {"input_cost_per_million": 0.50, "output_cost_per_million": 1.50}
}

@app.get("/api/pricing")
async def get_pricing():
    try:
        if os.path.exists(PRICING_CONFIG_PATH):
            with open(PRICING_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return DEFAULT_PRICING
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pricing")
async def save_pricing(payload: Dict[str, Any]):
    try:
        # Valider que le payload est bien un dict de modèles avec les bons champs
        validated = {}
        for model_name, costs in payload.items():
            if isinstance(costs, dict) and "input_cost_per_million" in costs and "output_cost_per_million" in costs:
                validated[model_name] = {
                    "input_cost_per_million": float(costs["input_cost_per_million"]),
                    "output_cost_per_million": float(costs["output_cost_per_million"])
                }
        os.makedirs("workspace", exist_ok=True)
        with open(PRICING_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(validated, f, indent=4, ensure_ascii=False)
        return {"status": "success", "models_count": len(validated)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pricing/reset")
async def reset_pricing():
    try:
        os.makedirs("workspace", exist_ok=True)
        with open(PRICING_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PRICING, f, indent=4, ensure_ascii=False)
        return {"status": "reset", "data": DEFAULT_PRICING}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import requests

@app.get("/api/config/models")
async def list_available_models():
    env = parse_env()
    
    # Flagships statiques de repli
    models = {
        "OpenAI (Flagships)": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini"],
        "Anthropic Claude": ["anthropic/claude-3-5-sonnet-20241022", "anthropic/claude-3-5-haiku-20241022", "anthropic/claude-3-opus-20240229", "anthropic/claude-3-sonnet-20240229", "anthropic/claude-3-haiku-20240307"],
        "Google Gemini": ["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash", "gemini/gemini-1.5-pro", "gemini/gemini-1.5-flash", "gemini/gemini-1.0-pro"],
        "Groq Fast Inference": ["groq/llama-3.3-70b-specdec", "groq/llama-3.1-70b-versatile", "groq/llama-3.1-8b-instant", "groq/mixtral-8x7b-32768", "groq/gemma2-9b-it"],
        "Mistral AI": ["mistral/mistral-large-latest", "mistral/mistral-medium-latest", "mistral/mistral-small-latest", "mistral/codestral-latest", "mistral/open-mixtral-8b"],
        "OpenRouter Cloud": [
            "openrouter/anthropic/claude-3.5-sonnet",
            "openrouter/deepseek/deepseek-chat",
            "openrouter/deepseek/deepseek-r1",
            "openrouter/google/gemini-2.5-pro",
            "openrouter/meta-llama/llama-3.3-70b-instruct",
            "openrouter/qwen/qwen-2.5-72b-instruct"
        ],
        "Ollama (Local / Custom)": [
            "ollama/llama3",
            "ollama/llama3.1",
            "ollama/llama3.3",
            "ollama/deepseek-r1",
            "ollama/mistral",
            "ollama/qwen2.5",
            "ollama/phi3",
            "ollama/gemma2"
        ],
        "Qwen Cloud (Dashscope)": ["dashscope/qwen-max", "dashscope/qwen-plus", "dashscope/qwen-turbo", "dashscope/qwen-long", "dashscope/qwen2.5-72b-instruct", "dashscope/qwen2.5-14b-instruct", "dashscope/qwen2.5-7b-instruct"],
    }
    
    # 1. Requête OpenAI en direct si clé présente
    openai_key = env.get("OPENAI_API_KEY")
    if openai_key:
        try:
            headers = {"Authorization": f"Bearer {openai_key}"}
            r = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=2)
            if r.status_code == 200:
                openai_models = [m['id'] for m in r.json().get("data", []) if "gpt" in m['id']]
                if openai_models:
                    models["OpenAI"] = sorted(openai_models)
        except Exception:
            pass

    # 1b. Requête Anthropic en direct si clé présente
    anthropic_key = env.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            headers = {
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01"
            }
            r = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=2)
            if r.status_code == 200:
                anthropic_models = [f"anthropic/{m['id']}" for m in r.json().get("data", [])]
                if anthropic_models:
                    models["Anthropic"] = sorted(anthropic_models)
        except Exception:
            pass

    # 2. Requête Google Gemini en direct si clé présente
    gemini_key = env.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_key}", timeout=2)
            if r.status_code == 200:
                gemini_models = [f"gemini/{m['name'].split('/')[-1]}" for m in r.json().get("models", []) if "gemini" in m['name']]
                if gemini_models:
                    models["Google Gemini"] = sorted(gemini_models)
        except Exception:
            pass

    # 3. Requête Groq en direct si clé présente
    groq_key = env.get("GROQ_API_KEY")
    if groq_key:
        try:
            headers = {"Authorization": f"Bearer {groq_key}"}
            r = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=2)
            if r.status_code == 200:
                groq_models = [f"groq/{m['id']}" for m in r.json().get("data", [])]
                if groq_models:
                    models["Groq"] = sorted(groq_models)
        except Exception:
            pass

    # 4. Requête Mistral AI en direct si clé présente
    mistral_key = env.get("MISTRAL_API_KEY")
    if mistral_key:
        try:
            headers = {"Authorization": f"Bearer {mistral_key}"}
            r = requests.get("https://api.mistral.ai/v1/models", headers=headers, timeout=2)
            if r.status_code == 200:
                mistral_models = [f"mistral/{m['id']}" for m in r.json().get("data", [])]
                if mistral_models:
                    models["Mistral AI"] = sorted(mistral_models)
        except Exception:
            pass

    # 5. Requête Ollama local si disponible
    ollama_base = env.get("OLLAMA_API_BASE")
    if ollama_base:
        try:
            r = requests.get(f"{ollama_base.rstrip('/')}/api/tags", timeout=2)
            if r.status_code == 200:
                local_models = [f"ollama/{m['name']}" for m in r.json().get("models", [])]
                if local_models:
                    models["Ollama (Local)"] = local_models
        except Exception:
            pass
            
    # 6. Requête OpenRouter si clé présente
    or_key = env.get("OPENROUTER_API_KEY")
    if or_key:
        try:
            headers = {"Authorization": f"Bearer {or_key}"}
            r = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=3)
            if r.status_code == 200:
                or_models = [f"openrouter/{m['id']}" for m in r.json().get("data", [])]
                if or_models:
                    models["OpenRouter"] = or_models[:30]
        except Exception:
            pass
            
    # 7. Requête Custom LLM Endpoint si disponible
    custom_base = env.get("CUSTOM_LLM_API_BASE")
    custom_key = env.get("CUSTOM_LLM_API_KEY")
    if custom_base:
        models["Custom Endpoint"] = ["custom-model"] # Valeur de repli par défaut pour choix rapide
        
        # Open WebUI ou autres serveurs d'API peuvent avoir des routes /models déplacées par rapport au /v1 de completion
        urls_to_try = [f"{custom_base.rstrip('/')}/models"]
        if "/v1" in custom_base:
            urls_to_try.append(custom_base.replace("/v1", "/api/v1").rstrip("/") + "/models")
            urls_to_try.append(custom_base.replace("/v1", "/api").rstrip("/") + "/models")
        elif "/api/v1" in custom_base:
            urls_to_try.append(custom_base.replace("/api/v1", "/api").rstrip("/") + "/models")
            
        headers = {}
        if custom_key:
            headers["Authorization"] = f"Bearer {custom_key}"
            
        for url in urls_to_try:
            try:
                r = requests.get(url, headers=headers, timeout=3)
                if r.status_code == 200:
                    content_type = r.headers.get("Content-Type", "").lower()
                    if "json" in content_type or r.text.strip().startswith("{"):
                        c_models = [m['id'] for m in r.json().get("data", [])]
                        if c_models:
                            models["Custom Endpoint"] = c_models
                            break # On a trouvé une URL valide avec du JSON
            except Exception:
                pass
                
    return models

import threading
import time

telegram_sessions = {}  # chat_id -> {"messages": [], "active_agent": agent}

def telegram_bot_worker():
    print("🤖 [Telegram] Worker démarré.")
    last_update_id = 0
    
    while True:
        try:
            env = parse_env()
            token = env.get("TELEGRAM_BOT_TOKEN")
            if not token:
                time.sleep(5)
                continue
                
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 10}
            r = requests.get(url, params=params, timeout=15)
            
            if r.status_code == 200:
                updates = r.json().get("result", [])
                for update in updates:
                    last_update_id = update["update_id"]
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                        
                    chat_id = message["chat"]["id"]
                    text = message["text"]

                    print(f"🤖 [Telegram] Message reçu de {chat_id}: {text}")

                    # --- DM pairing : seuls les contacts approuvés peuvent dialoguer ---
                    from core import telegram_pairing as _pair

                    def _tg_send(cid, msg):
                        try:
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                          json={"chat_id": cid, "text": msg}, timeout=8)
                        except Exception:
                            pass

                    if _pair.required() and not _pair.is_allowed(chat_id):
                        # Commande d'approbation depuis ce chat (cas rare) ignorée s'il n'est pas autorisé.
                        if not _pair.maybe_bootstrap(chat_id):
                            code = _pair.request_pairing(chat_id)
                            _tg_send(chat_id, f"🔒 Accès non autorisé. Code de pairage : {code}\n"
                                              "Demande à l'administrateur de l'approuver "
                                              "(Réglages → Messageries, ou « /approve " + code + " » depuis un compte autorisé).")
                            for owner in _pair.allowed_chats():
                                _tg_send(owner, f"🔔 Demande d'accès Telegram de {chat_id}. Pour approuver : /approve {code}")
                            print(f"🤖 [Telegram] Accès refusé pour {chat_id} (pairing requis, code {code}).")
                            continue
                        else:
                            _tg_send(chat_id, f"✅ Bienvenue — ce compte est désormais l'administrateur de {_app_name()}.")

                    # Commande d'approbation par l'administrateur : /approve <code>
                    if text.strip().lower().startswith("/approve ") and _pair.is_allowed(chat_id):
                        cid = _pair.approve_code(text.strip().split(None, 1)[1])
                        _tg_send(chat_id, f"✅ Contact {cid} approuvé." if cid else "Code de pairage inconnu.")
                        if cid:
                            _tg_send(cid, f"✅ Ton accès à {_app_name()} a été approuvé. Tu peux maintenant discuter.")
                        continue

                    # Initialiser la session si elle n'existe pas
                    if chat_id not in telegram_sessions:
                        default_agent = _orch_agent() or list(swarm.agents.values())[0]
                        telegram_sessions[chat_id] = {
                            "messages": [{"role": "system", "content": f"Tu es {_orch_name()}, le superviseur de l'essaim multi-agent."}],
                            "active_agent": default_agent
                        }
                    
                    session_data = telegram_sessions[chat_id]
                    
                    # Gérer /reset
                    if text.strip() == "/reset":
                        default_agent = _orch_agent() or list(swarm.agents.values())[0]
                        telegram_sessions[chat_id] = {
                            "messages": [{"role": "system", "content": f"Tu es {_orch_name()}, le superviseur de l'essaim multi-agent."}],
                            "active_agent": default_agent
                        }
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": "🔄 *Essaim réinitialisé pour cette discussion.*",
                            "parse_mode": "Markdown"
                        })
                        continue
                        
                    # Gérer /status
                    if text.strip() == "/status":
                        agent_name = session_data["active_agent"].name
                        msg = f"🏢 *État de l'essaim :*\n• *Agent actif :* `{agent_name}`\n• *Agents disponibles :* {', '.join([f'`{a}`' for a in swarm.agents.keys()])}"
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": msg,
                            "parse_mode": "Markdown"
                        })
                        continue
                    
                    # Gérer le message utilisateur
                    session_data["messages"].append({"role": "user", "content": text})
                    
                    # Envoyer l'action "typing"
                    requests.post(f"https://api.telegram.org/bot{token}/sendChatAction", json={
                        "chat_id": chat_id,
                        "action": "typing"
                    })
                    
                    tg_run_id = run_store.new_run_id()
                    run_registry.start(tg_run_id)
                    tg_token = current_run_id.set(tg_run_id)
                    tg_chan = f"telegram:{chat_id}"
                    tg_chan_token = channels.current_channel.set(tg_chan)
                    tg_appr_token = approvals.auto_approve_var.set(channels.auto_approve_for(tg_chan))
                    try:
                        # On démarre avec l'agent actuellement actif pour un dialogue persistant
                        starting_agent = session_data["active_agent"] or _orch_agent()
                        next_agent, new_messages, steps = swarm.run(starting_agent, session_data["messages"])
                        session_data["active_agent"] = _orch_agent()
                        session_data["messages"] = new_messages
                        
                        # Formater la trace d'exécution pour Telegram
                        formatted_response = ""
                        for step in steps:
                            if step["type"] == "activation":
                                formatted_response += f"👤 *{step['agent']}* prend la main.\n"
                            elif step["type"] == "tool_call":
                                formatted_response += f"  ⚙️ Outil: `{step['tool']}`\n"
                            elif step["type"] == "tool_output":
                                output_preview = step['output'][:80] + "..." if len(step['output']) > 80 else step['output']
                                formatted_response += f"  📊 Résultat: `{output_preview}`\n"
                            elif step["type"] == "handoff":
                                formatted_response += f"➡️ Relais : `{step['from']}` ➔ `{step['to']}`\n"
                            elif step["type"] == "message":
                                formatted_response += f"\n💬 *{step['agent']} :*\n{step['content']}\n"
                                
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": formatted_response or "Tâche traitée en arrière-plan sans réponse formulée.",
                            "parse_mode": "Markdown"
                        })
                    except Exception as swarm_err:
                        print(f"🤖 [Telegram] Erreur swarm: {swarm_err}")
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
                            "chat_id": chat_id,
                            "text": f"❌ *Erreur de l'essaim :* {str(swarm_err)}",
                            "parse_mode": "Markdown"
                        })
                    finally:
                        run_registry.finish(tg_run_id)
                        current_run_id.reset(tg_token)
                        channels.current_channel.reset(tg_chan_token)
                        approvals.auto_approve_var.reset(tg_appr_token)
            elif r.status_code == 401:
                print("🤖 [Telegram] Token invalide ou non autorisé.")
                time.sleep(10)
            else:
                print(f"🤖 [Telegram] Erreur de récupération: {r.status_code}")
                time.sleep(5)
        except Exception as e:
            print(f"🤖 [Telegram] Exception dans le thread: {e}")
            time.sleep(5)

# Lancement du bot en tâche de fond
t = threading.Thread(target=telegram_bot_worker, daemon=True)
t.start()

def agenda_scheduler():
    """
    Planificateur d'arrière-plan pour l'agenda.
    Vérifie toutes les 30 secondes si un événement approche (sous 15 min) ou commence,
    puis envoie des notifications. Synchronise également les calendriers toutes les 5 minutes.
    """
    import time
    import json
    from datetime import datetime
    from tools.agenda_tools import AGENDA_FILE, ensure_agenda_file, sync_all_external_calendars, load_agenda
    
    print("📅 [Agenda] Planificateur d'arrière-plan démarré.")
    last_sync = 0
    
    while True:
        try:
            # Synchronisation toutes les 5 minutes
            now_ts = time.time()
            if now_ts - last_sync > 300:
                print("📅 [Agenda] Synchronisation automatique d'arrière-plan...")
                try:
                    sync_all_external_calendars()
                    last_sync = now_ts
                except Exception as sync_err:
                    print(f"📅 [Agenda Sync Erreur d'arrière-plan] {sync_err}")

            events = load_agenda()
            if events:
                now = datetime.now()
                updated = False

                for e in events:
                    try:
                        event_dt = datetime.strptime(e["datetime"], "%Y-%m-%d %H:%M")
                    except Exception:
                        continue
                        
                    diff_minutes = (event_dt - now).total_seconds() / 60.0
                    
                    # Rappel 15 minutes avant
                    if 0 < diff_minutes <= 15.0 and not e.get("reminded_15m", False):
                        e["reminded_15m"] = True
                        updated = True
                        msg = f"🔔 [{_app_name()} Agenda] Rappel : Votre événement '{e['title']}' commence dans {int(diff_minutes)} minutes (à {e['datetime']})."
                        if e.get("description"):
                            msg += f"\nDescription : {e['description']}"
                        broadcast_notification(msg)
                        
                    # Rappel immédiat au début
                    elif -1.0 <= diff_minutes <= 0.5 and not e.get("reminded_now", False):
                        e["reminded_now"] = True
                        updated = True
                        msg = f"⚡ [{_app_name()} Agenda] C'est l'heure ! Votre événement '{e['title']}' commence maintenant ({e['datetime']})."
                        if e.get("description"):
                            msg += f"\nDescription : {e['description']}"
                        broadcast_notification(msg)
                        
                if updated:
                    with open(AGENDA_FILE, "w", encoding="utf-8") as f:
                        json.dump(events, f, indent=4, ensure_ascii=False)
        except Exception as err:
            print(f"📅 [Agenda Erreur] {err}")
            
        time.sleep(30)

_budget_alert_date = None


def _check_budget():
    """Alerte (une fois par jour) si le coût cumulé du jour dépasse BUDGET_DAILY_LIMIT (€)."""
    global _budget_alert_date
    try:
        limit = float(os.getenv("BUDGET_DAILY_LIMIT", "0") or 0)
    except ValueError:
        return
    if limit <= 0:
        return
    import datetime
    today = datetime.date.today().isoformat()
    cost = run_store.cost_today()
    if cost >= limit and _budget_alert_date != today:
        _budget_alert_date = today
        broadcast_notification(
            f"⚠️ Budget quotidien dépassé : {cost:.2f} € / {limit:.2f} € (les requêtes continuent).",
            title=f"Alerte budget {_app_name()}",
        )


@app.get("/api/budget")
async def get_budget():
    try:
        limit = float(os.getenv("BUDGET_DAILY_LIMIT", "0") or 0)
    except ValueError:
        limit = 0.0
    return {"today": run_store.cost_today(), "limit": limit}


def broadcast_notification(message: str, title: str = None):
    """Diffuse le message sur la console et tous les canaux configurés
    (Discord, Slack, webhook, email, Telegram explicite) + les sessions
    Telegram actives en cours."""
    print(f"\033[93m📣 [Notification]\033[0m {message}")

    # Canaux configurés (env) via la couche multi-canaux.
    try:
        from core.notifications import notify
        notify(message, title=title)
    except Exception as e:
        print(f"[Notification erreur] {e}")

    # Sessions Telegram actives (utilisateurs ayant écrit au bot).
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        for chat_id in list(telegram_sessions.keys()):
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message},
                    timeout=5
                )
            except Exception as e:
                print(f"🤖 [Telegram Alerte Erreur] chat_id {chat_id}: {e}")

# Lancement du planificateur d'agenda en tâche de fond
t_agenda = threading.Thread(target=agenda_scheduler, daemon=True)
t_agenda.start()

# Démarrage du listener satellites ESP32-S3 (ESPHome) si au moins un est configuré.
# Tolérant : si aioesphomeapi/whisper/Piper manquent, l'erreur est juste remontée
# dans l'UI (status), le serveur n'est pas impacté.
try:
    from voice.esphome_satellites import manager as satellite_manager, _load_satellites
    if _load_satellites():
        satellite_manager.start()
        print("🛰️  [Satellites] Listener démarré.")
except Exception as e:
    print(f"🛰️  [Satellites] non démarré : {e}")


# =========================================================================
# ROUTINES PROACTIVES / PLANIFIÉES (cron-agent)
# =========================================================================
def _run_routine(routine: dict):
    """Exécute une routine : lance l'agent sur son prompt, persiste, notifie."""
    prompt = (routine.get("prompt") or "").strip()
    if not prompt:
        return
    starting = swarm.agents.get(routine.get("agent", _orch_name())) or _orch_agent()
    rid = run_store.new_run_id()
    started = time.time()
    token = current_run_id.set(rid)
    run_registry.start(rid)
    chan_token = channels.current_channel.set("routine")
    appr_token = approvals.auto_approve_var.set(True)  # tâche planifiée = de confiance
    try:
        agent, _msgs, steps = swarm.run(starting, [{"role": "user", "content": prompt}])
        steps = list(steps)
        resp = next((s.get("content", "") for s in reversed(steps) if s.get("type") == "message"), "")
        run_store.save(
            run_id=rid, agent=agent.name, status="routine",
            user_message=f"[Routine] {routine.get('name', '')}", final_response=resp,
            duration_ms=int((time.time() - started) * 1000), steps=steps, created_at=started,
        )
        logger.info("routine '%s' exécutée (run %s)", routine.get("name"), rid)
        if routine.get("notify", True) and resp:
            broadcast_notification(resp, title=f"🗓️ {routine.get('name', 'Routine')}")
        _check_budget()
    except Exception as e:
        logger.exception("Erreur routine '%s'", routine.get("name"))
    finally:
        run_registry.finish(rid)
        current_run_id.reset(token)
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)


class RoutineRequest(BaseModel):
    id: str = None
    name: str
    prompt: str
    agent: str = ""  # vide = orchestrateur (résolu à l'exécution via _orch_name)
    schedule: Dict[str, Any]
    enabled: bool = True
    notify: bool = True
    secret: str = None


@app.get("/api/routines")
async def list_routines():
    return {"routines": routine_store.list()}


@app.post("/api/routines")
async def save_routine(req: RoutineRequest):
    return {"status": "success", "routine": routine_store.upsert(req.dict())}


@app.delete("/api/routines/{rid}")
async def delete_routine(rid: str):
    routine_store.delete(rid)
    return {"status": "success"}


@app.post("/api/routines/{rid}/run")
async def run_routine_now(rid: str):
    r = routine_store.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="Routine introuvable.")
    await asyncio.to_thread(_run_routine, r)
    return {"status": "success"}


@app.api_route("/api/hooks/{rid}", methods=["GET", "POST"])
async def trigger_hook(rid: str, request: Request, token: str = None):
    """Webhook entrant (Home Assistant, capteurs, IFTTT…) : déclenche une routine
    de type 'webhook'. Exempté de l'auth admin, protégé par un secret propre.
    Le corps (JSON ou texte) est injecté dans le prompt comme données d'événement."""
    r = routine_store.get(rid)
    if not r or (r.get("schedule") or {}).get("type") != "webhook":
        raise HTTPException(status_code=404, detail="Webhook introuvable.")
    secret = r.get("secret", "") or ""
    provided = token or request.headers.get("X-Hook-Secret", "")
    if secret and not secrets.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Secret de webhook invalide.")
    if not r.get("enabled", True):
        raise HTTPException(status_code=403, detail="Webhook désactivé.")

    # Récupérer le payload (JSON de préférence, sinon texte brut).
    payload = None
    try:
        payload = await request.json()
    except Exception:
        try:
            raw = (await request.body()).decode("utf-8", "ignore").strip()
            payload = raw or None
        except Exception:
            payload = None

    routine = dict(r)
    if payload:
        data = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload)
        routine["prompt"] = (r.get("prompt", "") + "\n\n[Données de l'événement reçu]\n" + data[:2000]).strip()

    await asyncio.to_thread(_run_routine, routine)
    return {"status": "triggered", "routine": r.get("name")}


# Lancement du planificateur de routines en tâche de fond
start_routine_scheduler(_run_routine)

# Endpoint de transcription et diarisation de réunions audio
@app.post("/api/meeting/transcribe")
async def transcribe_meeting(file: UploadFile = File(...)):
    try:
        content = await file.read()
        mime_type = file.content_type or "audio/mp3"
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        
        # 1. OPTION DE TRANSCRIPTION LOCALE : OPENAI-WHISPER OFFLINE (GRATUIT)
        local_whisper_available = False
        try:
            import whisper
            local_whisper_available = True
        except ImportError:
            pass

        if local_whisper_available:
            print("🎙️ [Meeting API] Utilisation de Whisper local (Modèle 'base')...")
            # Pour transcrire, whisper a besoin d'un vrai fichier sur le disque.
            # On va sauvegarder temporairement le fichier uploadé dans le dossier 'workspace'.
            os.makedirs("workspace", exist_ok=True)
            temp_filename = f"workspace/temp_{uuid.uuid4().hex}_{file.filename}"
            with open(temp_filename, "wb") as f:
                f.write(content)
            
            try:
                model = whisper.load_model("base")
                result = model.transcribe(temp_filename)
                raw_text = result.get("text", "").strip()
                print(f"🎙️ [Meeting API] Transcription locale réussie ({len(raw_text)} caractères).")
            finally:
                # Toujours supprimer le fichier temporaire
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                    
            # Charger la configuration dynamique de l'agent Secretaire (modèle et instructions système)
            custom_base = os.environ.get("CUSTOM_LLM_API_BASE", "").strip()
            custom_key = os.environ.get("CUSTOM_LLM_API_KEY", "").strip()
            
            secretaire_model = "qwen3"
            secretaire_instructions = (
                "Tu es un secrétaire expert en analyse et transcription de réunions."
            )
            
            secretaire_agent = swarm.agents.get("Secretaire")
            if secretaire_agent:
                secretaire_model = secretaire_agent.model
                # Filtrer les instructions orientées agent de chat s'il y en a
                secretaire_instructions = secretaire_agent.system_prompt
                print(f"🎙️ [Meeting API] Utilisation de l'agent Secretaire dynamique (Modèle : {secretaire_model}).")
                
            def clean_and_parse_json(text):
                text = text.strip()
                # Enlever les éventuelles balises Markdown pour les blocs JSON
                if text.startswith("```"):
                    first_line_end = text.find("\n")
                    if first_line_end != -1:
                        text = text[first_line_end:].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                try:
                    return json.loads(text)
                except Exception as e:
                    # Tenter d'isoler uniquement l'objet JSON si du texte superflu l'entoure
                    start_idx = text.find("{")
                    end_idx = text.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        try:
                            return json.loads(text[start_idx:end_idx+1])
                        except Exception:
                            pass
                    raise e

            # Directives strictes pour la structuration JSON, la diarisation intelligente et le compte-rendu
            system_prompt = (
                f"{secretaire_instructions}\n\n"
                "--- DIRECTIVES DE STRUCTURATION ET DE DIARISATION ABSOLUES ---\n"
                "1. DIARISATION (IDENTIFICATION DES LOCUTEURS) :\n"
                "   - Tu dois séparer intelligemment le texte brut en un dialogue de répliques distinctes.\n"
                "   - Identifie précisément qui parle d'après le contexte des phrases (ex: si quelqu'un dit 'Sophie, qu'en pensez-vous ?', la personne qui parle est un interlocuteur distinct (ex: 'Locuteur A'), et la personne qui répond après est 'Sophie').\n"
                "   - Ne nomme JAMAIS un locuteur 'Agent Secrétaire', 'Secrétaire', 'Orchestrateur' ou 'IA'. Les locuteurs doivent être des humains participant à la réunion (ex: 'Sophie', 'Jean', ou 'Locuteur A', 'Locuteur B' si les prénoms ne sont pas connus).\n"
                "   - Ne mets pas plusieurs phrases de locuteurs différents dans la même réplique.\n"
                "\n"
                "2. COMPTE-RENDU (RÉSUMÉ EXÉCUTIF) :\n"
                "   - Rédige un compte-rendu complet, formel et extrêmement professionnel en Markdown dans la clé 'summary'.\n"
                "   - Même si l'audio est extrêmement court (comme un simple test), réédige un rapport stylé et propre résumant l'échange (par exemple en signalant qu'il s'agit d'un test réussi des fonctionnalités de transcription).\n"
                "   - Ton rapport doit comporter un titre, un résumé exécutif, les points clés abordés et des décisions ou prochaines étapes.\n"
                "   - Ne laisse JAMAIS le champ 'summary' vide.\n"
                "\n"
                "3. FORMAT DE RÉPONSE :\n"
                "   - Réponds obligatoirement sous forme d'un objet JSON valide contenant EXACTEMENT ces deux clés :\n"
                "     {\n"
                '       "transcript": [\n'
                '         { "speaker": "Nom/Label Locuteur", "text": "phrase exacte" },\n'
                "         ...\n"
                '       ],\n'
                '       "summary": "Compte-rendu complet en Markdown"\n'
                "     }\n"
                "   - N'ajoute aucun texte explicatif en dehors du JSON pur. Pas de balise markdown ```json autour."
            )
            
            if custom_base and custom_key:
                # Auto-correction pour Open WebUI si l'utilisateur a mis /v1 au lieu de /api/v1
                if "/v1" in custom_base and not "/api" in custom_base:
                    custom_base = custom_base.replace("/v1", "/api/v1")
                
                print(f"🎙️ [Meeting API] Structuration via le LLM Custom ({custom_base})...")
                url_gpt = f"{custom_base}/chat/completions"
                headers_gpt = {
                    "Authorization": f"Bearer {custom_key}",
                    "Content-Type": "application/json"
                }
                payload_gpt = {
                    "model": secretaire_model,  # Utilise le modèle dynamique configuré de l'agent Secretaire
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Voici le texte brut :\n\n{raw_text}"}
                    ]
                }
                r_gpt = requests.post(url_gpt, json=payload_gpt, headers=headers_gpt, timeout=120)
                if r_gpt.status_code == 200:
                    gpt_response = r_gpt.json()["choices"][0]["message"]["content"]
                    return clean_and_parse_json(gpt_response)
                else:
                    raise Exception(f"Erreur LLM Custom (HTTP {r_gpt.status_code}) : {r_gpt.text}")
                    
            elif openai_key:
                print("🎙️ [Meeting API] Structuration via OpenAI GPT-4o...")
                url_gpt = "https://api.openai.com/v1/chat/completions"
                headers_gpt = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                payload_gpt = {
                    "model": "gpt-4o",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Voici le texte brut :\n\n{raw_text}"}
                    ]
                }
                r_gpt = requests.post(url_gpt, json=payload_gpt, headers=headers_gpt, timeout=90)
                if r_gpt.status_code == 200:
                    gpt_response = r_gpt.json()["choices"][0]["message"]["content"]
                    return clean_and_parse_json(gpt_response)
                else:
                    raise Exception(f"Erreur GPT-4o (HTTP {r_gpt.status_code}) : {r_gpt.text}")
                    
            elif gemini_key:
                print("🎙️ [Meeting API] Structuration via Google Gemini...")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": f"{system_prompt}\n\nVoici le texte brut :\n\n{raw_text}"}
                        ]
                    }],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                r = requests.post(url, json=payload, headers=headers, timeout=90)
                if r.status_code == 200:
                    res_data = r.json()
                    text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return clean_and_parse_json(text_response)
                else:
                    raise Exception(f"Erreur API Gemini (HTTP {r.status_code}) : {r.text}")
            else:
                print("🎙️ [Meeting API] Aucun LLM disponible pour structurer le compte-rendu. Rendu brut.")
                return {
                    "transcript": [
                        {"speaker": "Transcription brute locale", "text": raw_text}
                    ],
                    "summary": f"### 📝 Transcription de Réunion (Brute et locale)\n\n{raw_text}"
                }

        # 2. OPTION A : GOOGLE GEMINI 1.5 FLASH (Audio natif Cloud)
        elif gemini_key:
            print("🎙️ [Meeting API] Utilisation de Google Gemini 1.5 Flash pour transcription & diarisation...")
            audio_b64 = base64.b64encode(content).decode("utf-8")
            
            prompt = (
                "Agis en tant que secrétaire de direction et expert en analyse de réunions. "
                "Tu as reçu l'enregistrement audio de la réunion. Ta tâche est double :\n"
                "1. Transcris fidèlement la réunion. Tu devez absolument différencier les interlocuteurs "
                "(ex: 'Locuteur A', 'Locuteur B') en identifiant leurs voix distinctes. Ne crée pas de texte brut continu, "
                "renvoie un dialogue structuré.\n"
                "2. Rédige un compte-rendu de réunion structuré et hautement professionnel en Markdown contenant :\n"
                "   - Un résumé exécutif des échanges,\n"
                "   - Les points clés abordés,\n"
                "   - Les décisions prises,\n"
                "   - Un plan d'action clair (Action Item, Responsable, Priorité).\n\n"
                "Tu dois absolument me renvoyer une réponse en JSON structuré respectant EXACTEMENT le format suivant :\n"
                "{\n"
                '  "transcript": [\n'
                '    { "speaker": "Locuteur A (ou son nom si identifié)", "text": "sa transcription" },\n'
                "    ...\n"
                "  ],\n"
                '  "summary": "Le compte-rendu complet rédigé en Markdown"\n'
                "}\n"
                "N'ajoute aucun texte en dehors de ce JSON."
            )
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [
                        {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json"
                }
            }
            
            r = requests.post(url, json=payload, headers=headers, timeout=120)
            if r.status_code == 200:
                res_data = r.json()
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_response)
            else:
                raise Exception(f"Erreur API Gemini (HTTP {r.status_code}) : {r.text}")

        # 2. OPTION B : OPENAI WHISPER + GPT-4o
        elif openai_key:
            print("🎙️ [Meeting API] Utilisation d'OpenAI Whisper + GPT-4o...")
            url_whisper = "https://api.openai.com/v1/audio/transcriptions"
            headers_whisper = {"Authorization": f"Bearer {openai_key}"}
            files = {
                "file": (file.filename, content, mime_type),
                "model": (None, "whisper-1")
            }
            
            r_whisper = requests.post(url_whisper, headers=headers_whisper, files=files, timeout=60)
            if r_whisper.status_code == 200:
                raw_text = r_whisper.json().get("text", "")
                
                url_gpt = "https://api.openai.com/v1/chat/completions"
                headers_gpt = {
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                }
                
                system_prompt = (
                    "Tu es un secrétaire expert. Tu reçois le texte brut d'une réunion transcrite par Whisper. "
                    "Tu dois recréer le dialogue diarisé (différencier les interlocuteurs intelligemment d'après le contexte) "
                    "et générer un compte-rendu de réunion Markdown structuré. "
                    "Réponds impérativement avec un objet JSON structuré comme suit :\n"
                    "{\n"
                    '  "transcript": [\n'
                    '    { "speaker": "Locuteur A", "text": "phrase" },\n'
                    "    ...\n"
                    "  ],\n"
                    '  "summary": "Compte-rendu Markdown"\n'
                    "}"
                )
                
                payload_gpt = {
                    "model": "gpt-4o",
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Voici le texte brut :\n\n{raw_text}"}
                    ]
                }
                r_gpt = requests.post(url_gpt, json=payload_gpt, headers=headers_gpt, timeout=60)
                if r_gpt.status_code == 200:
                    gpt_response = r_gpt.json()["choices"][0]["message"]["content"]
                    return json.loads(gpt_response)
                else:
                    raise Exception(f"Erreur GPT-4o (HTTP {r_gpt.status_code}) : {r_gpt.text}")
            else:
                raise Exception(f"Erreur Whisper (HTTP {r_whisper.status_code}) : {r_whisper.text}")
                
        # 3. OPTION C : SIMULATION LOCALE HAUTE-FIDÉLITÉ (SANS CLÉ CONSTRUCTIVE)
        else:
            print("🎙️ [Meeting API] Aucun fournisseur configuré. Lancement d'une simulation...")
            await asyncio.sleep(4) # simuler le temps de traitement
            return {
                "transcript": [
                    {"speaker": "Marc (Président)", "text": "Bonjour à tous. Merci d'être venus pour ce point d'avancement Jarvis-Swarm."},
                    {"speaker": "Sophie (R&D)", "text": "Bonjour Marc. De notre côté, l'intégration du double-moteur vidéo Hunyuan et Stable Video Diffusion est terminée."},
                    {"speaker": "Lucas (UX)", "text": "Super! J'ai testé l'interface, les modals de réglages s'affichent maintenant parfaitement par-dessus les autres."},
                    {"speaker": "Marc (Président)", "text": "Excellent travail de toute l'équipe. Validons cette release pour aujourd'hui !"},
                ],
                "summary": (
                    "### 📝 Compte-rendu de Réunion - Jarvis-Swarm Release\n\n"
                    "**Date :** 28 Mai 2026\n"
                    "**Président de séance :** Marc\n\n"
                    "#### 1. Résumé exécutif\n"
                    "La réunion a permis de valider les dernières fonctionnalités de production de médias d'art IA de la release Jarvis-Swarm. Les fonctionnalités d'animation vidéo cloud (Fal & Replicate) et les corrections de couches graphiques (z-index modals) sont officiellement validées.\n\n"
                    "#### 2. Points clés abordés\n"
                    "- Intégration du double-moteur vidéo Hunyuan Video sur Fal.ai et Replicate.\n"
                    "- Correction du chevauchement des fenêtres modales de réglages d'agents.\n"
                    "- Ajout du module de transcription diarisée des réunions.\n\n"
                    "#### 3. Décisions prises\n"
                    "- **RELEASE VALIDÉE :** Lancement de la version finale en production dès ce soir.\n\n"
                    "#### 4. Plan d'action\n"
                    "| Action | Responsable | Priorité |\n"
                    "| :--- | :--- | :---: |\n"
                    "| Déploiement en production de la build | Sophie | Haute |\n"
                    "| Rédaction de la note de mise à jour | Marc | Moyenne |"
                )
            }
    except Exception as e:
        return {"error": str(e)}

# Sert les fichiers statiques de l'interface Web
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import sys
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0").strip()
    port = int(os.getenv("PORT", "8000"))
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()

    # Note : le garde-fou réseau (_enforce_network_security) s'exécute déjà au
    # CHARGEMENT du module — il couvre aussi `uvicorn server:app`. Ici on ne fait
    # qu'un message d'avertissement convivial en mode local sans mot de passe.
    if not admin_password:
        print("\033[93m[AVERTISSEMENT] ADMIN_PASSWORD vide : authentification désactivée "
              "(autorisé uniquement car bind local).\033[0m")

    print(f"\n🚀 Lancement du serveur {_app_name()} Dashboard...")
    print(f"👉 Accède à l'application ici : http://{'localhost' if host == '0.0.0.0' else host}:{port}\n")
    uvicorn.run("server:app", host=host, port=port, reload=True)

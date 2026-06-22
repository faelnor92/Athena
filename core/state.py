import os
import re
import json
import time
import tempfile
import threading
import contextvars
from typing import Dict, Any, List
from core.swarm import Swarm
from core.users import user_store

# Variables globales (Télémétrie, CWD, config dynamique)
TELEMETRY = {
    "total_queries": 0,
    "tool_calls": 0,
    "total_tokens": 0,
    "total_cost": 0.0
}

CODER_CWD = None

def get_workspace_dir() -> str:
    # abspath : indispensable pour les vérifs anti-traversée (commonpath) des routeurs.
    # Si l'utilisateur courant a un PROJET ACTIF, on s'y scope ; sinon workspace de base.
    try:
        from core import projects
        p = projects.active_path()
        if p:
            return os.path.abspath(p)
    except Exception:
        pass
    return os.path.abspath(
        os.environ.get("ACTIVE_WORKSPACE_DIR",
                       os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")))

def get_coder_cwd() -> str:
    global CODER_CWD
    base = get_workspace_dir()
    if CODER_CWD is None or not os.path.isdir(CODER_CWD):
        CODER_CWD = base
    return CODER_CWD

def set_coder_cwd(target: str) -> str:
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

def parse_env() -> dict:
    env_path = ".env"
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()
    return env_vars

def get_model_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    try:
        env_vars = parse_env()
        custom_base = env_vars.get("CUSTOM_LLM_API_BASE")
        if custom_base:
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
            if not has_official_key or model_lower in ["qwen3", "custom-model"]:
                return 0.0

        pricing_path = "workspace/pricing_config.json"
        if not os.path.exists(pricing_path):
            return 0.0
        with open(pricing_path, "r", encoding="utf-8") as f:
            pricing = json.load(f)
            
        def _norm(m: str) -> str:
            return m.lower().split("/")[-1].strip()

        matched = None
        if model_name in pricing:
            matched = pricing[model_name]
        else:
            target = _norm(model_name)
            norm_index = {_norm(k): v for k, v in pricing.items() if k != "default"}
            if target in norm_index:
                matched = norm_index[target]
            else:
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

# Sessions d'authentification Web — adossées au store SQLite partagé pour rester
# cohérentes entre workers (un login sur un worker est reconnu par les autres).
# API dict-like minimale : ACTIVE_SESSIONS[token] = {...} / .get(token) / .pop(token, None).
class _SessionStore:
    _NS = "sessions"

    def __setitem__(self, token, value):
        from core import shared_store
        shared_store.set(self._NS, token, value)

    def get(self, token, default=None):
        from core import shared_store
        return shared_store.get(self._NS, token, default)

    def pop(self, token, default=None):
        from core import shared_store
        v = shared_store.get(self._NS, token, default)
        shared_store.delete(self._NS, token)
        return v

    def revoke_user(self, username: str, keep_token: str = None) -> int:
        """Révoque toutes les sessions d'un utilisateur (sauf keep_token éventuel).
        Appelé au changement/reset de mot de passe → un token volé cesse d'être valide."""
        from core import shared_store
        n = 0
        for tok, sess in shared_store.items(self._NS).items():
            if tok == keep_token:
                continue
            if (sess or {}).get("username") == username:
                shared_store.delete(self._NS, tok)
                n += 1
        return n

    def purge_expired(self) -> int:
        """Supprime les sessions expirées (hygiène du store)."""
        from core import shared_store
        now = time.time()
        n = 0
        for tok, sess in shared_store.items(self._NS).items():
            if (sess or {}).get("exp", 0) < now:
                shared_store.delete(self._NS, tok)
                n += 1
        return n

ACTIVE_SESSIONS = _SessionStore()
_current_username = contextvars.ContextVar("current_username", default=None)
# Rôle de l'appelant courant ("admin"/"user"/None). None = mode local/no-auth → traité
# comme admin (aucune restriction). Sert au RBAC par outil (ADMIN_ONLY_TOOLS).
_current_role = contextvars.ContextVar("current_role", default=None)
# Langue d'INTERFACE de l'appelant (code ISO court : fr/en/es/it/de/zh/ja). Posée par le
# serveur depuis l'en-tête X-Athena-Lang, propagée au thread swarm. Sert à faire RÉPONDRE
# les agents dans la langue de l'utilisateur (cf. préambule système). None → fr par défaut.
_current_lang = contextvars.ContextVar("current_lang", default=None)
# Noms de langue (dans la langue cible) pour la directive de réponse du préambule système.
LANG_NAMES = {
    "fr": "français", "en": "English", "es": "español", "it": "italiano",
    "de": "Deutsch", "zh": "中文（简体）", "ja": "日本語",
}

def _scope_cid(client_id: str) -> str:
    client_id = (client_id or "web").strip() or "web"
    if client_id.startswith("u:"):
        return client_id
    user = _current_username.get()
    if user:
        return f"u:{user}:{client_id}"
    return client_id

# Instance globale de l'essaim
swarm = Swarm("agents.yaml")

def _orch_name() -> str:
    return getattr(swarm, "orchestrator_name", None) or "Athena"

def _app_name() -> str:
    return os.getenv("APP_NAME", "").strip() or _orch_name()

def _orch_agent():
    a = swarm.agents.get(_orch_name())
    if a is None and swarm.agents:
        a = next(iter(swarm.agents.values()))
    return a

# --- Chiffrement de la DB ---
from cryptography.fernet import Fernet
_fernet = None

def _get_fernet():
    global _fernet
    if _fernet is None:
        env_vars = parse_env()
        key = env_vars.get("DB_ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key().decode("utf-8")
            try:
                with open(".env", "a", encoding="utf-8") as f:
                    f.write(f"\n# Clé de chiffrement des conversations SQLite (NE PAS PERDRE)\nDB_ENCRYPTION_KEY={key}\n")
            except Exception:
                pass
        _fernet = Fernet(key.encode("utf-8"))
    return _fernet

def _encrypt(data: str) -> str:
    return _get_fernet().encrypt(data.encode("utf-8")).decode("utf-8")

def _decrypt(data: str) -> str:
    try:
        return _get_fernet().decrypt(data.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback de migration douce : la donnée était en clair
        return data

# Gestionnaire de Conversations persistantes
import sqlite3

_CONV_DB_PATH = os.environ.get("CONVERSATIONS_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conversations.sqlite3"
))
_db_lock = threading.Lock()

def _init_conv_db():
    with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                client_id       TEXT,
                conv_id         TEXT,
                name            TEXT,
                messages_json   TEXT,
                active_node_id  TEXT,
                active_agent    TEXT,
                updated_at      REAL,
                PRIMARY KEY (client_id, conv_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_sessions (
                client_id       TEXT PRIMARY KEY,
                active_conv_id  TEXT
            )
        """)
        # Système de migration simple (Source de vérité)
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        db_version = cursor.fetchone()[0]
        
        # Version 1 : DB initiale. 
        # Si db_version == 0, on vient de créer la table, on set à 1.
        if db_version == 0:
            conn.execute("PRAGMA user_version = 1")
            
        # Exemple de migration future :
        # if db_version < 2:
        #     conn.execute("ALTER TABLE conversations ADD COLUMN new_col TEXT")
        #     conn.execute("PRAGMA user_version = 2")
        
_init_conv_db()

def _session_file(client_id: str) -> str:
    base = os.environ.get("CONVERSATIONS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conversations.json"
    )
    if client_id == "web": return base
    root, ext = os.path.splitext(base)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", client_id)
    return f"{root}_{safe}{ext or '.json'}"

class ConversationManager:
    def __init__(self, client_id="web"):
        self.client_id = client_id
        self.active_id = "default"
        
        legacy_path = _session_file(client_id)
        if os.path.exists(legacy_path) and not legacy_path.endswith(".sqlite3"):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    legacy_data = json.load(f)
                with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
                    for c_id, c_data in legacy_data.items():
                        conn.execute("""
                            INSERT OR IGNORE INTO conversations 
                            (client_id, conv_id, name, messages_json, active_node_id, active_agent, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            self.client_id, c_id, c_data.get("name", "Discussion"),
                            _encrypt(json.dumps(c_data.get("messages", []))),
                            c_data.get("active_node_id"),
                            c_data.get("active_agent", _orch_name()),
                            time.time()
                        ))
                os.rename(legacy_path, legacy_path + ".bak")
            except Exception as e:
                print(f"Error migrating JSON for {client_id}: {e}")

        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            row = conn.execute("SELECT active_conv_id FROM active_sessions WHERE client_id=?", (self.client_id,)).fetchone()
            if row:
                self.active_id = row[0]
            else:
                self.active_id = "default"
                conn.execute("INSERT OR REPLACE INTO active_sessions (client_id, active_conv_id) VALUES (?, ?)", (self.client_id, self.active_id))
                
        self._ensure_exists(self.active_id, "Discussion principale")

    def _ensure_exists(self, conv_id, default_name):
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            row = conn.execute("SELECT 1 FROM conversations WHERE client_id=? AND conv_id=?", (self.client_id, conv_id)).fetchone()
            if not row:
                conn.execute("""
                    INSERT INTO conversations (client_id, conv_id, name, messages_json, active_node_id, active_agent, updated_at)
                    VALUES (?, ?, ?, ?, NULL, ?, ?)
                """, (self.client_id, conv_id, default_name, _encrypt('[]'), _orch_name(), time.time()))

    @property
    def conversations(self):
        res = {}
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM conversations WHERE client_id=?", (self.client_id,)).fetchall()
            for r in rows:
                res[r["conv_id"]] = {
                    "name": r["name"],
                    "messages": json.loads(_decrypt(r["messages_json"])),
                    "active_node_id": r["active_node_id"],
                    "active_agent": r["active_agent"]
                }
        return res

    def save(self):
        pass
        
    # Colonnes autorisées : le nom de colonne est interpolé dans le SQL (les valeurs, elles,
    # sont paramétrées). ALLOWLIST stricte → aucune injection possible via `key`, même si un
    # futur appelant passait une valeur non maîtrisée. (Défense en profondeur.)
    _ALLOWED_CONV_COLS = {"messages", "active_node_id", "active_agent", "name"}

    def _update_conv(self, conv_id, key, value):
        if key not in self._ALLOWED_CONV_COLS:
            raise ValueError(f"colonne de conversation non autorisée : {key!r}")
        if key == "messages":
            col, val = "messages_json", _encrypt(json.dumps(value))
        else:
            col, val = key, value
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            conn.execute(f"UPDATE conversations SET {col}=?, updated_at=? WHERE client_id=? AND conv_id=?",  # nosec B608 — `col` validé par allowlist ci-dessus
                         (val, time.time(), self.client_id, conv_id))

    def new_conversation(self, name=None):
        import uuid
        conv_id = uuid.uuid4().hex[:8]
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM conversations WHERE client_id=?", (self.client_id,)).fetchone()[0]
        self._ensure_exists(conv_id, name or f"Discussion {count + 1}")
        self.active_id = conv_id
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            conn.execute("UPDATE active_sessions SET active_conv_id=? WHERE client_id=?", (conv_id, self.client_id))
        return conv_id
        
    def delete_conversation(self, conv_id):
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            conn.execute("DELETE FROM conversations WHERE client_id=? AND conv_id=?", (self.client_id, conv_id))
            row = conn.execute("SELECT conv_id FROM conversations WHERE client_id=? LIMIT 1", (self.client_id,)).fetchone()
            self.active_id = row[0] if row else "default"
            conn.execute("UPDATE active_sessions SET active_conv_id=? WHERE client_id=?", (self.active_id, self.client_id))
            self._ensure_exists(self.active_id, "Discussion principale")

    def get_active(self):
        with _db_lock, sqlite3.connect(_CONV_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM conversations WHERE client_id=? AND conv_id=?", (self.client_id, self.active_id)).fetchone()
            if not row:
                self._ensure_exists(self.active_id, "Discussion principale")
                row = conn.execute("SELECT * FROM conversations WHERE client_id=? AND conv_id=?", (self.client_id, self.active_id)).fetchone()
            return {
                "name": row["name"],
                "messages": json.loads(_decrypt(row["messages_json"])),
                "active_node_id": row["active_node_id"],
                "active_agent": row["active_agent"]
            }

class ChatSession:
    def __init__(self, client_id: str = "web"):
        self.client_id = client_id
        self.manager = ConversationManager(client_id=client_id)

    @property
    def messages(self):
        return self.manager.get_active()["messages"]
        
    @messages.setter
    def messages(self, value):
        self.manager._update_conv(self.manager.active_id, "messages", value)
        
    @property
    def active_node_id(self):
        return self.manager.get_active()["active_node_id"]
        
    @active_node_id.setter
    def active_node_id(self, value):
        self.manager._update_conv(self.manager.active_id, "active_node_id", value)
        
    @property
    def active_agent(self):
        agent_name = self.manager.get_active().get("active_agent", _orch_name())
        return swarm.agents.get(agent_name) or _orch_agent()
        
    @active_agent.setter
    def active_agent(self, agent_obj):
        name = agent_obj.name if agent_obj else _orch_name()
        self.manager._update_conv(self.manager.active_id, "active_agent", name)
        active_conv = self.manager.get_active()
        if len(active_conv["messages"]) > 0 and active_conv["name"].startswith("Discussion "):
            for msg in active_conv["messages"]:
                if msg["role"] == "user":
                    summary = msg["content"][:25] + "..." if len(msg["content"]) > 25 else msg["content"]
                    self.manager._update_conv(self.manager.active_id, "name", summary)
                    break
        
    def reset(self):
        self.manager._update_conv(self.manager.active_id, "messages", [])
        self.manager._update_conv(self.manager.active_id, "active_node_id", None)
        self.manager._update_conv(self.manager.active_id, "active_agent", _orch_name())
        self.manager._update_conv(self.manager.active_id, "name", "Discussion principale")

class SessionManager:
    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def get(self, client_id: str = "web") -> "ChatSession":
        client_id = _scope_cid(client_id)
        with self._lock:
            if client_id not in self._sessions:
                self._sessions[client_id] = ChatSession(client_id=client_id)
            return self._sessions[client_id]

sessions = SessionManager()

class _WebSessionProxy:
    def __getattr__(self, name):
        return getattr(sessions.get("web"), name)

    def __setattr__(self, name, value):
        setattr(sessions.get("web"), name, value)

session = _WebSessionProxy()

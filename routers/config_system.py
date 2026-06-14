import os
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.state import _app_name

router = APIRouter(tags=["Config System"])

def parse_env() -> Dict[str, str]:
    """Parses the .env file and returns a dictionary of its variables."""
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    val = val.strip().strip('"').strip("'")
                    env_vars[key.strip()] = val
    return env_vars

@router.get("/api/config/mcp")
async def get_config_mcp() -> Dict[str, Any]:
    """Configuration MCP (JSON brut) + état des serveurs/outils connectés."""
    try:
        from tools.mcp_manager import mcp_manager
        path = mcp_manager.config_path
        raw = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        return {"config": raw, "config_path": path, "status": mcp_manager.status()}
    except Exception as e:
        import logging
        logging.exception("Erreur récupération MCP")
        raise HTTPException(status_code=500, detail=str(e))

class SaveMcpRequest(BaseModel):
    config: str

@router.post("/api/config/mcp")
async def save_config_mcp(req: SaveMcpRequest) -> Dict[str, Any]:
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
        import logging
        logging.exception("Erreur redémarrage MCP")
        return {"status": "saved_with_error", "detail": str(e), "mcp": mcp_manager.status()}
    return {"status": "success", "mcp": mcp_manager.status()}

# --- Gestion graphique des serveurs MCP -----------------------------------
_MCP_MARKETPLACE_CATALOGS = [
    {
        "category": "Officiels (Anthropic)",
        "servers": [
            {
                "label": "Brave Search", "name": "brave-search", "icon": "🌐",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                "env": {"BRAVE_API_KEY": ""},
                "note": "Recherche web sur internet."
            },
            {
                "label": "Puppeteer", "name": "puppeteer", "icon": "🖥️",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
                "env": {},
                "note": "Automatisation web et navigation (Chromium headless)."
            },
            {
                "label": "GitHub", "name": "github", "icon": "🐙",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
                "note": "Gérer issues, PRs, et repos GitHub."
            },
            {
                "label": "PostgreSQL", "name": "postgres", "icon": "🐘",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost/db"],
                "env": {},
                "note": "Requêtes directes dans une BDD PostgreSQL."
            },
            {
                "label": "Memory", "name": "memory", "icon": "🧠",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {},
                "note": "Graphe de connaissances MCP d'Anthropic."
            }
        ]
    },
    {
        "category": "Utilitaires Locaux",
        "servers": [
            {
                "label": "Filesystem", "name": "filesystem", "icon": "📂",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/chemin/autorise"],
                "env": {},
                "note": "Donne un accès sécurisé à des dossiers spécifiques."
            },
            {
                "label": "Git", "name": "git", "icon": "🗂️",
                "command": "uvx", "args": ["mcp-server-git"],
                "env": {},
                "note": "Manipulation d'historique et branches Git locaux."
            },
            {
                "label": "Time", "name": "time", "icon": "⏰",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-time"],
                "env": {},
                "note": "Gestion des horloges mondiales et fuseaux horaires."
            }
        ]
    },
    {
        "category": "Communauté & Extensions",
        "servers": [
             {
                "label": "Home Assistant (ha-mcp) — local, géré par Athena", "name": "homeassistant", "icon": "🏠",
                "command": "", "args": [],
                "env": {"HOMEASSISTANT_URL": "", "HOMEASSISTANT_TOKEN": ""},
                "note": "84+ outils HA en STDIO : Athena le lance et le relance toute seule (pas de Docker, démarre/redémarre avec Athena). Renseigne HOMEASSISTANT_URL (ex: http://homeassistant.local:8123) + un token longue durée HA. Le chemin de commande est rempli automatiquement si ha-mcp est installé."
            },
            {
                "label": "SQLite", "name": "sqlite", "icon": "🗃️",
                "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "/chemin/vers/mabase.db"],
                "env": {},
                "note": "Exploration et modification de bases SQLite."
            },
            {
                "label": "Slack", "name": "slack", "icon": "💬",
                "command": "npx", "args": ["-y", "@modelcontextprotocol/server-slack"],
                "env": {"SLACK_BOT_TOKEN": "", "SLACK_TEAM_ID": ""},
                "note": "Accès aux channels Slack."
            }
        ]
    }
]


def _mcp_raw() -> Dict[str, Any]:
    from tools.mcp_manager import mcp_manager
    path = mcp_manager.config_path
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
            return data.get("mcpServers", data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _mcp_save(servers: Dict[str, Any]):
    from tools.mcp_manager import mcp_manager
    with open(mcp_manager.config_path, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": servers}, f, ensure_ascii=False, indent=2)


@router.get("/api/config/mcp/servers")
async def list_mcp_servers() -> Dict[str, Any]:
    """Serveurs MCP configurés (avec statut connecté + outils) pour l'UI graphique."""
    from tools.mcp_manager import mcp_manager
    servers = _mcp_raw()
    st = mcp_manager.status()
    connected = set(st.get("connected_servers", []))
    tbs = st.get("tools_by_server", {})
    out = []
    for name, conf in servers.items():
        out.append({
            "name": name,
            "command": conf.get("command", ""),
            "args": conf.get("args", []),
            "env": conf.get("env", {}),
            "disabled": bool(conf.get("disabled")),
            "connected": name in connected,
            "tools": tbs.get(name, []),
        })
    return {"servers": out, "presets": [], "tool_count": st.get("tool_count", 0)}

def _ha_mcp_stdio_command() -> str:
    """Chemin absolu du console-script stdio de ha-mcp s'il est installé (sinon '')."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cand = os.path.join(root, "tools", "mcp-servers", "ha-mcp", ".venv", "bin", "ha-mcp")
    return cand if os.path.exists(cand) else ""


@router.get("/api/config/mcp/marketplace")
async def mcp_marketplace() -> list[Dict[str, Any]]:
    """Retourne le catalogue complet des serveurs MCP pour l'UI.

    L'entrée Home Assistant est résolue dynamiquement : si ha-mcp est installé,
    on remplit son chemin de commande stdio (géré par Athena). Sinon on bascule
    l'entrée en mode HTTP avec une note pour la lancer à part."""
    import copy
    catalog = copy.deepcopy(_MCP_MARKETPLACE_CATALOGS)
    ha_cmd = _ha_mcp_stdio_command()
    for cat in catalog:
        for srv in cat.get("servers", []):
            if srv.get("name") != "homeassistant":
                continue
            if ha_cmd:
                srv["command"] = ha_cmd
                srv["args"] = []
            else:
                # ha-mcp pas installé localement → repli HTTP (service à lancer à part).
                srv["label"] = "Home Assistant (ha-mcp) — HTTP"
                srv["url"] = "http://127.0.0.1:8099/mcp"
                srv["transport"] = "http"
                srv["note"] = ("ha-mcp non installé localement. Lance-le en service HTTP "
                               "(Docker/uv/add-on HA) avec HOMEASSISTANT_URL+TOKEN, puis mets son URL ci-dessus.")
    return catalog


class McpServerRequest(BaseModel):
    name: str
    command: str = ""
    args: list = []
    env: Dict[str, str] = {}
    url: str = ""
    transport: str = ""
    disabled: bool = False


@router.post("/api/config/mcp/servers")
async def upsert_mcp_server(req: McpServerRequest) -> Dict[str, Any]:
    """Ajoute/met à jour UN serveur MCP (formulaire) et reconnecte à chaud.
    Deux types : DISTANT (url + transport http/sse) OU local (command + args)."""
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de serveur requis.")
    servers = _mcp_raw()
    if (req.url or "").strip():
        # Serveur MCP DISTANT (HTTP/SSE) : url + transport priment sur command/args.
        servers[name] = {"url": req.url.strip(),
                         "transport": (req.transport or "http").strip() or "http",
                         "env": req.env or {}, "disabled": bool(req.disabled)}
    else:
        servers[name] = {"command": req.command.strip(), "args": req.args or [],
                         "env": req.env or {}, "disabled": bool(req.disabled)}
    _mcp_save(servers)
    from tools.mcp_manager import mcp_manager
    try:
        await asyncio.to_thread(mcp_manager.restart)
    except Exception as e:
        return {"status": "saved_with_error", "detail": str(e), "mcp": mcp_manager.status()}
    return {"status": "success", "mcp": mcp_manager.status()}


@router.delete("/api/config/mcp/servers/{name}")
async def delete_mcp_server(name: str) -> Dict[str, Any]:
    servers = _mcp_raw()
    if name not in servers:
        raise HTTPException(status_code=404, detail="Serveur introuvable.")
    servers.pop(name, None)
    _mcp_save(servers)
    from tools.mcp_manager import mcp_manager
    try:
        await asyncio.to_thread(mcp_manager.restart)
    except Exception as e:
        return {"status": "saved_with_error", "detail": str(e)}
    return {"status": "success", "mcp": mcp_manager.status()}


@router.get("/api/user-profile")
async def get_user_profile() -> Dict[str, str]:
    """Profil utilisateur évolutif (texte curé réinjecté dans le prompt)."""
    try:
        from core.user_profile import user_profile
        return {"profile": user_profile.get()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UserProfileRequest(BaseModel):
    profile: str = ""

@router.post("/api/user-profile")
async def set_user_profile(req: UserProfileRequest) -> Dict[str, str]:
    """Édition manuelle du profil utilisateur."""
    try:
        from core.user_profile import user_profile
        user_profile.set(req.profile or "")
        return {"status": "success", "profile": user_profile.get()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class NotifyTestRequest(BaseModel):
    channel: str = ""

@router.post("/api/notify/test")
async def notify_test(req: NotifyTestRequest) -> Dict[str, Any]:
    """Envoie un message de test sur les messageries (ou un canal précis)."""
    try:
        from core.notifications import notify, configured_channels
        ch = (req.channel or "").strip().lower() or None
        sent = notify(f"✅ Test de notification depuis {_app_name()}.", title=f"{_app_name()} — test", channel=ch)
        return {"sent": sent, "configured": configured_channels()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/notify/channels")
async def notify_channels() -> Dict[str, Any]:
    """Liste les canaux de messagerie actuellement configurés."""
    try:
        from core.notifications import configured_channels
        return {"configured": configured_channels()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/config/env")
async def get_config_env() -> Dict[str, str]:
    try:
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
            "HOST", "PORT", "ALLOWED_ORIGINS", "ACTIVE_WORKSPACE_DIR",
            "SANDBOX_MODE", "SANDBOX_DOCKER_IMAGE",
            "SELF_IMPROVE", "AUTO_APPROVE_SENSITIVE", "SENSITIVE_TOOLS",
            "LLM_MAX_RETRIES", "SWARM_MAX_SECONDS", "SWARM_MAX_TOKENS", "SWARM_MAX_PARALLEL",
            "MEMORY_MAX_MESSAGES", "MEMORY_KEEP_RECENT", "LOG_LEVEL",
            "SESSION_TTL_HOURS", "TELEGRAM_REQUIRE_PAIRING",
            "VOICE_EMOTION_TAGS", "VOICE_TTS_HTTP_URL", "VOICE_TTS_VOICE",
            "PRESENCE_ENTITY", "N8N_WORKFLOWS",
            "DELEGATION_ROUTER", "FAST_MODEL", "FALLBACK_MODELS", "AUTO_CRITIC",
            "USER_MODELING", "SELF_IMPROVE_SKILLS", "TOOL_SCRIPTS", "PROMPT_CACHE",
            "EXPERIENCE_MAX", "DOC_MAX_CHUNKS",
            "DISCORD_WEBHOOK_URL", "SLACK_WEBHOOK_URL", "NOTIFY_WEBHOOK_URL",
            "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
            "SMTP_FROM", "SMTP_SSL", "NOTIFY_EMAIL_TO",
        ]
        for k in typical_keys:
            if k not in masked_env:
                masked_env[k] = ""
        return masked_env
    except Exception as e:
        import logging
        logging.exception("Erreur récupération .env")
        raise HTTPException(status_code=500, detail=str(e))

class SaveEnvRequest(BaseModel):
    env: Dict[str, str]

@router.post("/api/config/env")
async def save_config_env(req: SaveEnvRequest) -> Dict[str, str]:
    try:
        current_env = parse_env()
        updates = {}
        for k, v in req.env.items():
            if "..." in v or v == "***" or (not v and k in current_env and current_env[k]):
                continue
            updates[k] = v

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
        import logging
        logging.exception("Erreur sauvegarde .env")
        raise HTTPException(status_code=500, detail=f"Erreur d'écriture dans le .env : {str(e)}")

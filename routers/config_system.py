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

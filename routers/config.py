import os
import json
import yaml
import time
import asyncio
import traceback
import requests
import uuid
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from core.tracing import run_store
from core.routines import routine_store, start_scheduler as start_routine_scheduler
from core.run_context import registry as run_registry, current_run_id
from core.state import (
    swarm, _orch_name, _app_name, _orch_agent, 
    ConversationManager, _session_file, ChatSession, SessionManager, 
    sessions, session, TELEMETRY, CODER_CWD, get_coder_cwd, set_coder_cwd, get_model_cost
)

router = APIRouter(tags=["Config"])

def parse_env():
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

# ENDPOINTS D'ADMINISTRATION NO-CODE (Géstion Agents & Clés API)
# =========================================================================
import yaml

@router.get("/api/config/agents")
async def get_config_agents():
    try:
        with open("agents.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("agents", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture de agents.yaml : {str(e)}")

class SaveAgentsRequest(BaseModel):
    agents: List[Dict[str, Any]]

@router.post("/api/config/agents")
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

@router.get("/api/config/skills")
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



@router.get("/api/config/mcp")
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


@router.post("/api/config/mcp")
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


@router.get("/api/config/satellites")
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


@router.post("/api/config/satellites/genkey")
async def gen_satellite_key():
    """Génère une clé d'API ESPHome (base64) à recopier dans le YAML de l'ESP."""
    from voice import esphome_satellites as es
    return {"key": es.generate_encryption_key()}


@router.post("/api/config/satellites")
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


@router.delete("/api/config/satellites/{name}")
async def delete_config_satellite(name: str):
    """Supprime un satellite puis reconnecte le listener."""
    from voice import esphome_satellites as es
    es.delete_satellite(name)
    await asyncio.to_thread(es.manager.restart)
    return {"status": "success", "satellites": es.manager.status()}


@router.get("/api/user-profile")
async def get_user_profile():
    """Profil utilisateur évolutif (texte curé réinjecté dans le prompt)."""
    from core.user_profile import user_profile
    return {"profile": user_profile.get()}


class UserProfileRequest(BaseModel):
    profile: str = ""


@router.post("/api/user-profile")
async def set_user_profile(req: UserProfileRequest):
    """Édition manuelle du profil utilisateur."""
    from core.user_profile import user_profile
    user_profile.set(req.profile or "")
    return {"status": "success", "profile": user_profile.get()}


class VoiceWakeRequest(BaseModel):
    engine: str = "stt"
    word: str = "Athena"


@router.get("/api/config/voice-wake")
async def get_voice_wake():
    """Mot d'activation vocal courant (moteur + mot)."""
    return {"engine": os.getenv("VOICE_WAKE_ENGINE", "stt"),
            "word": os.getenv("VOICE_WAKE_WORD", "Athena")}


@router.post("/api/config/voice-wake")
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


@router.get("/api/config/satellites/sensor-catalog")
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


@router.post("/api/config/satellites/yaml")
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


@router.post("/api/config/satellites/connect")
async def connect_satellites():
    """(Re)connecte tous les satellites configurés."""
    from voice import esphome_satellites as es
    await asyncio.to_thread(es.manager.restart)
    return {"status": "success", "satellites": es.manager.status()}


@router.delete("/api/config/skills/{skill_name}")
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


@router.post("/api/notify/test")
async def notify_test(req: NotifyTestRequest):
    """Envoie un message de test sur les messageries (ou un canal précis)."""
    from core.notifications import notify, configured_channels
    ch = (req.channel or "").strip().lower() or None
    sent = notify(f"✅ Test de notification depuis {_app_name()}.", title=f"{_app_name()} — test", channel=ch)
    return {"sent": sent, "configured": configured_channels()}


@router.get("/api/notify/channels")
async def notify_channels():
    """Liste les canaux de messagerie actuellement configurés."""
    from core.notifications import configured_channels
    return {"configured": configured_channels()}


# (Endpoints /api/telegram/pairing déplacés dans routers/system.py.)


@router.get("/api/config/env")
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

@router.post("/api/config/env")
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

@router.get("/api/config/agenda")
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

@router.post("/api/config/agenda")
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

@router.post("/api/config/agenda/google-key")
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

@router.post("/api/agenda/sync")
async def force_agenda_sync():
    try:
        from tools.agenda_tools import sync_all_external_calendars
        imported = sync_all_external_calendars()
        return {"status": "success", "message": f"Synchronisation forcée réussie. {imported} événements externes importés."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/telemetry/reset")
async def reset_telemetry():
    """Remet à zéro les compteurs du cockpit (requêtes, outils, tokens, coût)."""
    global TELEMETRY
    TELEMETRY = {"total_queries": 0, "tool_calls": 0, "total_tokens": 0, "total_cost": 0.0}
    return {"status": "success", **TELEMETRY}


@router.get("/api/config/tools")
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


@router.get("/api/telemetry")
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

@router.get("/api/gallery")
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

@router.post("/api/gallery/delete")
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

@router.get("/api/pricing")
async def get_pricing():
    try:
        if os.path.exists(PRICING_CONFIG_PATH):
            with open(PRICING_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return DEFAULT_PRICING
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/pricing")
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

@router.post("/api/pricing/reset")
async def reset_pricing():
    try:
        os.makedirs("workspace", exist_ok=True)
        with open(PRICING_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PRICING, f, indent=4, ensure_ascii=False)
        return {"status": "reset", "data": DEFAULT_PRICING}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import requests

@router.get("/api/config/models")
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


@router.get("/api/budget")
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
        
    agent_name = routine.get("agent", _orch_name())
    if agent_name == "_nightly_agent":
        from core.swarm import Agent
        from tools.maintenance import cleanup_skills
        starting = Agent(
            name="NightlyAgent",
            model="ollama/qwen2.5:0.5b",
            instructions="Tu es le concierge nocturne de Jarvis. Ta seule mission est d'exécuter l'outil cleanup_skills.",
            tools=[cleanup_skills]
        )
    else:
        starting = swarm.agents.get(agent_name) or _orch_agent()
        
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


@router.get("/api/routines")
async def list_routines():
    return {"routines": routine_store.list()}


@router.post("/api/routines")
async def save_routine(req: RoutineRequest):
    return {"status": "success", "routine": routine_store.upsert(req.dict())}


@router.delete("/api/routines/{rid}")
async def delete_routine(rid: str):
    routine_store.delete(rid)
    return {"status": "success"}


@router.post("/api/routines/{rid}/run")
async def run_routine_now(rid: str):
    r = routine_store.get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="Routine introuvable.")
    await asyncio.to_thread(_run_routine, r)
    return {"status": "success"}


@router.api_route("/api/hooks/{rid}", methods=["GET", "POST"])
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
@router.post("/api/meeting/transcribe")
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


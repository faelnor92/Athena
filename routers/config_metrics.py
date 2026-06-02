import os
import json
import requests
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, UploadFile, File

from core.state import TELEMETRY

router = APIRouter(tags=["Config Metrics & UI"])

@router.post("/api/telemetry/reset")
async def reset_telemetry() -> Dict[str, Any]:
    """Remet à zéro les compteurs du cockpit (requêtes, outils, tokens, coût)."""
    global TELEMETRY
    TELEMETRY.update({"total_queries": 0, "tool_calls": 0, "total_tokens": 0, "total_cost": 0.0})
    return {"status": "success", **TELEMETRY}


@router.get("/api/budget")
async def get_budget() -> Dict[str, Any]:
    """Coût cumulé du jour et limite configurée (BUDGET_DAILY_LIMIT)."""
    from core.tracing import run_store
    try:
        limit = float(os.getenv("BUDGET_DAILY_LIMIT", "0") or 0)
    except ValueError:
        limit = 0.0
    return {"today": run_store.cost_today(), "limit": limit}

def _parse_env_local() -> Dict[str, str]:
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip("'\"")
    return env_vars

@router.get("/api/telemetry")
async def get_telemetry() -> Dict[str, Any]:
    try:
        env = _parse_env_local()
        has_google = os.path.exists("workspace/google_credentials.json")
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
                
        has_ha = bool(env.get("HA_URL") and env.get("HA_TOKEN"))
        
        return {
            "total_queries": TELEMETRY.get("total_queries", 0),
            "tool_calls": TELEMETRY.get("tool_calls", 0),
            "total_tokens": TELEMETRY.get("total_tokens", 0),
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
async def get_media_gallery() -> List[Dict[str, Any]]:
    try:
        images_dir = "workspace/generated_images"
        videos_dir = "workspace/generated_videos"
        gallery = []
        
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
                    
        gallery.sort(key=lambda x: x["time"], reverse=True)
        return gallery
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel
class DeleteMediaRequest(BaseModel):
    path: str

@router.post("/api/gallery/delete")
async def delete_gallery_media(req: DeleteMediaRequest) -> Dict[str, str]:
    try:
        normalized = os.path.normpath(req.path)
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
async def get_pricing() -> Dict[str, Dict[str, float]]:
    try:
        if os.path.exists(PRICING_CONFIG_PATH):
            with open(PRICING_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return DEFAULT_PRICING
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/pricing")
async def save_pricing(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
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
async def reset_pricing() -> Dict[str, Any]:
    try:
        os.makedirs("workspace", exist_ok=True)
        with open(PRICING_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PRICING, f, indent=4, ensure_ascii=False)
        return {"status": "reset", "data": DEFAULT_PRICING}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/config/models")
async def list_available_models() -> Dict[str, List[str]]:
    env = _parse_env_local()
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
            "ollama/llama3", "ollama/llama3.1", "ollama/llama3.3", "ollama/deepseek-r1",
            "ollama/mistral", "ollama/qwen2.5", "ollama/phi3", "ollama/gemma2"
        ],
        "Qwen Cloud (Dashscope)": ["dashscope/qwen-max", "dashscope/qwen-plus", "dashscope/qwen-turbo", "dashscope/qwen-long", "dashscope/qwen2.5-72b-instruct", "dashscope/qwen2.5-14b-instruct", "dashscope/qwen2.5-7b-instruct"],
    }
    
    openai_key = env.get("OPENAI_API_KEY")
    if openai_key:
        try:
            r = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {openai_key}"}, timeout=2)
            if r.status_code == 200:
                openai_models = [m['id'] for m in r.json().get("data", []) if "gpt" in m['id']]
                if openai_models:
                    models["OpenAI"] = sorted(openai_models)
        except Exception:
            pass

    anthropic_key = env.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            r = requests.get("https://api.anthropic.com/v1/models", headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"}, timeout=2)
            if r.status_code == 200:
                anth_models = [m['id'] for m in r.json().get("data", [])]
                if anth_models:
                    models["Anthropic Claude"] = sorted(anth_models)
        except Exception:
            pass

    openrouter_key = env.get("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            r = requests.get("https://openrouter.ai/api/v1/models", timeout=3)
            if r.status_code == 200:
                or_models = [m['id'] for m in r.json().get("data", [])]
                if or_models:
                    models["OpenRouter (Full Catalog)"] = sorted(or_models)
        except Exception:
            pass

    ollama_base = env.get("OLLAMA_API_BASE", "http://localhost:11434")
    try:
        r = requests.get(f"{ollama_base}/api/tags", timeout=1)
        if r.status_code == 200:
            local_models = [f"ollama/{m['name']}" for m in r.json().get("models", [])]
            if local_models:
                models["Ollama (Modèles installés)"] = sorted(local_models)
    except Exception:
        pass

    custom_base = env.get("CUSTOM_LLM_API_BASE")
    custom_key = env.get("CUSTOM_LLM_API_KEY", "")
    if custom_base:
        try:
            headers = {"Authorization": f"Bearer {custom_key}"} if custom_key else {}
            url = f"{custom_base}/models" if not custom_base.endswith("/v1") else f"{custom_base}/models"
            r = requests.get(url, headers=headers, timeout=2)
            if r.status_code == 200:
                c_models = [f"custom/{m['id']}" for m in r.json().get("data", [])]
                if c_models:
                    models["Serveur Custom"] = sorted(c_models)
        except Exception:
            pass

    return models

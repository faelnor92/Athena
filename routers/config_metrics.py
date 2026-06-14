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
    # On cherche .env d'abord dans le cwd, puis à la racine du projet (parent de routers/).
    # Indispensable quand le serveur est lancé depuis un autre dossier (nohup, wrapper,
    # service) : sans ça le .env n'est pas trouvé et la liste des modèles tombe vide.
    candidates = [".env", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")]
    seen = set()
    for path in candidates:
        ap = os.path.abspath(path)
        if ap in seen or not os.path.exists(ap):
            continue
        seen.add(ap)
        with open(ap, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars.setdefault(k.strip(), v.strip("'\""))
        break
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
    # On lit le .env ET l'environnement live (l'UI écrit dans .env, mais une variable
    # passée au process sans être dans .env doit quand même compter).
    env = {**_parse_env_local()}
    for k in ("CUSTOM_LLM_API_BASE", "CUSTOM_LLM_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
              "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "OLLAMA_API_BASE"):
        v = os.environ.get(k)
        if v and not (env.get(k) or "").strip():
            env[k] = v
    models: Dict[str, List[str]] = {}

    # --- Endpoint CUSTOM (OpenAI-compatible) EN PREMIER : on liste ses modèles en direct.
    #     Cas d'usage principal (vLLM/LM Studio/Open WebUI/LiteLLM…). On essaie plusieurs
    #     chemins car les serveurs n'exposent pas tous /v1/models.
    custom_base = (env.get("CUSTOM_LLM_API_BASE") or "").rstrip("/")
    custom_key = env.get("CUSTOM_LLM_API_KEY", "")
    if custom_base:
        base_v1 = custom_base if custom_base.endswith("/v1") else custom_base + "/v1"
        root = custom_base[:-3].rstrip("/") if custom_base.endswith("/v1") else custom_base
        headers = {"Authorization": f"Bearer {custom_key}"} if custom_key else {}
        # OpenAI-compat (/v1/models, /models) puis Ollama (/api/tags) et Open WebUI (/api/models)
        candidates = [f"{base_v1}/models", f"{root}/models",
                      f"{root}/api/models", f"{root}/api/tags"]
        seen = set()
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            try:
                r = requests.get(url, headers=headers, timeout=4)
                if r.status_code != 200:
                    continue
                payload = r.json()
                # Formats : {"data":[{"id":..}]} (OpenAI) ; {"models":[{"name":..}]} (Ollama) ; [..]
                if isinstance(payload, dict):
                    data = payload.get("data") or payload.get("models") or []
                else:
                    data = payload
                ids = []
                for m in (data or []):
                    if isinstance(m, dict):
                        mid = m.get("id") or m.get("name") or m.get("model")
                    else:
                        mid = m
                    if mid:
                        ids.append(f"custom/{mid}")
                c_models = sorted(set(ids))
                if c_models:
                    models["⭐ Serveur Custom (ton endpoint)"] = c_models
                    break
            except Exception:
                continue

    # --- Catalogue STATIQUE par fournisseur cloud : ajouté UNIQUEMENT si la clé du
    #     fournisseur est présente (sinon une longue liste de modèles inaccessibles).
    catalog = {
        "OPENAI_API_KEY": ("OpenAI", ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini"]),
        "ANTHROPIC_API_KEY": ("Anthropic Claude", ["anthropic/claude-3-5-sonnet-20241022", "anthropic/claude-3-5-haiku-20241022", "anthropic/claude-3-opus-20240229"]),
        "GEMINI_API_KEY": ("Google Gemini", ["gemini/gemini-2.5-pro", "gemini/gemini-2.5-flash", "gemini/gemini-1.5-pro"]),
        "GROQ_API_KEY": ("Groq", ["groq/llama-3.3-70b-versatile", "groq/llama-3.1-8b-instant", "groq/mixtral-8x7b-32768"]),
        "MISTRAL_API_KEY": ("Mistral AI", ["mistral/mistral-large-latest", "mistral/mistral-small-latest", "mistral/codestral-latest"]),
    }
    for key_name, (label, lst) in catalog.items():
        if (env.get(key_name) or "").strip():
            models[label] = lst

    # Listes LIVE (remplacent le statique) si la clé est présente.
    openai_key = env.get("OPENAI_API_KEY")
    if openai_key:
        try:
            r = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {openai_key}"}, timeout=3)
            if r.status_code == 200:
                om = sorted(m['id'] for m in r.json().get("data", []) if "gpt" in m['id'] or m['id'].startswith("o"))
                if om:
                    models["OpenAI"] = om
        except Exception:
            pass

    anthropic_key = env.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            r = requests.get("https://api.anthropic.com/v1/models", headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"}, timeout=3)
            if r.status_code == 200:
                am = sorted(m['id'] for m in r.json().get("data", []))
                if am:
                    models["Anthropic Claude"] = am
        except Exception:
            pass

    openrouter_key = env.get("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            r = requests.get("https://openrouter.ai/api/v1/models", timeout=3)
            if r.status_code == 200:
                orm = sorted(m['id'] for m in r.json().get("data", []))
                if orm:
                    models["OpenRouter"] = orm
        except Exception:
            pass

    # Ollama local : ajouté seulement s'il est joignable.
    ollama_base = (env.get("OLLAMA_API_BASE", "http://localhost:11434") or "").rstrip("/")
    try:
        r = requests.get(f"{ollama_base}/api/tags", timeout=1)
        if r.status_code == 200:
            lm = sorted(f"ollama/{m['name']}" for m in r.json().get("models", []))
            if lm:
                models["Ollama (installés)"] = lm
    except Exception:
        pass

    # Filet de sécurité : si RIEN n'a été détecté (pas de clé cloud, endpoint custom
    # injoignable au moment de l'appel), on propose quand même une courte liste de
    # raccourcis courants — le champ reste un texte libre, donc l'utilisateur peut
    # toujours saisir n'importe quel modèle. Jamais de liste vide.
    if not models:
        models["⚡ Courants (saisie libre possible)"] = [
            "gpt-4o", "gpt-4o-mini",
            "anthropic/claude-3-5-sonnet-20241022", "anthropic/claude-3-5-haiku-20241022",
            "gemini/gemini-2.5-flash",
            "custom/(ton-modèle)",
        ]

    return models

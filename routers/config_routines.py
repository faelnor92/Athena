import os
import json
import uuid
import base64
import secrets
import asyncio
import requests
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from pydantic import BaseModel

from core.tracing import run_store
from core.run_context import registry as run_registry, current_run_id
from core.routines import routine_store, start_scheduler as start_routine_scheduler
from core import channels, approvals
import time
from core.state import swarm, _orch_name, _orch_agent

_budget_alert_date = ""

def broadcast_notification(message: str, title: str = None):
    print(f"\033[93m📣 [Notification]\033[0m {message}")
    try:
        from core.notifications import notify
        notify(message, title=title)
    except Exception as e:
        print(f"[Notification erreur] {e}")

def _check_budget():
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
            title="Alerte Budget Athena"
        )

def _run_routine(routine: dict):
    import logging
    logger = logging.getLogger("athena.routines")

    # Pont Workflow : une routine peut déclencher un pipeline déterministe (au lieu d'un
    # prompt). Exécuté dans le contexte du propriétaire ; le prompt sert d'entrée initiale.
    pid = routine.get("pipeline_id")
    if pid:
        from core.pipelines import pipeline_store
        from tools.pipeline_tools import run_pipeline
        from core.state import _current_username
        owner = routine.get("owner") or "local"
        utok = _current_username.set(owner)
        try:
            p = pipeline_store.get(pid)
            if not p or (p.get("owner") or "local") != owner:
                logger.warning("routine '%s' : pipeline %s introuvable", routine.get("name"), pid)
                return
            res = run_pipeline(p, routine.get("prompt") or "")
            if routine.get("notify", True):
                msg = res.get("error") or res.get("final") or "Workflow terminé."
                broadcast_notification(msg, title=f"🛠️ {routine.get('name', p.get('name'))}")
        except Exception:
            logger.exception("Erreur pipeline routine '%s'", routine.get("name"))
        finally:
            _current_username.reset(utok)
        return

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
            instructions="Tu es le concierge nocturne de Athena. Ta seule mission est d'exécuter l'outil cleanup_skills.",
            tools=[cleanup_skills]
        )
    else:
        starting = swarm.agents.get(agent_name) or _orch_agent()

    rid = run_store.new_run_id()
    started = time.time()
    token = current_run_id.set(rid)
    run_registry.start(rid)
    chan_token = channels.current_channel.set("routine")
    appr_token = approvals.auto_approve_var.set(True)
    # Exécuter la routine DANS LE CONTEXTE DE SON PROPRIÉTAIRE (agenda/mémoire/notifs
    # de cet utilisateur). Sans propriétaire (routines historiques) → "local".
    from core.state import _current_username
    user_token = _current_username.set(routine.get("owner") or "local")
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
        _current_username.reset(user_token)


router = APIRouter(tags=["Config Routines & Transcribe"])

class RoutineRequest(BaseModel):
    id: str = None
    name: str
    prompt: str = ""
    agent: str = ""
    schedule: Dict[str, Any]
    enabled: bool = True
    notify: bool = True
    secret: str = None
    pipeline_id: str = None  # si défini : la routine déclenche ce workflow déterministe

def _me() -> str:
    from core.user_config import current_user_key
    return current_user_key()


def _owned_or_404(rid: str):
    """Récupère une routine SI elle appartient à l'utilisateur courant, sinon 404."""
    r = routine_store.get(rid)
    if not r or (r.get("owner") or "local") != _me():
        raise HTTPException(status_code=404, detail="Routine introuvable.")
    return r


@router.get("/api/routines")
async def list_routines() -> Dict[str, Any]:
    me = _me()
    return {"routines": [r for r in routine_store.list() if (r.get("owner") or "local") == me]}

@router.post("/api/routines")
async def save_routine(req: RoutineRequest) -> Dict[str, Any]:
    data = req.model_dump()
    # Empêche de détourner la routine d'un autre utilisateur : on (ré)affecte au courant.
    if data.get("id"):
        existing = routine_store.get(data["id"])
        if existing and (existing.get("owner") or "local") != _me():
            raise HTTPException(status_code=404, detail="Routine introuvable.")
    data["owner"] = _me()
    return {"status": "success", "routine": routine_store.upsert(data)}

@router.delete("/api/routines/{rid}")
async def delete_routine(rid: str) -> Dict[str, str]:
    _owned_or_404(rid)
    routine_store.delete(rid)
    return {"status": "success"}

@router.post("/api/routines/{rid}/run")
async def run_routine_now(rid: str) -> Dict[str, str]:
    r = _owned_or_404(rid)
    await asyncio.to_thread(_run_routine, r)
    return {"status": "success"}

@router.api_route("/api/hooks/{rid}", methods=["GET", "POST"])
async def trigger_hook(rid: str, request: Request, token: str = None) -> Dict[str, str]:
    r = routine_store.get(rid)
    if not r or (r.get("schedule") or {}).get("type") != "webhook":
        raise HTTPException(status_code=404, detail="Webhook introuvable.")
    secret = r.get("secret", "") or ""
    provided = token or request.headers.get("X-Hook-Secret", "")
    if secret and not secrets.compare_digest(provided, secret):
        raise HTTPException(status_code=403, detail="Secret de webhook invalide.")
    if not r.get("enabled", True):
        raise HTTPException(status_code=403, detail="Webhook désactivé.")

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

# Lancement du planificateur
start_routine_scheduler(_run_routine)

@router.post("/api/meeting/transcribe")
async def transcribe_meeting(file: UploadFile = File(...)) -> Dict[str, Any]:
    try:
        content = await file.read()
        mime_type = file.content_type or "audio/mp3"
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        
        local_whisper_available = False
        try:
            import whisper
            local_whisper_available = True
        except ImportError:
            pass

        if local_whisper_available:
            print("🎙️ [Meeting API] Utilisation de Whisper local (Modèle 'base')...")
            os.makedirs("workspace", exist_ok=True)
            temp_filename = f"workspace/temp_{uuid.uuid4().hex}_{file.filename}"
            with open(temp_filename, "wb") as f:
                f.write(content)
            
            try:
                model = whisper.load_model("base")
                result = model.transcribe(temp_filename)
                raw_text = result.get("text", "").strip()
            finally:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                    
            custom_base = os.environ.get("CUSTOM_LLM_API_BASE", "").strip()
            custom_key = os.environ.get("CUSTOM_LLM_API_KEY", "").strip()
            
            secretaire_model = "qwen3"
            secretaire_instructions = "Tu es un secrétaire expert en analyse et transcription de réunions."
            
            from core.state import swarm
            secretaire_agent = swarm.agents.get("Secretaire")
            if secretaire_agent:
                secretaire_model = secretaire_agent.model
                secretaire_instructions = secretaire_agent.system_prompt
                
            def clean_and_parse_json(text):
                text = text.strip()
                if text.startswith("```"):
                    first_line_end = text.find("\n")
                    if first_line_end != -1:
                        text = text[first_line_end:].strip()
                    if text.endswith("```"):
                        text = text[:-3].strip()
                try:
                    return json.loads(text)
                except Exception as e:
                    start_idx = text.find("{")
                    end_idx = text.rfind("}")
                    if start_idx != -1 and end_idx != -1:
                        try:
                            return json.loads(text[start_idx:end_idx+1])
                        except Exception:
                            pass
                    raise e

            system_prompt = (
                f"{secretaire_instructions}\n\n"
                "--- DIRECTIVES DE STRUCTURATION ET DE DIARISATION ABSOLUES ---\n"
                "1. DIARISATION (IDENTIFICATION DES LOCUTEURS) :\n"
                "   - Tu dois séparer intelligemment le texte brut en un dialogue de répliques distinctes.\n"
                "   - Identifie précisément qui parle d'après le contexte des phrases.\n"
                "2. COMPTE-RENDU (RÉSUMÉ EXÉCUTIF) :\n"
                "   - Rédige un compte-rendu complet, formel et extrêmement professionnel en Markdown dans la clé 'summary'.\n"
                "3. FORMAT DE RÉPONSE :\n"
                "   - Réponds obligatoirement sous forme d'un objet JSON valide contenant EXACTEMENT ces deux clés :\n"
                "     {\n"
                '       "transcript": [\n'
                '         { "speaker": "Nom/Label Locuteur", "text": "phrase exacte" },\n'
                "         ...\n"
                '       ],\n'
                '       "summary": "Compte-rendu complet en Markdown"\n'
                "     }\n"
            )
            
            if custom_base and custom_key:
                if "/v1" in custom_base and not "/api" in custom_base:
                    custom_base = custom_base.replace("/v1", "/api/v1")
                url_gpt = f"{custom_base}/chat/completions"
                headers_gpt = {
                    "Authorization": f"Bearer {custom_key}",
                    "Content-Type": "application/json"
                }
                payload_gpt = {
                    "model": secretaire_model,
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
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
                headers = {"Content-Type": "application/json"}
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\nVoici le texte brut :\n\n{raw_text}"}]}],
                    "generationConfig": {"responseMimeType": "application/json"}
                }
                r = requests.post(url, json=payload, headers=headers, timeout=90)
                if r.status_code == 200:
                    res_data = r.json()
                    text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
                    return clean_and_parse_json(text_response)
                else:
                    raise Exception(f"Erreur API Gemini (HTTP {r.status_code}) : {r.text}")
            else:
                return {
                    "transcript": [{"speaker": "Transcription brute locale", "text": raw_text}],
                    "summary": f"### 📝 Transcription de Réunion (Brute et locale)\n\n{raw_text}"
                }

        elif gemini_key:
            audio_b64 = base64.b64encode(content).decode("utf-8")
            prompt = (
                "Agis en tant que secrétaire de direction et expert en analyse de réunions. "
                "Tu dois absolument me renvoyer une réponse en JSON structuré respectant EXACTEMENT le format suivant :\n"
                "{\n"
                '  "transcript": [\n'
                '    { "speaker": "Locuteur A (ou son nom si identifié)", "text": "sa transcription" },\n'
                "  ],\n"
                '  "summary": "Le compte-rendu complet rédigé en Markdown"\n'
                "}\n"
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"inlineData": {"mimeType": mime_type, "data": audio_b64}}, {"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            r = requests.post(url, json=payload, headers=headers, timeout=120)
            if r.status_code == 200:
                res_data = r.json()
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text_response)
            else:
                raise Exception(f"Erreur API Gemini (HTTP {r.status_code}) : {r.text}")

        elif openai_key:
            url_whisper = "https://api.openai.com/v1/audio/transcriptions"
            headers_whisper = {"Authorization": f"Bearer {openai_key}"}
            files = {"file": (file.filename, content, mime_type), "model": (None, "whisper-1")}
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
                    "Réponds impérativement avec un objet JSON structuré comme suit :\n"
                    "{\n"
                    '  "transcript": [{ "speaker": "Locuteur A", "text": "phrase" }],\n'
                    '  "summary": "Compte-rendu Markdown"\n'
                    "}"
                )
                payload_gpt = {
                    "model": "gpt-4o",
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Voici le texte brut :\n\n{raw_text}"}]
                }
                r_gpt = requests.post(url_gpt, json=payload_gpt, headers=headers_gpt, timeout=60)
                if r_gpt.status_code == 200:
                    gpt_response = r_gpt.json()["choices"][0]["message"]["content"]
                    return json.loads(gpt_response)
                else:
                    raise Exception(f"Erreur GPT-4o (HTTP {r_gpt.status_code}) : {r_gpt.text}")
            else:
                raise Exception(f"Erreur Whisper (HTTP {r_whisper.status_code}) : {r_whisper.text}")
                
        else:
            await asyncio.sleep(2)
            return {
                "transcript": [{"speaker": "Athena", "text": "Ceci est une simulation locale car aucune API Key n'est présente."}],
                "summary": "### Simulation Locale\n\nAucune API configurée pour la transcription."
            }
    except Exception as e:
        import logging
        logging.exception("Erreur transcription")
        return {"error": str(e)}

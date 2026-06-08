import os
import json
import time
import asyncio
import functools
import re
import threading
import traceback
import uuid
import contextvars
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from core import run_context, approvals, channels
from core.tracing import run_store
from core.run_context import registry as run_registry, current_run_id
from core.state import (
    swarm, _orch_name, _app_name, _orch_agent, 
    ConversationManager, _session_file, ChatSession, SessionManager, 
    sessions, session, TELEMETRY, CODER_CWD, get_coder_cwd, set_coder_cwd, get_model_cost
)
from routers.config_routines import _check_budget

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    parent_id: Optional[str] = None
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
            # Pour éviter les faux positifs (ex: "je suis développeur" routé vers le Codeur),
            # on ne force l'agent de départ QUE si l'utilisateur utilise une mention explicite @alias
            m = _re.search(r"@" + _re.escape(alias) + r"\b", last_user_content)
            if m and m.start() < first_mention_idx:
                first_mention_idx = m.start()
                mentioned_agent = agent
    if mentioned_agent:
        return mentioned_agent
    if any(last_user_content.startswith(x) for x in ["bonjour athena", "athena,", "dis athena", "hey athena", "salut athena"]):
        return _orch_agent()
    return starting_agent


def _chat_prepare(sess, req, run_id):
    """Ajoute le message utilisateur, reconstruit la chaîne et choisit l'agent.
    Renvoie (chain, starting_agent, original_chain_len)."""
    parent_id = req.parent_id if req.parent_id is not None else sess.active_node_id
    user_msg_id = uuid.uuid4().hex
    msgs = sess.messages
    msgs.append({"id": user_msg_id, "parent_id": parent_id, "role": "user", "content": req.message})
    sess.messages = msgs
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
    msgs = sess.messages
    for msg in new_chain[original_chain_len:]:
        new_id = uuid.uuid4().hex
        msgs.append({"id": new_id, "parent_id": prev_id, **msg})
        prev_id = new_id
    sess.messages = msgs
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


@router.post("/api/chat", response_model=ChatResponse)
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


@router.post("/api/structured")
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
    callback_url: Optional[str] = None
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


@router.post("/api/chat/async")
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


@router.get("/api/chat/async/{task_id}")
async def chat_async_status(task_id: str):
    with _ASYNC_LOCK:
        task = ASYNC_TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche inconnue ou expirée.")
    return {"task_id": task_id, **task}


# Plan d'action : extrait en routeur dédié (routers/plan.py).



@router.post("/api/chat/stream")
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

@router.get("/api/chat/status")
async def get_chat_status(run_id: str = None):
    # Sans run_id : renvoie le dernier run (compat. frontend mono-session).
    # Avec run_id : statut/étapes de ce run précis (utile en concurrence).
    return run_registry.status(run_id)


class ClientReq(BaseModel):
    client_id: str = "web"


@router.post("/api/chat/undo")
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


@router.post("/api/chat/retry")
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


@router.get("/api/sessions/search")
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


@router.get("/api/doctor")
async def doctor():
    """Auto-diagnostic : config, dépendances et services (équivalent 'hermes doctor')."""
    from core.diagnostics import run_diagnostics
    checks = run_diagnostics(swarm)
    ok_count = sum(1 for c in checks if c["ok"])
    return {"checks": checks, "ok": ok_count, "total": len(checks)}


@router.post("/api/chat/attach")
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
            athena = _orch_agent()
            vmodel = os.getenv("VISION_MODEL", "").strip() or (athena.model if athena else "gpt-4o")
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

@router.get("/api/runs")
async def list_runs(limit: int = 50, status: str = None):
    """Liste les derniers runs persistés (résumés) pour le cockpit / debug."""
    return {"runs": run_store.list(limit=limit, status=status)}


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Détail complet d'un run (étapes incluses) pour inspection/rejeu."""
    run = run_store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run introuvable.")
    return run


@router.post("/api/runs/{run_id}/cancel")
async def cancel_run_endpoint(run_id: str):
    """Demande l'annulation d'un run en cours (barge-in vocal / bouton stop).
    L'arrêt est effectif au prochain tour de l'essaim."""
    ok = run_registry.cancel(run_id)
    return {"run_id": run_id, "cancellation_requested": ok}


class SteerRequest(BaseModel):
    message: str


@router.post("/api/runs/{run_id}/steer")
async def steer_run_endpoint(run_id: str, req: SteerRequest):
    """STEERING : envoie une consigne à un run EN COURS pour le réorienter sans le relancer.
    Injectée comme message utilisateur au prochain tour de l'essaim."""
    ok = run_registry.steer(run_id, req.message)
    return {"run_id": run_id, "steering_accepted": ok}


@router.post("/api/runs/{run_id}/replay")
async def replay_run_endpoint(run_id: str):
    """Rejoue le message d'un run et renvoie la comparaison ancien/nouveau."""
    from core.eval import replay_run
    result = await asyncio.to_thread(replay_run, swarm, run_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/api/chat/tree")
async def get_chat_tree():
    return {
        "messages": session.messages,
        "active_node_id": session.active_node_id,
        "active_agent": session.active_agent.name if session.active_agent else _orch_name()
    }

@router.get("/api/conversations")
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

@router.post("/api/conversations/select")
async def select_conversation(req: SelectConvRequest):
    if req.id in session.manager.conversations:
        session.manager.active_id = req.id
        session.manager.save()
        return {"status": "success", "active_id": session.manager.active_id}
    raise HTTPException(status_code=404, detail="Conversation not found")

class NewConvRequest(BaseModel):
    name: Optional[str] = None

@router.post("/api/conversations/new")
async def create_conversation(req: NewConvRequest = None):
    name = req.name if req else None
    cid = session.manager.new_conversation(name)
    return {"status": "success", "id": cid, "name": session.manager.conversations[cid]["name"]}

@router.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    session.manager.delete_conversation(conv_id)
    return {"status": "success", "active_id": session.manager.active_id}

class ForkRequest(BaseModel):
    message_id: str

@router.post("/api/chat/fork")
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
    agent: str = "Codeur"
    project_id: Optional[str] = None  # projet ciblé par la CONSOLE (None = projet courant)
    host_id: Optional[str] = None     # hôte SSH ciblé (None = défaut .env / local)

@router.post("/api/terminal/coder")
async def terminal_coder(req: TerminalRequest):
    if not session.active_agent:
        raise HTTPException(status_code=500, detail=f"{_app_name()} n'est pas initialisé.")

    agent_name = req.agent or "Codeur"
    coder_agent = swarm.agents.get(agent_name)
    if not coder_agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} introuvable.")

    # Suivi de PLAN/TODO (façon Claude Code) : on garantit que l'agent codeur dispose des
    # outils de plan, quelle que soit sa config (agents.yaml éditable par l'utilisateur).
    # Ajout idempotent au toolset de l'agent — comme la carte de projet injectée au runtime.
    import tools.planning_tools as _planning
    _have = {getattr(f, "__name__", "") for f in coder_agent.tools}
    for _pf in (_planning.make_plan, _planning.update_plan_step, _planning.get_plan):
        if _pf.__name__ not in _have:
            coder_agent.tools.append(_pf)

    # Projet ciblé PAR LA CONSOLE : override de contexte (sans toucher le projet global du
    # chat/voix). get_workspace_dir() résoudra ce projet pour CE run uniquement.
    from core import projects as _projects
    _proj = (req.project_id or "").strip() or None
    if _proj:
        _projects.set_override(_proj)

    # Contexte de la CONSOLE codeur : historique DÉDIÉ (isolé du chat principal), propre à
    # l'utilisateur ET au projet, persistant (shared_store, multi-worker). La console garde
    # sa mémoire d'une commande à l'autre sans polluer le chat.
    from core import shared_store
    from core.user_config import current_user_key
    _console_key = f"{current_user_key()}:{_proj or 'global'}"
    chain = list(shared_store.get("coder_console", _console_key) or [])

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
        # 1. Routage SSH : hôte sélectionné dans la console (registre multi-hôtes) OU
        #    hôte unique du .env (rétro-compatible).
        if req.host_id or os.getenv("SSH_HOST"):
            from tools.system_tools import run_ssh_command
            from tools import ssh_hosts as _sshh
            _hid = req.host_id

            if raw_bash_cmd.startswith("cd ") or raw_bash_cmd == "cd":
                # `cd` indépendant PAR HÔTE : run_ssh_command préfixe déjà le cwd suivi de
                # l'hôte (resolve), donc on envoie juste `cd <cible> && pwd` et on mémorise
                # le nouveau chemin pour CE serveur (ssh_hosts.set_cwd).
                target_dir = raw_bash_cmd[3:].strip().strip("'\"") if raw_bash_cmd != "cd" else "~"
                remote_cmd = f"cd {shlex.quote(target_dir)} && pwd"
                stdout_content, stderr_content, rc = run_ssh_command(remote_cmd, host_id=_hid)
                if rc == 0 and stdout_content.strip():
                    new_remote_path = stdout_content.strip()
                    _sshh.set_cwd(new_remote_path, _hid)
                    stdout_content = f"📂 Répertoire distant SSH changé : {new_remote_path}"
                    stderr_content = ""
                else:
                    stdout_content = ""
                    if not stderr_content:
                        stderr_content = f"cd: {target_dir}: Aucun fichier ou dossier de ce type sur l'hôte SSH"
            else:
                stdout_content, stderr_content, rc = run_ssh_command(raw_bash_cmd, host_id=_hid)
                
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
                from tools import dev_container

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
                        elif dev_container.enabled():
                            # CONTENEUR DEV PERSISTANT (par utilisateur+projet) : git, pip/npm et
                            # l'état persistent entre les commandes (vrai terminal de dev). Timeout
                            # plus large (installs). Sous-dossier courant relatif à /work.
                            rel = os.path.relpath(get_coder_cwd(), get_workspace_dir())
                            if rel.startswith("..") or os.path.isabs(rel):
                                rel = "."
                            dc_key = dev_container.sanitize_key(current_user_key(), _proj)
                            _dc_to = int(os.getenv("DEV_CONTAINER_EXEC_TIMEOUT", "180") or 180)
                            stdout_content, stderr_content, _rc = dev_container.exec_bash(
                                dc_key, raw_bash_cmd, timeout=_dc_to, workdir=rel
                            )
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
            {"type": "activation", "agent": coder_agent.name},
            {"type": "tool_call", "agent": coder_agent.name, "tool": "Direct Shell Execution", "args": {"command": raw_bash_cmd}}
        ]
        
        if stdout_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": coder_agent.name,
                "output": stdout_content,
                "stream": "stdout"
            })
            
        if stderr_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": coder_agent.name,
                "output": stderr_content,
                "stream": "stderr"
            })
            
        if not stdout_content and not stderr_content:
            steps.append({
                "type": "terminal_output_direct",
                "agent": coder_agent.name,
                "output": "(Exécution terminée avec succès, aucun retour standard)",
                "stream": "stdout"
            })
            
        return {
            "status": "success",
            "steps": steps,
            "active_node_id": session.active_node_id
        }

    # Sinon, on passe par l'exécution standard de l'Agent Codeur
    chain.append({"role": "user", "content": req.command})

    run_id = run_store.new_run_id()
    run_registry.start(run_id)
    token = current_run_id.set(run_id)
    chan_token = channels.current_channel.set("web")
    # La console codeur est admin-only ET pilotée en direct par l'utilisateur : on
    # AUTO-APPROUVE les outils (sinon chaque git_status/écriture exige une confirmation
    # verbeuse). L'admin qui tape la commande assume l'action ; sandbox + can_write tiennent.
    appr_token = approvals.auto_approve_var.set(True)
    # CONTENEUR DEV PERSISTANT : on l'active pour CE run → les outils bash de l'agent
    # (run_checks, execute_bash_command via sandbox_runner) s'exécutent dans le conteneur
    # du projet (git/pip/npm + état persistent), comme le bash direct de la console.
    from tools import dev_container as _dev_container
    _dc_token = None
    if _dev_container.enabled():
        _dc_token = _dev_container.activate(_dev_container.sanitize_key(current_user_key(), _proj))
    # Scope du PLAN propre à cette console (user+projet) → isolé du plan du chat principal.
    _plan_token = _planning.set_scope(f"coder:{_console_key}")
    # Hôte SSH actif pour CE run (registre multi-hôtes) → l'outil bash de l'agent cible le
    # serveur sélectionné dans la console.
    from tools import ssh_hosts as _ssh_hosts
    _ssh_token = _ssh_hosts.set_active(req.host_id) if req.host_id else None
    # Allowlist/denylist d'outils PAR SESSION (sécurité, configurable par l'admin) : permet
    # de restreindre ce que l'agent codeur peut faire dans la console, sans toucher sa config.
    from core import tool_policy as _tool_policy
    _tp_allow = [t.strip() for t in os.getenv("CODER_CONSOLE_ALLOW_TOOLS", "").split(",") if t.strip()]
    _tp_deny = [t.strip() for t in os.getenv("CODER_CONSOLE_DENY_TOOLS", "").split(",") if t.strip()]
    _tp_token = _tool_policy.set_policy(allow=_tp_allow or None, deny=_tp_deny or None) if (_tp_allow or _tp_deny) else None
    # Tâche de code multi-fichiers : budget de tours généreux (cf. Aider/Hermes ≈ 60-90).
    max_turns = int(os.getenv("CODER_CONSOLE_MAX_TURNS", "60") or 60)
    # REPO-MAP : on donne à l'agent la carte du projet (arbo + symboles) pour qu'il ne code
    # pas « à l'aveugle ». Injecté à l'exécution seulement (pas persisté : éviter bloat/staleness).
    run_chain = chain
    try:
        from tools.repo_map import build_repo_map
        _rmap = build_repo_map()
        if _rmap and len(_rmap) > 20:
            run_chain = [{"role": "system",
                          "content": "Carte du projet actif (pour situer ton travail ; relis les "
                                     "fichiers au besoin) :\n" + _rmap}] + chain
    except Exception:
        pass
    # ÉTAT PARTAGÉ du run (context_variables) : ancre l'agent sur le contexte de code
    # courant (projet, répertoire) — visible dans son préambule et lisible par ses outils.
    _ctx_vars = {}
    try:
        from core.state import get_workspace_dir, get_coder_cwd
        _active = _projects.get_active() if _proj else None
        _ctx_vars["projet"] = (_active or {}).get("name") if _active else (_proj or "workspace de base")
        _rel = os.path.relpath(get_coder_cwd(), get_workspace_dir())
        _ctx_vars["repertoire_courant"] = "." if (_rel == "." or _rel.startswith("..")) else _rel
    except Exception:
        pass
    try:
        # Exécution ciblée sur l'Agent Codeur (thread), verrouillée sur lui.
        next_agent, new_chain, steps = await asyncio.to_thread(
            functools.partial(swarm.run, coder_agent, run_chain, max_turns=max_turns,
                              locked=True, context_variables=_ctx_vars))

        # CODE-TEST-FIX (auto-correction du code) : on lance les vérifications du projet ; en
        # cas d'échec, on renvoie les erreurs au codeur pour qu'il corrige, puis on revérifie
        # (boucle bornée). Équivalent de l'auto-correction du design, model-agnostic.
        try:
            from core import code_autofix
            from tools.dev_tools import run_checks
            from core.state import get_workspace_dir
            if code_autofix.enabled():
                _cmd = code_autofix.detect_check_command(get_workspace_dir())
                _att = 0
                while _cmd and _att < code_autofix.max_attempts():
                    _checks = await asyncio.to_thread(run_checks, _cmd)
                    steps.append({"type": "tool_output", "agent": coder_agent.name,
                                  "tool": "run_checks", "output": _checks})
                    if code_autofix.checks_passed(_checks):
                        break
                    _att += 1
                    new_chain.append({"role": "user", "content":
                        f"🔧 Code-Test-Fix : les vérifications ont ÉCHOUÉ.\n{_checks[:2000]}\n"
                        "Corrige le code pour les faire passer (n'explique pas, agis)."})
                    next_agent, new_chain, _s2 = await asyncio.to_thread(
                        functools.partial(swarm.run, coder_agent, new_chain, max_turns=max_turns,
                                          locked=True, context_variables=_ctx_vars))
                    steps += _s2
        except Exception:
            import logging
            logging.getLogger("athena.server").exception("Code-Test-Fix échoué")

        # S'assurer de rester sur l'orchestrateur au niveau de la session globale
        session.active_agent = _orch_agent()

        # MÉMOIRE de la console (isolée du chat) : on sauvegarde l'historique, en retirant la
        # carte injectée (messages système) et borné aux 40 derniers messages.
        try:
            persist = [m for m in new_chain if m.get("role") != "system"][-40:]
            shared_store.set("coder_console", _console_key, persist)
        except Exception:
            import logging
            logging.getLogger("athena.server").exception("Persistance console codeur échouée")

        # Transformer les types "message" en "terminal_message" : la console reste séparée
        # du chat principal côté affichage.
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
        if _dc_token is not None:
            _dev_container.deactivate(_dc_token)
        _planning.reset_scope(_plan_token)
        if _ssh_token is not None:
            _ssh_hosts.reset_active(_ssh_token)
        if _tp_token is not None:
            _tool_policy.reset_policy(_tp_token)

# Endpoints mémoire / connaissances / agenda / listes : extraits en routeurs
# dédiés (Single Responsibility). Voir routers/{memory,agenda,lists}.py.



@router.post("/api/reset")
async def reset_chat():
    session.reset()
    return {"status": "success", "message": "La conversation a été réinitialisée."}


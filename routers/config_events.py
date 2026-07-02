"""Bus d'événements + agent Vigie : config (UI), ingress externe, journal.

- GET/POST /api/config/events     → configuration (UI ET via Athena par les outils)
- POST     /api/events            → INGRESS externe (Zabbix/Grafana/HA/SNMP-forwarder…),
                                     authentifié par jeton (pas de session) → enfile l'événement
- GET      /api/events/recent     → journal récent (UI)
- POST     /api/events/test       → émet un événement de test (admin)
"""
import time
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core import events, channels, approvals
from core.state import swarm, _orch_agent, _orch_name, _current_username
from core.run_context import registry as run_registry, current_run_id
from core.tracing import run_store

router = APIRouter(tags=["Events / Vigie"])
logger = logging.getLogger("athena.vigie")


class EventConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    owner_user: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    min_severity: Optional[str] = None
    dedup_window: Optional[int] = None
    auto_investigate: Optional[bool] = None
    ingest_token: Optional[str] = None
    proxmox_monitor: Optional[bool] = None
    proxmox_interval: Optional[int] = None
    proxmox_ram_pct: Optional[int] = None
    proxmox_disk_pct: Optional[int] = None


class EventIn(BaseModel):
    type: str = "event"
    source: str = ""
    severity: str = "info"
    message: str = ""
    data: Optional[Any] = None
    token: str = ""        # repli si pas d'en-tête X-Event-Token


def _masked(cfg: dict) -> dict:
    c = dict(cfg)
    tok = c.get("ingest_token") or ""
    c["ingest_token"] = (f"{tok[:2]}…{tok[-2:]}" if len(tok) > 4 else ("***" if tok else ""))
    return c


@router.get("/api/config/events")
async def get_events_config() -> Dict[str, Any]:
    return _masked(events.config())


@router.post("/api/config/events")
async def set_events_config(req: EventConfigRequest) -> Dict[str, Any]:
    updates = {k: v for k, v in req.dict().items() if v is not None}
    # Ne pas écraser le jeton s'il est masqué.
    if "ingest_token" in updates and ("…" in updates["ingest_token"] or updates["ingest_token"] == "***"):
        updates.pop("ingest_token")
    cfg = events.set_config(updates)
    return {"status": "success", "config": _masked(cfg)}


@router.get("/api/events/recent")
async def recent_events() -> Dict[str, Any]:
    return {"events": events.recent()}


@router.post("/api/events")
async def ingest_event(ev: EventIn, request: Request) -> Dict[str, Any]:
    """INGRESS externe : authentifié par jeton (X-Event-Token ou champ token). Pas de session."""
    cfg = events.config()
    expected = (cfg.get("ingest_token") or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="Ingress désactivé : aucun jeton configuré (Réglages → Événements).")
    provided = (request.headers.get("X-Event-Token") or ev.token or "").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="Jeton d'événement invalide.")
    res = events.submit(ev.dict(exclude={"token"}))
    return res


@router.post("/api/events/test")
async def test_event() -> Dict[str, Any]:
    """Émet un événement de test (pour vérifier le pipeline Vigie de bout en bout)."""
    return events.submit({
        "type": "test", "source": "athena-ui", "severity": "warning",
        "message": "Événement de test : vérification du pipeline Vigie.",
    })


# --- Exécution du Vigie sur un événement (mirroir de _run_routine) -------------
def _deliver(chat_id: str, message: str):
    from core.notifications import broadcast_notification
    if not message:
        return
    try:
        broadcast_notification(message, title="👁️ Vigie")
    except Exception:
        pass
    chat_id = (chat_id or "").strip()
    if chat_id:
        try:
            from core import telegram_bot
            if telegram_bot.is_enabled():
                telegram_bot.send_message(chat_id, "👁️ Vigie\n\n" + message)
        except Exception as e:
            logger.warning("envoi Telegram Vigie échoué : %s", e)


def _run_vigie(rec: dict):
    cfg = events.config()
    owner = cfg.get("owner_user") or "local"
    chat = (cfg.get("telegram_chat_id") or "").strip()
    # Canal Telegram → les alertes ET les validations HITL des actions sensibles y arrivent.
    channel = f"telegram:{chat}" if chat else "events"

    desc = (f"type = {rec.get('type')}\nsource = {rec.get('source')}\n"
            f"sévérité = {rec.get('severity')}\n{rec.get('message')}")
    if rec.get("data"):
        desc += f"\ndonnées : {rec.get('data')}"

    # CORRÉLATION : événements récents (≠ courant, dernière heure) → la Vigie peut diagnostiquer une
    # cause commune (« VM down APRÈS un pic RAM nœud ») au lieu d'analyser l'événement isolé.
    correlation = ""
    try:
        cur_id = rec.get("id")
        recent = [e for e in events.recent()
                  if e.get("id") != cur_id and (time.time() - e.get("ts", 0)) < 3600]
        if recent:
            correlation = "\nÉvénements récents (corrélation possible) :\n" + "\n".join(
                f"- [{e.get('severity', '?')}] {e.get('type')} / {e.get('source')} : "
                f"{(e.get('message') or '')[:100]}" for e in recent[:6]) + "\n"
    except Exception:  # noqa: BLE001
        correlation = ""

    if cfg.get("auto_investigate"):
        # Vigie INTELLIGENTE : investigue (lecture seule) puis DÉCLENCHE la remédiation via HITL.
        invest = (
            "Tu PEUX et DOIS investiguer brièvement EN LECTURE SEULE (ex. proxmox_status, lire un "
            "log) pour CONFIRMER la cause avant d'agir. Puis, SI une remédiation STANDARD et "
            "RÉVERSIBLE s'applique (redémarrer une VM tombée, relancer un service), APPELLE "
            "DIRECTEMENT l'outil correspondant (proxmox_vm_action…) — il sera soumis à TA VALIDATION "
            "(HITL, approbation d'un clic) AVANT toute exécution. NE te contente PAS de décrire "
            "l'action : déclenche-la pour qu'on puisse l'approuver. Une seule remédiation à la fois.")
    else:
        invest = ("N'exécute AUCUN outil : analyse et alerte seulement, et propose le correctif en "
                  "TEXTE (l'auto-remédiation est désactivée).")

    prompt = (
        "[ÉVÉNEMENT SYSTÈME — mode proactif Vigie] Un événement de supervision vient d'arriver :\n"
        f"{desc}\n{correlation}\n"
        "Diagnostique la CAUSE PROBABLE (corrèle avec les événements récents ci-dessus si pertinent) "
        "et l'impact réel, en 2-3 phrases. "
        f"{invest} Sois bref, concret, sans alarmisme inutile."
    )

    rid = run_store.new_run_id()
    started = time.time()
    tok = current_run_id.set(rid)
    run_registry.start(rid)
    chan_tok = channels.current_channel.set(channel)
    # PAS d'auto-approve : une action sensible déclenchera le HITL (validation Telegram).
    appr_tok = approvals.auto_approve_var.set(False)
    usr_tok = _current_username.set(owner)
    try:
        agent, _msgs, steps = swarm.run(_orch_agent(), [{"role": "user", "content": prompt}])
        steps = list(steps)
        resp = next((s.get("content", "") for s in reversed(steps) if s.get("type") == "message"), "")
        run_store.save(run_id=rid, agent=agent.name, status="vigie",
                       user_message=f"[Vigie] {rec.get('type')} / {rec.get('source')}",
                       final_response=resp, duration_ms=int((time.time() - started) * 1000),
                       steps=steps, created_at=started)
        logger.info("événement %s traité (run %s)", rec.get("id"), rid)
        _deliver(chat, resp)
    except Exception:
        logger.exception("Erreur Vigie sur événement %s", rec.get("id"))
    finally:
        # finish AVANT le reset du canal : publie run.completed avec le bon contexte.
        run_registry.finish(rid)
        current_run_id.reset(tok)
        channels.current_channel.reset(chan_tok)
        approvals.auto_approve_var.reset(appr_tok)
        _current_username.reset(usr_tok)


events.start_worker(_run_vigie)

"""File d'approbations ASYNCHRONES (Human-in-the-loop multi-canal).

Pour les actions SENSIBLES déclenchées depuis un canal où l'utilisateur ne regarde pas le
chat en direct (Telegram, voix), au lieu de « demander et s'arrêter », le run se FIGE sur
l'action et pousse une notification ACTIONNABLE. L'utilisateur approuve/refuse depuis son
téléphone (bouton inline Telegram, ou /approve <id> / /deny <id>, ou l'API) → le run
reprend et exécute (ou non) l'outil.

Implémentation : un registre {id -> threading.Event + décision}. Le run tourne dans un
thread (cf. swarm), donc threading.Event convient (pas asyncio). Timeout → refus (sûr).
"""
import os
import threading
import time
import uuid

from core import event_bus

_lock = threading.Lock()
_pending: dict = {}   # id -> {event, decision, tool, args, agent, channel, created}


def _emit(phase: str, aid: str, entry: dict = None, approved: bool = None):
    """Publie une étape du cycle HITL sur le bus d'événements (topic 'approval') → réacteurs
    découplés (audit, notifications…). Best-effort : ne casse jamais le flux d'approbation."""
    try:
        payload = {"phase": phase, "id": aid}
        if entry:
            payload.update({"tool": entry.get("tool"), "agent": entry.get("agent"),
                            "channel": entry.get("channel")})
        if approved is not None:
            payload["approved"] = approved
        event_bus.publish("approval", payload)
    except Exception:
        pass


def async_enabled(channel: str) -> bool:
    """Vrai si l'approbation asynchrone (notif + attente) s'applique à ce canal.
    Par défaut : activée pour les canaux DISTANTS (telegram:, voice:) ; le web reste in-band
    (l'utilisateur voit le chat). Réglable via APPROVAL_ASYNC (true/false)."""
    if os.getenv("APPROVAL_ASYNC", "true").lower() not in ("true", "1", "yes"):
        return False
    ch = (channel or "").lower()
    # Canaux PUSH (l'utilisateur ne regarde pas le chat → notif actionnable + attente).
    # La voix est exclue : l'utilisateur est présent → confirmation in-band (à l'oral).
    remote = ch.startswith(("telegram:", "matrix:"))
    # APPROVAL_ASYNC_ALL=true → asynchrone même sur le web.
    return remote or os.getenv("APPROVAL_ASYNC_ALL", "false").lower() in ("true", "1", "yes")


def request(tool: str, args: dict, agent: str, channel: str) -> str:
    """Crée une demande d'approbation en attente. Renvoie son id court."""
    aid = uuid.uuid4().hex[:6].upper()
    with _lock:
        _pending[aid] = {
            "event": threading.Event(), "decision": None,
            "tool": tool, "args": args or {}, "agent": agent,
            "channel": channel, "created": time.time(),
        }
    _emit("requested", aid, _pending[aid])
    return aid


def resolve(aid: str, approved: bool) -> bool:
    """Approuve (True) ou refuse (False) une demande. Renvoie False si l'id est inconnu."""
    aid = (aid or "").strip().upper()
    with _lock:
        entry = _pending.get(aid)
        if not entry or entry["decision"] is not None:
            return False
        entry["decision"] = "approved" if approved else "denied"
        entry["event"].set()
    _emit("resolved", aid, entry, approved=approved)
    return True


def wait(aid: str, timeout: float) -> str:
    """Bloque jusqu'à décision ou expiration. Renvoie 'approved' | 'denied' | 'timeout'."""
    with _lock:
        entry = _pending.get(aid)
    if not entry:
        return "timeout"
    got = entry["event"].wait(timeout=timeout)
    with _lock:
        decision = _pending.get(aid, {}).get("decision")
        _pending.pop(aid, None)   # nettoyage : une demande ne sert qu'une fois
    if not got or not decision:
        _emit("timeout", aid, entry)
        return "timeout"
    return decision


def pending_list() -> list:
    """Demandes en attente (pour l'UI / les notifications), sans l'objet Event."""
    with _lock:
        return [
            {"id": k, "tool": v["tool"], "args": v["args"], "agent": v["agent"],
             "channel": v["channel"], "age_s": int(time.time() - v["created"])}
            for k, v in _pending.items() if v["decision"] is None
        ]


def timeout_seconds() -> float:
    try:
        return float(os.getenv("APPROVAL_TIMEOUT", "600") or 600)
    except ValueError:
        return 600.0

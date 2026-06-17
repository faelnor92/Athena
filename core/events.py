"""Bus d'ÉVÉNEMENTS + agent « Vigie » — proactivité PILOTÉE PAR ÉVÉNEMENT.

Principe : Athena ne surveille RIEN en boucle. Une source externe (Zabbix, Grafana,
LibreNMS, Home Assistant, trap SNMP via forwarder, ou une routine de poll) POUSSE un
événement sur `POST /api/events`. Un thread worker BLOQUÉ sur une file le reçoit, réveille
l'agent Vigie pour l'analyser (et alerter / proposer un correctif), puis se rendort.

Coût au repos = nul (thread bloqué, aucun appel LLM tant qu'aucun événement n'arrive).

Anti-tempête : filtrage par sévérité minimale + dé-duplication (même type/source/message dans
une fenêtre) + file bornée. Configurable dans l'UI ET par Athena (cf. tools/event_tools.py).
"""
import hashlib
import queue
import threading
import time
import uuid
from collections import deque

from core import shared_store

_NS = "events"
_CFG_KEY = "config"

_SEV_ORDER = {"info": 0, "warning": 1, "critical": 2}

_q: "queue.Queue" = queue.Queue(maxsize=200)
_recent = deque(maxlen=50)        # journal récent (pour l'UI)
_dedup: dict = {}                 # signature -> timestamp
_lock = threading.Lock()
_worker_started = False
_run_cb = None                    # injecté par le routeur (exécute le Vigie)


_DEFAULTS = {
    "enabled": False,
    "owner_user": "local",        # compte sous lequel tourne le Vigie (agenda/mémoire)
    "telegram_chat_id": "",       # destinataire des alertes + validations HITL
    "min_severity": "warning",    # info | warning | critical
    "dedup_window": 300,          # s : ignore un événement identique répété
    "auto_investigate": False,    # autoriser le Vigie à investiguer (outils) vs analyser seul
    "ingest_token": "",           # jeton attendu sur POST /api/events
    # --- Surveillance Proxmox (moniteur interne, sans LLM ; émet des événements) ---
    "proxmox_monitor": False,     # surveiller Proxmox (VM down, RAM/disque, nœud offline)
    "proxmox_interval": 300,      # s : période de vérification
    "proxmox_ram_pct": 90,        # seuil RAM % d'une VM/nœud → alerte
    "proxmox_disk_pct": 90,       # seuil disque % (réel) d'une VM → alerte
}


def config() -> dict:
    cfg = dict(_DEFAULTS)
    cfg.update(shared_store.get(_NS, _CFG_KEY) or {})
    return cfg


def set_config(updates: dict) -> dict:
    def _f(cur):
        cur = dict(cur or {})
        for k, v in (updates or {}).items():
            if k in _DEFAULTS:
                cur[k] = v
        return cur
    shared_store.update(_NS, _CFG_KEY, _f)
    return config()


def _prune_dedup(now: float, window: float):
    for sig, ts in list(_dedup.items()):
        if now - ts > max(window, 60) * 2:
            _dedup.pop(sig, None)


def submit(event: dict) -> dict:
    """Dépose un événement (best-effort). Renvoie {status, ...}. Ne lève jamais."""
    cfg = config()
    if not cfg.get("enabled"):
        return {"status": "disabled"}
    ev = {
        "type": str(event.get("type") or "event")[:80],
        "source": str(event.get("source") or "?")[:120],
        "severity": (str(event.get("severity") or "info").lower()),
        "message": str(event.get("message") or "")[:2000],
        "data": event.get("data") if isinstance(event.get("data"), (dict, list)) else None,
    }
    if _SEV_ORDER.get(ev["severity"], 0) < _SEV_ORDER.get(cfg.get("min_severity", "warning"), 1):
        return {"status": "filtered", "reason": "severity"}
    sig = hashlib.sha1(f"{ev['type']}|{ev['source']}|{ev['message']}".encode("utf-8", "ignore")).hexdigest()[:12]
    now = time.time()
    win = float(cfg.get("dedup_window", 300) or 0)
    with _lock:
        last = _dedup.get(sig)
        if last and (now - last) < win:
            return {"status": "deduped"}
        _dedup[sig] = now
        _prune_dedup(now, win)
    rec = {"id": uuid.uuid4().hex[:8], "ts": now, "status": "queued", **ev}
    with _lock:
        _recent.appendleft(rec)
    try:
        _q.put_nowait(rec)
    except queue.Full:
        rec["status"] = "overloaded"
        return {"status": "overloaded"}
    return {"status": "queued", "id": rec["id"]}


def recent() -> list:
    with _lock:
        return list(_recent)


def _set_status(rec_id: str, status: str):
    with _lock:
        for r in _recent:
            if r.get("id") == rec_id:
                r["status"] = status
                break


def start_worker(run_cb):
    """Démarre le worker Vigie (idempotent). `run_cb(rec)` exécute l'analyse d'un événement."""
    global _worker_started, _run_cb
    _run_cb = run_cb
    if _worker_started:
        return
    _worker_started = True
    threading.Thread(target=_loop, daemon=True, name="event-vigie").start()
    print("👁️  [Vigie] worker d'événements démarré (en attente, piloté par événement).")


def _loop():
    while True:
        rec = _q.get()                 # BLOQUE : aucun CPU/LLM tant qu'aucun événement
        try:
            _set_status(rec["id"], "processing")
            if _run_cb:
                _run_cb(rec)
            _set_status(rec["id"], "done")
        except Exception as e:
            _set_status(rec["id"], "error")
            print(f"[Vigie] erreur traitement événement : {e}")
        finally:
            _q.task_done()

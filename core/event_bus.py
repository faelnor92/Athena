"""Bus d'événements pub/sub EN-PROCESS — substrat de découplage pour la proactivité.

Permet à des PRODUCTEURS (cycle de vie d'un run, HITL/approbations, Vigie, objectifs…) d'émettre
des événements sans connaître leurs RÉACTEURS (audit, notifications, apprentissage…). Plusieurs
abonnés par sujet ; un sujet `"*"` reçoit TOUT. Erreurs isolées par abonné (un réacteur qui
plante n'empêche pas les autres). Diffusion SYNCHRONE par défaut, ou ASYNCHRONE (worker thread)
pour ne pas bloquer le producteur sur un réacteur lent.

Volontairement minimal et sans dépendance (cf. principe « natif > dépendance »).
"""
import logging
import queue
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_subs: dict = {}          # topic -> {token: handler}
_next_token = 0
_q: "queue.Queue | None" = None
_worker: "threading.Thread | None" = None

ALL = "*"


def subscribe(topic: str, handler) -> int:
    """Abonne `handler(topic, payload)` au sujet `topic` (ou `"*"` pour tout). Renvoie un jeton
    de désabonnement."""
    global _next_token
    with _lock:
        _next_token += 1
        tok = _next_token
        _subs.setdefault(topic, {})[tok] = handler
    return tok


def unsubscribe(token: int) -> bool:
    with _lock:
        for handlers in _subs.values():
            if token in handlers:
                del handlers[token]
                return True
    return False


def _handlers_for(topic: str) -> list:
    with _lock:
        return list(_subs.get(topic, {}).values()) + list(_subs.get(ALL, {}).values())


def _dispatch(topic: str, payload):
    for h in _handlers_for(topic):
        try:
            h(topic, payload)
        except Exception:
            logger.exception("event_bus: un abonné a levé une exception (topic=%s)", topic)


def _ensure_worker():
    global _q, _worker
    with _lock:
        if _worker is None:
            _q = queue.Queue()
            _worker = threading.Thread(target=_run, name="event-bus", daemon=True)
            _worker.start()


def _run():
    while True:
        topic, payload = _q.get()
        _dispatch(topic, payload)


def publish(topic: str, payload=None, async_: bool = False) -> int:
    """Diffuse `payload` à tous les abonnés de `topic` (+ `"*"`). Renvoie le nombre d'abonnés
    visés. `async_=True` → diffusion en arrière-plan (ne bloque pas le producteur)."""
    payload = payload if payload is not None else {}
    n = len(_handlers_for(topic))
    if async_:
        _ensure_worker()
        _q.put((topic, payload))
    else:
        _dispatch(topic, payload)
    return n


def topics() -> list:
    with _lock:
        return [t for t, h in _subs.items() if h]


def subscriber_count(topic: str = None) -> int:
    with _lock:
        if topic is None:
            return sum(len(h) for h in _subs.values())
        return len(_subs.get(topic, {})) + len(_subs.get(ALL, {}))


def reset():
    """Vide tous les abonnements (utile pour les tests)."""
    global _subs
    with _lock:
        _subs = {}

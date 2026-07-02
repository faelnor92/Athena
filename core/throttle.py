"""Throttle générique à fenêtre glissante, partagé entre workers (shared_store SQLite).

Généralise le pattern anti-brute-force du login (routers/auth.py) pour le réutiliser
sur d'autres surfaces : inscription par code d'invitation (brute-force des codes),
endpoints LLM (déni-de-portefeuille sur les clés API si un compte est compromis).

Usage :
    from core import throttle
    if throttle.too_many("register_fail", ip, max_events=8, window=300):
        raise HTTPException(429, ...)
    ...
    throttle.record("register_fail", ip, window=300)   # après un échec
    throttle.clear("register_fail", ip)                # après un succès

Ou en un appel (compte TOUTES les requêtes, pas seulement les échecs) :
    if not throttle.allow("llm", username, max_events=60, window=60):
        raise HTTPException(429, ...)
"""
import time

_NS_PREFIX = "throttle:"


def _events(ns: str, key: str, window: int) -> list:
    from core import shared_store
    now = time.time()
    return [t for t in (shared_store.get(_NS_PREFIX + ns, key) or []) if now - t < window]


def count(ns: str, key: str, window: int) -> int:
    """Nombre d'événements enregistrés pour `key` dans la fenêtre glissante."""
    return len(_events(ns, key, window))


def too_many(ns: str, key: str, max_events: int, window: int) -> bool:
    """Vrai si `key` a déjà atteint `max_events` dans la fenêtre. Ne consomme rien."""
    if max_events <= 0:  # 0 = throttle désactivé
        return False
    return count(ns, key, window) >= max_events


def record(ns: str, key: str, window: int) -> None:
    """Enregistre un événement (atomique inter-process, élague les expirés au passage)."""
    from core import shared_store
    now = time.time()
    shared_store.update(_NS_PREFIX + ns, key,
                        lambda l: [t for t in (l or []) if now - t < window] + [now])


def clear(ns: str, key: str) -> None:
    from core import shared_store
    shared_store.delete(_NS_PREFIX + ns, key)


def allow(ns: str, key: str, max_events: int, window: int) -> bool:
    """Compteur de REQUÊTES (pas d'échecs) : consomme un jeton si sous la limite.
    Renvoie False (sans consommer) si la limite est atteinte. max_events ≤ 0 = illimité."""
    if max_events <= 0:
        return True
    if too_many(ns, key, max_events, window):
        return False
    record(ns, key, window)
    return True

"""Santé des fournisseurs LLM — sélection PROACTIVE avant l'appel, au lieu du seul
failover réactif après l'erreur.

Chaque modèle (principal + FALLBACK_MODELS) a un disjoncteur (pattern du tool_router) :
- erreur de RATE LIMIT (429/quota/surcharge) → cooldown IMMÉDIAT (fenêtre Retry-After si
  le fournisseur la donne, sinon LLM_HEALTH_RL_COOLDOWN, défaut 90 s) ;
- autres erreurs → cooldown après LLM_HEALTH_FAILS échecs consécutifs (défaut 3),
  fenêtre LLM_HEALTH_COOLDOWN (défaut 60 s) ;
- un succès referme le disjoncteur.

order_candidates() trie les candidats : disponibles d'abord (ordre de config conservé),
puis ceux en cooldown (on ne bloque JAMAIS complètement — si tout est ouvert, on tente
quand même dans l'ordre). État en mémoire par processus : les fenêtres sont courtes, la
précision inter-worker n'apporterait rien face au coût d'un aller-retour SQLite par appel.
"""
import os
import re
import threading
import time

_LOCK = threading.Lock()
_STATE = {}  # modèle -> {fails, cooldown_until, rate_limited, last_err}

_RATE_HINTS = ("429", "rate limit", "rate_limit", "ratelimit", "too many requests",
               "quota", "insufficient_quota", "overloaded", "capacity", "exhausted")


def _is_rate_limit(err) -> bool:
    s = f"{type(err).__name__} {err}".lower()
    code = getattr(err, "status_code", None)
    return code == 429 or any(h in s for h in _RATE_HINTS)


def _retry_after_seconds(err):
    """Fenêtre annoncée par le fournisseur (« retry after 17s », « try again in 1m2s »…)."""
    s = str(err)
    m = re.search(r"retry.{0,12}?(\d+(?:\.\d+)?)\s*s", s, re.IGNORECASE)
    if m:
        return float(m.group(1))
    m = re.search(r"in\s+(\d+)m(\d+(?:\.\d+)?)s", s, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    return None


def record_success(model: str):
    with _LOCK:
        _STATE.pop(model, None)


def record_failure(model: str, err):
    now = time.time()
    with _LOCK:
        st = _STATE.setdefault(model, {"fails": 0, "cooldown_until": 0.0,
                                       "rate_limited": False, "last_err": ""})
        st["fails"] += 1
        st["last_err"] = str(err)[:300]
        if _is_rate_limit(err):
            window = _retry_after_seconds(err) or float(
                os.getenv("LLM_HEALTH_RL_COOLDOWN", "90") or 90)
            st["rate_limited"] = True
            st["cooldown_until"] = max(st["cooldown_until"], now + window)
        elif st["fails"] >= int(os.getenv("LLM_HEALTH_FAILS", "3") or 3):
            st["cooldown_until"] = max(
                st["cooldown_until"],
                now + float(os.getenv("LLM_HEALTH_COOLDOWN", "60") or 60))


def available(model: str) -> bool:
    with _LOCK:
        st = _STATE.get(model)
        return not st or st["cooldown_until"] <= time.time()


def order_candidates(models: list) -> list:
    """Disponibles d'abord (ordre de config conservé), en-cooldown ensuite. Jamais vide."""
    seen, uniq = set(), []
    for m in models:
        if m and m not in seen:
            seen.add(m)
            uniq.append(m)
    return [m for m in uniq if available(m)] + [m for m in uniq if not available(m)]


def snapshot() -> dict:
    """État courant (debug / endpoint santé)."""
    now = time.time()
    with _LOCK:
        return {m: {"fails": st["fails"], "rate_limited": st["rate_limited"],
                    "cooldown_remaining_s": max(0, round(st["cooldown_until"] - now, 1)),
                    "last_err": st["last_err"]}
                for m, st in _STATE.items()}


def reset():
    with _LOCK:
        _STATE.clear()

"""Quarantaine (canary) des compétences AUTO-INDUITES — mesurer avant d'adopter.

Une skill induite bancale dégradait silencieusement l'essaim pour toujours (elle
rejoignait skills/ définitivement dès sa création). Désormais :

1. À l'induction, le LLM fournit aussi des CAS DE TEST ; la fonction est exécutée
   dessus immédiatement (self-tests, timeout borné) — échec = refus, rien n'est écrit.
2. Une skill validée va en QUARANTAINE (skills/quarantine/) : elle est exposée aux
   agents comme les autres (canary — usage réel), mais chaque exécution est comptée.
3. Promotion : SKILL_CANARY_PROMOTE succès (défaut 3) sans échec → déplacée dans
   skills/ (adoption définitive). SKILL_CANARY_MAX_FAILS échecs (défaut 3) →
   supprimée (le réparateur _improve_skills a sa chance entre les deux).

Compteurs dans le shared_store (ns « skill_canary ») : survivent aux redémarrages.
"""
import functools
import glob
import importlib.util
import json
import os
import shutil

_NS = "skill_canary"
QUARANTINE_DIR = os.path.join("skills", "quarantine")


def _promote_threshold() -> int:
    return int(os.getenv("SKILL_CANARY_PROMOTE", "3") or 3)


def _max_fails() -> int:
    return int(os.getenv("SKILL_CANARY_MAX_FAILS", "3") or 3)


def _call_with_timeout(func, args, kwargs, timeout_s: float):
    """Exécute func dans un thread DAEMON avec join borné : une boucle infinie générée
    par le LLM ne bloque ni l'induction ni l'arrêt du processus (un ThreadPoolExecutor
    attendrait le thread pour toujours à sa fermeture)."""
    import threading
    out = {}

    def _t():
        try:
            out["res"] = func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — remonté à l'appelant
            out["exc"] = e

    th = threading.Thread(target=_t, daemon=True)
    th.start()
    th.join(timeout_s)
    if th.is_alive():
        raise TimeoutError
    if "exc" in out:
        raise out["exc"]
    return out.get("res")


def run_self_tests(func, tests, timeout_s: float = 5.0):
    """Exécute la fonction sur les cas fournis par l'induction. Chaque cas :
    {"args": [...], "kwargs": {...}, "expected": ...}. Timeout par cas (fonction
    pure mais un LLM peut générer une boucle infinie). Renvoie (ok, raison)."""
    if not tests:
        return False, "aucun cas de test fourni"
    for i, case in enumerate(tests, 1):
        args = case.get("args") or []
        kwargs = case.get("kwargs") or {}
        expected = case.get("expected")
        try:
            got = _call_with_timeout(func, args, kwargs, timeout_s)
        except TimeoutError:
            return False, f"cas {i} : timeout (> {timeout_s}s)"
        except Exception as e:
            return False, f"cas {i} : exception {type(e).__name__}: {e}"
        if isinstance(expected, float) and isinstance(got, (int, float)):
            if abs(got - expected) > 1e-6:
                return False, f"cas {i} : attendu {expected!r}, obtenu {got!r}"
        elif got != expected:
            return False, f"cas {i} : attendu {expected!r}, obtenu {got!r}"
    return True, ""


def save_quarantined(name: str, code: str, description: str, tests: list) -> str:
    """Écrit la skill en quarantaine (code + cas de test pour re-validation)."""
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    with open(os.path.join(QUARANTINE_DIR, f"{name}.py"), "w", encoding="utf-8") as f:
        f.write(code)
    with open(os.path.join(QUARANTINE_DIR, f"{name}.tests.json"), "w", encoding="utf-8") as f:
        json.dump({"description": description, "tests": tests}, f, ensure_ascii=False, indent=1)
    from core import shared_store
    shared_store.set(_NS, name, {"successes": 0, "failures": 0})
    return f"Succès : compétence '{name}' en QUARANTAINE (canary) — promue après {_promote_threshold()} usages réussis."


def record_result(name: str, ok: bool):
    """Compte un usage réel (canary) et applique promotion / éviction aux seuils."""
    from core import shared_store
    st = shared_store.get(_NS, name) or {"successes": 0, "failures": 0}
    st["successes" if ok else "failures"] += 1
    shared_store.set(_NS, name, st)
    if st["failures"] >= _max_fails():
        _evict(name)
        print(f"[\033[93mQUARANTAINE\033[0m] skill '{name}' évincée ({st['failures']} échecs en canary).")
    elif ok and st["failures"] == 0 and st["successes"] >= _promote_threshold():
        _promote(name)
        print(f"[\033[96mQUARANTAINE\033[0m] skill '{name}' PROMUE ({st['successes']} usages réussis).")


def _promote(name: str):
    src = os.path.join(QUARANTINE_DIR, f"{name}.py")
    if os.path.exists(src):
        shutil.move(src, os.path.join("skills", f"{name}.py"))
    _cleanup(name)


def _evict(name: str):
    src = os.path.join(QUARANTINE_DIR, f"{name}.py")
    if os.path.exists(src):
        os.remove(src)
    _cleanup(name)


def _cleanup(name: str):
    tj = os.path.join(QUARANTINE_DIR, f"{name}.tests.json")
    if os.path.exists(tj):
        os.remove(tj)
    from core import shared_store
    shared_store.delete(_NS, name)


def _wrap_canary(name: str, func):
    """Instrumente la skill : chaque exécution réelle alimente les compteurs canary.
    functools.wraps → signature/docstring d'origine conservées (schéma d'outil intact)."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            res = func(*args, **kwargs)
        except Exception:
            record_result(name, ok=False)
            raise
        record_result(name, ok=True)
        return res
    return wrapper


def load_quarantined() -> dict:
    """Charge les skills en quarantaine (exposées aux agents = canary), instrumentées."""
    out = {}
    if not os.path.isdir(QUARANTINE_DIR):
        return out
    for file_path in glob.glob(os.path.join(QUARANTINE_DIR, "*.py")):
        name = os.path.basename(file_path)[:-3]
        try:
            spec = importlib.util.spec_from_file_location(name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            func = getattr(module, name, None)
            if func:
                out[name] = _wrap_canary(name, func)
        except Exception as e:
            print(f"[\033[91mErreur Skill (quarantaine)\033[0m] {name} : {e}")
    return out


def status() -> dict:
    """État des skills en quarantaine (pour l'UI/debug)."""
    from core import shared_store
    names = [os.path.basename(p)[:-3] for p in glob.glob(os.path.join(QUARANTINE_DIR, "*.py"))]
    return {n: (shared_store.get(_NS, n) or {"successes": 0, "failures": 0}) for n in names}

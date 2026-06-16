"""Gestionnaire d'OBJECTIFS persistants (continuité de but, vers Jarvis).

Athena garde une liste d'objectifs à long terme PAR UTILISATEUR : elle ne « perd jamais le
fil ». Un objectif a un statut (actif / en pause / atteint / abandonné), une priorité et des
étapes (sous-objectifs). Les objectifs ACTIFS sont injectés dans la conscience situationnelle
de chaque run, et peuvent être relus périodiquement par une routine.

IMPORTANT — bridage : ce module STOCKE et SUIVT les objectifs. Il n'exécute RIEN tout seul.
Toute action concrète passe par les outils normaux (donc par le HITL pour le sensible). Pas
d'autonomie non bornée.

Persistance : shared_store (ns « goals »), par utilisateur. Multi-worker-safe.
"""
import time
import uuid

from core import shared_store
from core.user_config import current_user_key

_NS = "goals"
_STATUSES = ("active", "paused", "done", "abandoned")
_PRIORITIES = ("high", "normal", "low")


def _key() -> str:
    return current_user_key()


def _all(user: str = None) -> list:
    return list(shared_store.get(_NS, user or _key()) or [])


def _save(goals: list, user: str = None) -> None:
    shared_store.set(_NS, user or _key(), goals)


def _norm_status(s: str) -> str:
    s = (s or "").strip().lower()
    return s if s in _STATUSES else "active"


def _norm_priority(p: str) -> str:
    p = (p or "").strip().lower()
    return p if p in _PRIORITIES else "normal"


def create(title: str, detail: str = "", priority: str = "normal", steps=None) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("titre d'objectif requis")
    goal = {
        "id": uuid.uuid4().hex[:8],
        "title": title[:200],
        "detail": (detail or "").strip(),
        "status": "active",
        "priority": _norm_priority(priority),
        "steps": [{"id": uuid.uuid4().hex[:6], "text": str(s).strip(), "done": False}
                  for s in (steps or []) if str(s).strip()],
        "created_at": time.time(),
        "updated_at": time.time(),
    }

    def _f(cur):
        cur = list(cur or [])
        cur.append(goal)
        return cur
    shared_store.update(_NS, _key(), _f)
    return goal


def list_goals(status: str = None, user: str = None) -> list:
    goals = _all(user)
    if status:
        st = status.strip().lower()
        if st != "all":
            goals = [g for g in goals if g.get("status") == st]
    # tri : actifs d'abord, puis par priorité (high<normal<low), puis récents.
    order_status = {"active": 0, "paused": 1, "done": 2, "abandoned": 3}
    order_prio = {"high": 0, "normal": 1, "low": 2}
    goals.sort(key=lambda g: (order_status.get(g.get("status"), 9),
                              order_prio.get(g.get("priority"), 1),
                              -g.get("created_at", 0)))
    return goals


def get(goal_id: str, user: str = None):
    return next((g for g in _all(user) if g.get("id") == goal_id), None)


def _mutate(goal_id: str, change) -> bool:
    out = {"ok": False}

    def _f(cur):
        cur = list(cur or [])
        for g in cur:
            if g.get("id") == goal_id:
                change(g)
                g["updated_at"] = time.time()
                out["ok"] = True
                break
        return cur
    shared_store.update(_NS, _key(), _f)
    return out["ok"]


def set_status(goal_id: str, status: str) -> bool:
    return _mutate(goal_id, lambda g: g.__setitem__("status", _norm_status(status)))


def set_priority(goal_id: str, priority: str) -> bool:
    return _mutate(goal_id, lambda g: g.__setitem__("priority", _norm_priority(priority)))


def update_detail(goal_id: str, detail: str) -> bool:
    return _mutate(goal_id, lambda g: g.__setitem__("detail", (detail or "").strip()))


def add_step(goal_id: str, text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    return _mutate(goal_id, lambda g: g["steps"].append(
        {"id": uuid.uuid4().hex[:6], "text": text, "done": False}))


def complete_step(goal_id: str, step_ref: str) -> bool:
    """Coche une étape par son id ou par son texte (correspondance insensible à la casse)."""
    ref = (step_ref or "").strip().lower()

    def _f(g):
        for s in g.get("steps", []):
            if s["id"].lower() == ref or s["text"].strip().lower() == ref:
                s["done"] = True
                break
    return _mutate(goal_id, _f)


def remove(goal_id: str) -> bool:
    out = {"ok": False}

    def _f(cur):
        cur = list(cur or [])
        new = [g for g in cur if g.get("id") != goal_id]
        out["ok"] = len(new) < len(cur)
        return new
    shared_store.update(_NS, _key(), _f)
    return out["ok"]


def _fmt(g: dict) -> str:
    done = sum(1 for s in g.get("steps", []) if s.get("done"))
    total = len(g.get("steps", []))
    prog = f" [{done}/{total}]" if total else ""
    pr = {"high": "🔴", "normal": "🟡", "low": "⚪"}.get(g.get("priority"), "🟡")
    return f"{pr} ({g['id']}) {g['title']}{prog} — {g['status']}"


def summary(max_items: int = 5, user: str = None) -> str:
    """Résumé COURT des objectifs ACTIFS — pour la conscience situationnelle d'un run."""
    actifs = [g for g in list_goals("active", user)]
    if not actifs:
        return ""
    lignes = []
    for g in actifs[:max_items]:
        steps = g.get("steps", [])
        nxt = next((s["text"] for s in steps if not s.get("done")), None)
        item = _fmt(g)
        if nxt:
            item += f" · prochaine étape : {nxt}"
        lignes.append(item)
    return "\n".join(lignes)

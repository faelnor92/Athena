"""Liste de tâches de SESSION (planification multi-étapes), façon `todowrite` d'opencode /
Claude Code. L'agent structure un travail complexe en étapes suivies, VISIBLES par
l'utilisateur (athena_cli + onglet Code de l'UI), et met à jour leur statut en temps réel.

Portée : par UTILISATEUR (une liste active à la fois, comme Claude Code). Persistée dans le
store partagé (cohérent multi-worker, survit aux tours). L'appel REMPLACE toute la liste.
"""
from core import shared_store

_NS = "todos"
_STATUSES = ("pending", "in_progress", "completed", "cancelled")
_ICON = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "cancelled": "[-]"}


def _scope() -> str:
    try:
        from core.user_config import current_user_key
        return current_user_key() or "local"
    except Exception:
        return "local"


def get_todos(scope: str = None) -> list:
    """Liste de tâches courante (liste d'objets {content, status})."""
    return list(shared_store.get(_NS, scope or _scope()) or [])


_MAX_ITEMS = 100          # garde-fou : une todo-list de session reste raisonnable
_MAX_CONTENT = 500        # longueur max d'une tâche (anti-explosion de contexte/stockage)


def _normalize(items) -> list:
    out = []
    for it in (items or [])[:_MAX_ITEMS]:
        if isinstance(it, str):
            it = {"content": it}
        if not isinstance(it, dict):
            continue
        content = str(it.get("content") or it.get("task") or it.get("title") or "").strip()[:_MAX_CONTENT]
        if not content:
            continue
        status = str(it.get("status") or "pending").strip().lower()
        if status not in _STATUSES:
            status = "pending"
        out.append({"content": content, "status": status})
    return out


def render(items: list) -> str:
    """Rendu texte (checklist) — réutilisé par la sortie d'outil et les CLI."""
    if not items:
        return "(liste de tâches vide)"
    done = sum(1 for i in items if i["status"] == "completed")
    lines = [f"📋 Tâches ({done}/{len(items)}) :"]
    for i in items:
        lines.append(f"  {_ICON.get(i['status'], '[ ]')} {i['content']}")
    return "\n".join(lines)


def set_todos(items: list, scope: str = None) -> list:
    """Remplace la liste de tâches et la persiste. Renvoie la liste normalisée."""
    items = _normalize(items)
    shared_store.set(_NS, scope or _scope(), items)
    return items


def todo_write(items: list) -> str:
    """Crée ou met à jour la LISTE DE TÂCHES de la session (planification visible par l'utilisateur).
    REMPLACE entièrement la liste à chaque appel — renvoie toujours la liste complète à jour.

    Quand l'utiliser : dès qu'un travail demande 3+ étapes distinctes, ou que l'utilisateur
    donne plusieurs tâches. Inutile pour une action triviale ou une simple question.
    Règles : garde EXACTEMENT UNE tâche 'in_progress' à la fois ; passe-la 'completed' seulement
    une fois RÉELLEMENT faite (et vérifiée) ; mets à jour au fil de l'eau ; ajoute les tâches
    de suivi découvertes en cours de route.

    items: liste d'objets {"content": "description de la tâche", "status": "pending|in_progress|completed|cancelled"}.
    """
    items = set_todos(items)
    # Un seul in_progress attendu : on le signale sans bloquer (l'agent se corrige).
    n_active = sum(1 for i in items if i["status"] == "in_progress")
    try:
        from core.run_context import publish_step
        publish_step({"type": "todo", "items": items})
    except Exception:
        pass
    out = render(items)
    if n_active > 1:
        out += f"\n⚠️ {n_active} tâches 'in_progress' — n'en garde qu'une seule active."
    return out

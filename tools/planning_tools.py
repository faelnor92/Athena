"""Planification explicite : l'agent externalise un plan d'action visible dans
l'UI, puis met à jour le statut de chaque étape au fil de l'exécution.

Les étapes sont publiées en temps réel via run_context (events 'plan' /
'plan_update'), rendues sous forme de checklist dans le chat.
"""
import re

from core import run_context
from core import plan_store
from core import channels


def _cid():
    """Canal/session courant (pour scoper le plan persistant)."""
    try:
        return channels.current_channel.get() or "web"
    except Exception:
        return "web"


def make_plan(steps: str) -> str:
    """
    Affiche un PLAN D'ACTION structuré et visible à l'utilisateur, à utiliser pour
    une demande complexe en plusieurs étapes AVANT de l'exécuter. Mets ensuite à
    jour l'avancement avec update_plan_step.

    Args:
        steps (str): Les étapes, une par ligne (ou séparées par ' | ').

    Returns:
        str: Confirmation.
    """
    items = []
    for s in re.split(r"\n|\s\|\s", steps or ""):
        s = s.strip()
        # Retire une éventuelle puce/numérotation EN TÊTE (1. , 1) , - , • , *).
        s = re.sub(r"^\s*(?:\d+[.)]|[-•*])\s*", "", s).strip()
        if s:
            items.append({"text": s, "status": "pending"})
    if not items:
        return "Plan vide : fournis au moins une étape."
    run_context.publish_step({"type": "plan", "items": items})
    plan_store.set_plan(_cid(), items)  # persiste (éditable par l'humain)
    return (f"Plan de {len(items)} étape(s) affiché. Exécute-les et appelle "
            "update_plan_step(step=N, status='done') au fur et à mesure. "
            "L'utilisateur peut modifier ce plan ; relis-le au besoin avec get_plan().")


def update_plan_step(step: int, status: str = "done") -> str:
    """
    Met à jour le statut d'une étape du plan affiché (numérotation à partir de 1).

    Args:
        step (int): Numéro de l'étape (1 = première).
        status (str): 'in_progress', 'done' ou 'failed'.

    Returns:
        str: Confirmation.
    """
    try:
        idx = int(step) - 1
    except (TypeError, ValueError):
        return "Numéro d'étape invalide."
    status = (status or "done").strip().lower()
    if status not in ("pending", "in_progress", "done", "failed"):
        status = "done"
    run_context.publish_step({"type": "plan_update", "index": idx, "status": status})
    plan_store.update_step(_cid(), idx, status)
    return f"Étape {step} → {status}."


def get_plan() -> str:
    """
    Relit le PLAN D'ACTION courant (avec les éventuelles MODIFICATIONS de l'utilisateur :
    étapes cochées, ajoutées, éditées ou supprimées à la main). À utiliser pour te
    resynchroniser sur ce que l'humain attend réellement avant de continuer.
    """
    items = plan_store.get_plan(_cid())
    if not items:
        return "Aucun plan en cours."
    icons = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "failed": "❌"}
    lines = [f"{i+1}. {icons.get(it.get('status'), '⬜')} {it.get('text','')}"
             for i, it in enumerate(items)]
    return "Plan courant :\n" + "\n".join(lines)

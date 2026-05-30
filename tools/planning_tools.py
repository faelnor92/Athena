"""Planification explicite : l'agent externalise un plan d'action visible dans
l'UI, puis met à jour le statut de chaque étape au fil de l'exécution.

Les étapes sont publiées en temps réel via run_context (events 'plan' /
'plan_update'), rendues sous forme de checklist dans le chat.
"""
import re

from core import run_context


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
    return (f"Plan de {len(items)} étape(s) affiché. Exécute-les et appelle "
            "update_plan_step(step=N, status='done') au fur et à mesure.")


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
    return f"Étape {step} → {status}."

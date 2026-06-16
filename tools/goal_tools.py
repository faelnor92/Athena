"""Outils de gestion d'OBJECTIFS persistants (continuité de but).

Athena suit des objectifs à long terme et ne perd pas le fil. Ces outils gèrent le SUIVI ;
ils n'exécutent aucune action concrète (qui passe, elle, par les outils normaux + le HITL).
"""
from typing import List, Optional

import core.goals as goals


def create_goal(title: str, detail: str = "", priority: str = "normal",
                steps: Optional[List[str]] = None) -> str:
    """
    Crée un OBJECTIF persistant que tu suivras dans le temps (ex. « migrer le serveur mail »,
    « finir le chapitre 7 »). Utilise-le quand l'utilisateur exprime un but durable, pas une
    tâche immédiate. Tu peux le décomposer en étapes.

    Args:
        title (str): intitulé court de l'objectif.
        detail (str): précisions / critère de réussite (optionnel).
        priority (str): "high", "normal" ou "low".
        steps (list[str]): sous-étapes initiales (optionnel).
    Returns:
        str: confirmation avec l'identifiant de l'objectif.
    """
    try:
        g = goals.create(title, detail, priority, steps)
    except ValueError as e:
        return f"Erreur : {e}"
    return f"🎯 Objectif créé ({g['id']}) : « {g['title']} » [{g['priority']}]. Suis-le avec list_goals()."


def list_goals(status: str = "active") -> str:
    """
    Liste les objectifs suivis. status : "active" (défaut), "paused", "done", "abandoned" ou "all".
    """
    gs = goals.list_goals(status)
    if not gs:
        return f"Aucun objectif ({status})."
    lines = []
    for g in gs:
        lines.append(goals._fmt(g))
        for s in g.get("steps", []):
            lines.append(f"      {'✅' if s.get('done') else '▫️'} {s['text']}")
        if g.get("detail"):
            lines.append(f"      ↳ {g['detail']}")
    return "Objectifs :\n" + "\n".join(lines)


def update_goal_status(goal_id: str, status: str) -> str:
    """
    Change le statut d'un objectif. status : "active", "paused", "done" (atteint) ou
    "abandoned" (abandonné, devenu obsolète).
    """
    if not goals.set_status(goal_id, status):
        return f"Objectif {goal_id} introuvable."
    libelle = {"active": "réactivé", "paused": "mis en pause", "done": "marqué ATTEINT ✅",
               "abandoned": "abandonné"}.get(status.strip().lower(), "mis à jour")
    return f"Objectif {goal_id} {libelle}."


def add_goal_step(goal_id: str, step: str) -> str:
    """Ajoute une étape (sous-objectif) à un objectif existant."""
    if not goals.add_step(goal_id, step):
        return f"Impossible d'ajouter l'étape (objectif {goal_id} introuvable ou étape vide)."
    return f"Étape ajoutée à l'objectif {goal_id}."


def complete_goal_step(goal_id: str, step: str) -> str:
    """Marque une étape comme faite (par son texte ou son id)."""
    if not goals.complete_step(goal_id, step):
        return f"Étape introuvable dans l'objectif {goal_id}."
    return f"Étape « {step} » cochée dans l'objectif {goal_id}."


def set_goal_priority(goal_id: str, priority: str) -> str:
    """Change la priorité d'un objectif : "high", "normal" ou "low"."""
    if not goals.set_priority(goal_id, priority):
        return f"Objectif {goal_id} introuvable."
    return f"Priorité de l'objectif {goal_id} → {priority}."

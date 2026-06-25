"""Assembleur de CONSCIENCE SITUATIONNELLE (« World Model » — couche LECTURE).

Le prompt d'un run injecte déjà, séparément : le profil utilisateur (`user_profile`),
les faits-graphe pertinents (Chronos), le RAG vectoriel et la Core Memory. Ce module
N'EN DUPLIQUE AUCUN : il ajoute la part qui manquait — l'état « ici et maintenant » que
le LLM ne peut pas deviner :

- les **parenthèses ouvertes** (tâches mises de côté via la pile de contextes) → Athena
  n'oublie jamais qu'elle a du travail parqué ;
- la **pièce courante** (présence Home Assistant) → pour agir au bon endroit.

Volontairement court et tolérant aux pannes : renvoie "" si rien de pertinent.
"""


def situational_block(session_key: str) -> str:
    """Bloc compact « état actuel » à injecter dans le contexte volatile d'un run.
    Renvoie "" s'il n'y a rien d'utile à signaler."""
    parts = []

    # Objectifs ACTIFS (continuité de but : Athena ne perd pas le fil).
    try:
        import core.goals as goals
        gsum = goals.summary(max_items=5)
        if gsum:
            parts.append("Objectifs en cours :\n" + gsum)
    except Exception:
        pass

    # Parenthèses ouvertes (pile de contextes).
    try:
        import core.context_stack as cs
        topics = cs.topics(session_key)
        if topics:
            liste = " ; ".join(topics)
            parts.append(
                f"Tâches MISES DE CÔTÉ (parenthèses ouvertes, de la plus ancienne à la plus "
                f"récente) : {liste}. L'utilisateur peut demander d'y revenir (« on reprend ») "
                f"→ close_context()."
            )
    except Exception:
        pass

    # Pièce courante (présence Home Assistant), si configurée.
    try:
        from tools import presence
        room = presence.current_room_value()
        if room:
            parts.append(f"Pièce actuelle de l'utilisateur : {room}.")
    except Exception:
        pass

    # Domicile (HOME_ADDRESS) : pour ne PAS inventer un lieu de départ et savoir le citer si on le
    # demande. Le calcul d'heure de départ reste fait par l'outil get_departure_alerts.
    try:
        import os
        home = ""
        try:
            from core import user_config
            cfg = user_config.get_all() or {}
            home = (cfg.get("HOME_ADDRESS") or cfg.get("WEATHER_CITY") or "").strip()
        except Exception:
            home = ""
        home = home or os.getenv("HOME_ADDRESS", "").strip() or os.getenv("WEATHER_CITY", "").strip()
        if home:
            parts.append(f"Domicile de l'utilisateur (lieu de départ) : {home}.")
    except Exception:
        pass

    if not parts:
        return ""
    body = "\n".join(f"- {p}" for p in parts)
    return ("\n=== ÉTAT ACTUEL (conscience situationnelle) ===\n"
            f"{body}\n"
            "====================================================\n")

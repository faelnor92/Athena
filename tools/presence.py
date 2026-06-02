"""Conscience spatiale (follow-me) — OPTIONNELLE.

Athena ne calcule PAS la présence elle-même (le BLE brut est bruité) : c'est Home
Assistant qui en est la source de vérité (capteur mmWave par pièce, ESPresense/Bermuda
en BLE…). Athena se contente de LIRE l'entité HA qui indique la pièce courante.

Activation : définir PRESENCE_ENTITY vers une entité HA dont l'état est le nom de la
pièce (ex. sensor.piece_actuelle = "salon"). Si non défini, la fonctionnalité est
simplement inactive — aucune dépendance imposée à qui clone le dépôt. Voir docs/follow-me.md.
"""
import os
import json


def current_room_value():
    """Renvoie le nom de la pièce courante (str) ou None si non configuré/indisponible.
    Usage interne (routage voix), sans message destiné au LLM."""
    entity = os.getenv("PRESENCE_ENTITY", "").strip()
    if not entity:
        return None
    try:
        from tools.home_assistant import get_ha_state
        raw = get_ha_state(entity)
        data = json.loads(raw)
        if isinstance(data, dict) and "error" not in data:
            state = (data.get("state") or "").strip()
            if state and state.lower() not in ("unknown", "unavailable", "none", ""):
                return state
    except Exception:
        pass
    return None


def get_current_room() -> str:
    """
    Indique dans quelle PIÈCE se trouve actuellement l'utilisateur, en lisant l'entité
    de présence Home Assistant configurée (PRESENCE_ENTITY). À utiliser pour agir sur la
    bonne pièce (ex. régler le chauffage de la pièce où il est, suivre la voix/musique).
    """
    entity = os.getenv("PRESENCE_ENTITY", "").strip()
    if not entity:
        return ("Suivi de présence non configuré. Pour l'activer, définis PRESENCE_ENTITY "
                "vers une entité HA de pièce (voir docs/follow-me.md).")
    room = current_room_value()
    if not room:
        return (f"Impossible de déterminer la pièce (entité « {entity} » indisponible ou "
                "sans valeur). Vérifie la détection de présence côté Home Assistant.")
    return f"Pièce actuelle : {room}"

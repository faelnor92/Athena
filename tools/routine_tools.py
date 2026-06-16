"""Outils ROUTINES : permettent à Athena de CRÉER/LISTER ses propres routines planifiées
(briefing matinal, rappels récurrents…) sans passer par l'UI.

Bridé : create_routine est marqué « sensible » (_requires_approval) → l'utilisateur CONFIRME
avant création. La routine s'exécute ensuite dans le contexte de son propriétaire.
"""
from core.routines import routine_store


_FREqs = ("daily", "weekly", "interval")


def create_routine(name: str, prompt: str, frequency: str = "daily", time: str = "08:00",
                   weekday: int = 0, minutes: int = 60, telegram_chat_id: str = "") -> str:
    """
    Crée une ROUTINE planifiée (tâche récurrente exécutée automatiquement). Nécessite la
    CONFIRMATION de l'utilisateur (action sensible).

    Args:
        name (str): Nom de la routine (ex: "Briefing du matin").
        prompt (str): La tâche à exécuter (ex: "Fais-moi le briefing du jour : agenda + météo").
        frequency (str): "daily" (chaque jour), "weekly" (chaque semaine) ou "interval" (toutes N min).
        time (str): Heure "HH:MM" (pour daily/weekly).
        weekday (int): Jour 0=lundi..6=dimanche (pour weekly).
        minutes (int): Intervalle en minutes (pour interval).
        telegram_chat_id (str): Si fourni, le résultat est aussi envoyé sur ce chat Telegram.
    Returns:
        str: Confirmation (ou erreur).
    """
    name = (name or "").strip()
    prompt = (prompt or "").strip()
    if not name or not prompt:
        return "Erreur : 'name' et 'prompt' sont requis."
    freq = (frequency or "daily").strip().lower()
    if freq not in _FREqs:
        return f"Erreur : frequency invalide ({freq}). Attendu : daily, weekly ou interval."
    if freq == "daily":
        schedule = {"type": "daily", "time": (time or "08:00").strip()}
    elif freq == "weekly":
        schedule = {"type": "weekly", "weekday": int(weekday or 0), "time": (time or "08:00").strip()}
    else:
        schedule = {"type": "interval", "minutes": max(1, int(minutes or 60))}
    routine = {
        "name": name, "prompt": prompt, "agent": "Athena", "schedule": schedule,
        "enabled": True, "notify": True, "approved": True,  # validée via la confirmation de l'outil
    }
    if (telegram_chat_id or "").strip():
        routine["telegram_chat_id"] = telegram_chat_id.strip()
    try:
        r = routine_store.upsert(routine)
    except Exception as e:
        return f"Erreur lors de la création de la routine : {e}"
    when = {"daily": f"chaque jour à {schedule.get('time')}",
            "weekly": f"chaque semaine (jour {schedule.get('weekday')}) à {schedule.get('time')}",
            "interval": f"toutes les {schedule.get('minutes')} min"}.get(freq, freq)
    tg = " + envoi Telegram" if routine.get("telegram_chat_id") else ""
    return f"✅ Routine « {name} » créée ({when}){tg}. Tu peux la gérer dans Réglages → Routines."


create_routine._requires_approval = True  # action sensible → confirmation utilisateur


def list_routines() -> str:
    """Liste les routines planifiées de l'utilisateur courant (nom, fréquence, état). LECTURE SEULE."""
    try:
        from core.user_config import current_user_key
        me = current_user_key()
    except Exception:
        me = "local"
    rs = [r for r in routine_store.list() if (r.get("owner") or "local") == me]
    if not rs:
        return "Aucune routine planifiée."
    out = ["Routines planifiées :"]
    for r in rs:
        sc = r.get("schedule") or {}
        t = sc.get("type")
        when = (f"chaque jour à {sc.get('time')}" if t == "daily"
                else f"chaque semaine (jour {sc.get('weekday')}) à {sc.get('time')}" if t == "weekly"
                else f"toutes les {sc.get('minutes')} min" if t == "interval"
                else t or "?")
        state = "activée" if r.get("enabled", True) else "désactivée"
        out.append(f"  • {r.get('name', '(sans nom)')} — {when} [{state}]")
    return "\n".join(out)

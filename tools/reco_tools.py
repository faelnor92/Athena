"""Recommandations CONTEXTUELLES : l'assistant anticipe à partir du contexte réel de l'utilisateur.

Cet outil n'invente rien : il ASSEMBLE des signaux réels (heure, météo hyperlocale, agenda du
jour, tâches/courses, perturbations transport, profil & préférences mémorisés) et demande à
l'agent d'en déduire 2 à 4 suggestions concrètes et personnalisées. La réflexion reste au LLM ;
le tool fournit la matière vérifiée (pas de fait fabriqué).
"""
from datetime import datetime


def _period(h: int) -> str:
    if h < 6:
        return "nuit"
    if h < 12:
        return "matinée"
    if h < 14:
        return "midi"
    if h < 18:
        return "après-midi"
    return "soirée"


def get_recommendations(focus: str = "") -> str:
    """Propose des recommandations CONTEXTUELLES personnalisées (anticipation).

    Rassemble le contexte réel du moment (heure, météo, agenda du jour, tâches/courses,
    perturbations transport, préférences connues) ; l'agent en tire ensuite 2-4 suggestions
    concrètes. À utiliser quand l'utilisateur demande « qu'est-ce que tu me conseilles ? »,
    « quoi de prévu / à anticiper ? », ou pour une suggestion proactive.

    focus : cadrage optionnel (ex. « ma journée », « ma soirée », « mon trajet », « le week-end »).
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    parts = ["=== CONTEXTE (données réelles vérifiées) ==="]
    parts.append(f"- Moment : {now.strftime('%A %d %B %Y, %H:%M')} ({_period(now.hour)}).")

    # Météo hyperlocale.
    try:
        from tools.basic_tools import get_weather
        w = (get_weather("") or "").strip()
        if w and not w.lower().startswith("erreur"):
            parts.append("- Météo :\n  " + "\n  ".join(w.splitlines()[:5]))
    except Exception:
        pass

    # Agenda du jour.
    try:
        from tools.agenda_tools import load_agenda
        evts = [e for e in (load_agenda() or []) if (e.get("datetime", "") or "").startswith(today)]
        if evts:
            ev = "; ".join(f"{e['datetime'].split(' ')[1]} {e.get('title','')}"
                           for e in sorted(evts, key=lambda x: x["datetime"]))
            parts.append(f"- Rendez-vous aujourd'hui : {ev}")
        else:
            parts.append("- Rendez-vous aujourd'hui : aucun.")
    except Exception:
        pass

    # Tâches & courses en attente.
    try:
        from tools.list_tools import get_list_items
        todos = [t["text"] for t in get_list_items("taches") if not t.get("completed")]
        courses = [s["text"] for s in get_list_items("courses") if not s.get("completed")]
        if todos:
            parts.append("- Tâches en attente : " + ", ".join(todos[:6]))
        if courses:
            parts.append("- Courses à acheter : " + ", ".join(courses[:8]))
    except Exception:
        pass


    # Profil & préférences durables (personnalisation).
    try:
        from core.user_profile import user_profile
        prof = (user_profile.as_prompt() or "").strip()
        if prof:
            parts.append("- Profil/préférences :\n  " + "\n  ".join(prof.splitlines()[:8]))
    except Exception:
        pass
    try:
        import tools.memory_tools as _mt
        mem = (_mt.core_mem.get_as_prompt() or "").strip()
        if mem:
            parts.append("- Mémoire (faits durables) :\n  " + "\n  ".join(mem.splitlines()[:8]))
    except Exception:
        pass

    cible = (focus or "").strip() or "maintenant"
    parts.append(
        "\n=== CONSIGNE ===\n"
        f"À partir UNIQUEMENT du contexte ci-dessus, propose à l'utilisateur 2 à 4 recommandations "
        f"CONCRÈTES, personnalisées et actionnables pour « {cible} ». Anticipe : météo → "
        "habillement/parapluie/volets ; agenda → quand partir, trajet, alternative en cas de "
        "perturbation ; tâches/courses → rappel opportun ; préférences connues → suggestion adaptée. "
        "Sois bref (puces), n'invente AUCUNE donnée absente du contexte, et ne propose rien d'inutile."
    )
    return "\n".join(parts)

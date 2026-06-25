"""Outil de proactivité émergente : propose des routines d'après les habitudes de l'utilisateur."""


def suggest_routines() -> str:
    """Analyse les HABITUDES de l'utilisateur (requêtes récurrentes à heure régulière, sur plusieurs
    jours) et PROPOSE de créer des routines proactives — ex. « tu demandes la météo ~8h chaque matin
    → créer une routine météo quotidienne à 8h ? ».

    Renvoie la liste des habitudes détectées avec, pour chacune, une routine suggérée. Pour ACCEPTER
    une suggestion, crée la routine avec create_routine (qui te demandera validation). Idéal en
    routine hebdomadaire (« propose-moi des routines d'après mes habitudes »).
    """
    from core import habits
    if not habits.enabled():
        return "Le minage d'habitudes est désactivé (variable HABIT_MINING)."
    try:
        from core.user_config import current_user_key
        user = current_user_key()
    except Exception:
        user = None
    found = habits.mine_habits(user=user)
    if not found:
        return ("Aucune habitude récurrente nette pour l'instant. Il faut plusieurs jours de "
                "requêtes similaires à heure régulière pour qu'un motif ressorte.")
    lines = ["🔁 **Habitudes détectées — routines suggérées** :"]
    for h in found:
        kw = ", ".join(h.get("signature") or []) or "?"
        lines.append(
            f"- vers **{h['hour']:02d}h** (~{h['days']} jours, {h['count']}×) : "
            f"« {h['example']} » → routine quotidienne {h['hour']:02d}:00 sur ce sujet ({kw}) ?")
    lines.append("\nDis-moi laquelle créer — je la planifierai après ta validation.")
    return "\n".join(lines)

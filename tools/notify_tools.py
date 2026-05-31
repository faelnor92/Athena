from core.notifications import notify


def send_notification(message: str, title: str = "Jarvis", channel: str = "") -> str:
    """
    Envoie un message/résultat à l'utilisateur sur ses messageries configurées.
    Idéal quand l'utilisateur demande de RECEVOIR une réponse (ex: « envoie-moi ça par
    mail », « préviens-moi sur Discord ») : mets le contenu voulu dans `message`.

    Args:
        message (str): Le texte à envoyer (peut être la réponse complète demandée).
        title (str): Titre/objet court (sert d'objet d'email).
        channel (str): Canal CIBLE optionnel parmi 'email', 'discord', 'slack',
            'telegram', 'webhook'. Vide = envoie sur TOUS les canaux configurés.

    Returns:
        str: Confirmation avec la liste des canaux atteints, ou avertissement.
    """
    ch = (channel or "").strip().lower() or None
    valid = {"email", "discord", "slack", "telegram", "webhook"}
    if ch and ch not in valid:
        return f"Canal '{channel}' inconnu. Choisis parmi : {', '.join(sorted(valid))}, ou laisse vide pour tous."
    channels = notify(message, title=title, channel=ch)
    if not channels:
        if ch:
            return (f"Le canal '{ch}' n'est pas configuré (Réglages → Messageries). Message non envoyé.")
        return ("Aucun canal de messagerie configuré "
                "(Discord/Slack/Telegram/email/webhook). Notification non envoyée.")
    return f"Message envoyé sur : {', '.join(channels)}."

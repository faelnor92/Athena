from core.notifications import notify


def send_notification(message: str, title: str = "Jarvis") -> str:
    """
    Envoie une notification à l'utilisateur sur toutes ses messageries configurées
    (Discord, Slack, Telegram, email, webhook générique). Utile pour le prévenir
    d'un résultat, d'une alerte, ou de la fin d'une tâche en arrière-plan.

    Args:
        message (str): Le texte de la notification.
        title (str): Titre court optionnel.

    Returns:
        str: Confirmation avec la liste des canaux atteints, ou avertissement si aucun.
    """
    channels = notify(message, title=title)
    if not channels:
        return ("Aucun canal de messagerie configuré "
                "(Discord/Slack/Telegram/email/webhook). Notification non envoyée.")
    return f"Notification envoyée sur : {', '.join(channels)}."

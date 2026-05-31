"""Couche de notifications multi-canaux.

Envoie un message sur tous les canaux configurés (via variables d'environnement) :
Discord (webhook), Slack (webhook), webhook générique, Telegram (chat_id explicite),
et email (SMTP). Utilisée par les routines, l'agenda, et l'outil agent
`send_notification`.

Aucun canal configuré => no-op silencieux.
"""
import os
import smtplib
from email.mime.text import MIMEText

import requests


def _csv(env_name: str):
    return [x.strip() for x in os.getenv(env_name, "").split(",") if x.strip()]


def configured_channels() -> list:
    """Liste des canaux actuellement configurés (pour l'UI/diagnostic)."""
    chans = []
    if os.getenv("DISCORD_WEBHOOK_URL", "").strip():
        chans.append("discord")
    if os.getenv("SLACK_WEBHOOK_URL", "").strip():
        chans.append("slack")
    if os.getenv("NOTIFY_WEBHOOK_URL", "").strip():
        chans.append("webhook")
    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and _csv("TELEGRAM_CHAT_ID"):
        chans.append("telegram")
    if os.getenv("SMTP_HOST", "").strip() and _csv("NOTIFY_EMAIL_TO"):
        chans.append("email")
    return chans


def _send_email(host, to_list, subject, body):
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    pwd = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or user or "jarvis@localhost"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    if os.getenv("SMTP_SSL", "false").lower() in ("true", "1", "yes"):
        server = smtplib.SMTP_SSL(host, port, timeout=10)
    else:
        server = smtplib.SMTP(host, port, timeout=10)
        try:
            server.starttls()
        except Exception:
            pass
    try:
        if user:
            server.login(user, pwd)
        server.sendmail(sender, to_list, msg.as_string())
    finally:
        server.quit()


def notify(message: str, title: str = None, channel: str = None) -> list:
    """Diffuse `message` sur les canaux configurés. Si `channel` est précisé
    (discord|slack|webhook|telegram|email), n'envoie QUE sur celui-ci.
    Renvoie la liste des canaux ayant réussi."""
    sent = []
    plain = f"{title}\n{message}" if title else message
    want = (channel or "").strip().lower() or None

    def _wanted(c):
        return want is None or want == c

    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if url and _wanted("discord"):
        try:
            content = (f"**{title}**\n{message}" if title else message)[:1900]
            requests.post(url, json={"content": content}, timeout=8)
            sent.append("discord")
        except Exception as e:
            print(f"[notif discord] {e}")

    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if url and _wanted("slack"):
        try:
            requests.post(url, json={"text": plain}, timeout=8)
            sent.append("slack")
        except Exception as e:
            print(f"[notif slack] {e}")

    url = os.getenv("NOTIFY_WEBHOOK_URL", "").strip()
    if url and _wanted("webhook"):
        try:
            requests.post(url, json={"title": title or "Jarvis", "message": message}, timeout=8)
            sent.append("webhook")
        except Exception as e:
            print(f"[notif webhook] {e}")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = _csv("TELEGRAM_CHAT_ID")
    if token and chat_ids and _wanted("telegram"):
        ok = False
        for cid in chat_ids:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": cid, "text": plain}, timeout=8)
                ok = True
            except Exception as e:
                print(f"[notif telegram] {e}")
        if ok:
            sent.append("telegram")

    host = os.getenv("SMTP_HOST", "").strip()
    to_list = _csv("NOTIFY_EMAIL_TO")
    if host and to_list and _wanted("email"):
        try:
            _send_email(host, to_list, title or "Notification Jarvis", message)
            sent.append("email")
        except Exception as e:
            print(f"[notif email] {e}")

    return sent

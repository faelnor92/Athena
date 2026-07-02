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


def _csv_user(env_name: str):
    """Cible PERSONNELLE (Telegram chat / email) de l'utilisateur courant si définie
    dans user_config, sinon repli sur le global .env. L'infra (token/SMTP) reste globale."""
    try:
        from core import user_config
        v = user_config.get(env_name)
        if v:
            return [x.strip() for x in str(v).split(",") if x.strip()]
    except Exception:
        pass
    return _csv(env_name)


def configured_channels() -> list:
    """Liste des canaux actuellement configurés (pour l'UI/diagnostic)."""
    chans = []
    if os.getenv("DISCORD_WEBHOOK_URL", "").strip():
        chans.append("discord")
    if os.getenv("SLACK_WEBHOOK_URL", "").strip():
        chans.append("slack")
    if os.getenv("NOTIFY_WEBHOOK_URL", "").strip():
        chans.append("webhook")
    if os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and _csv_user("TELEGRAM_CHAT_ID"):
        chans.append("telegram")
    if os.getenv("SMTP_HOST", "").strip() and _csv_user("NOTIFY_EMAIL_TO"):
        chans.append("email")
    return chans


def _send_email(host, to_list, subject, body):
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    pwd = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip() or user or "athena@localhost"
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
            requests.post(url, json={"title": title or "Athena", "message": message}, timeout=8)
            sent.append("webhook")
        except Exception as e:
            print(f"[notif webhook] {e}")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_ids = _csv_user("TELEGRAM_CHAT_ID")
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
    to_list = _csv_user("NOTIFY_EMAIL_TO")
    if host and to_list and _wanted("email"):
        try:
            _send_email(host, to_list, title or "Notification Athena", message)
            sent.append("email")
        except Exception as e:
            print(f"[notif email] {e}")

    return sent


# --- Réacteur `run.completed` (bus d'événements) -----------------------------
# Notifie la fin d'un run UNIQUEMENT là où l'utilisateur ne regarde pas la surface
# d'origine : routines planifiées, runs API/webhook/n8n/pipeline, monitoring (Vigie
# sans chat Telegram), run web dont le client s'est déconnecté, et runs VOCAUX longs
# (l'utilisateur est parti pendant la synthèse). JAMAIS le chat en direct
# (web/CLI/Telegram) : la réponse y est déjà visible → sinon spam.
_NOTIFY_CHANNEL_BASES = {"routine", "api", "events", "hook", "n8n", "pipeline"}


def run_completed_reactor(topic, payload):
    if (os.getenv("RUN_COMPLETED_NOTIFY", "true").lower() not in ("true", "1", "yes")):
        return
    p = payload or {}
    if p.get("cancelled"):
        return  # annulé par l'utilisateur : il le sait déjà
    chan = (p.get("channel") or "").strip()
    base = chan.split(":", 1)[0].lower()
    voice_min = int(os.getenv("RUN_COMPLETED_VOICE_MIN_S", "120") or 120)
    wanted = (
        bool(p.get("detached"))                       # client web parti avant la fin
        or base in _NOTIFY_CHANNEL_BASES              # surfaces non interactives
        or (base == "voice" and (p.get("duration_s") or 0) >= voice_min)  # vocal long
    )
    if not wanted:
        return
    agent = p.get("agent") or "?"
    who = f" · {p['user']}" if p.get("user") else ""
    body = (p.get("error") or p.get("response") or "").strip()
    if len(body) > 400:
        body = body[:400] + " …"
    head = "❌ Run en échec" if p.get("error") else "✅ Run terminé"
    notify(f"{head} — {agent} (canal {chan or '?'}{who}, {p.get('duration_s', '?')} s)\n{body}")


def wire_event_bus():
    """Abonne le réacteur au bus (appelé au démarrage du serveur)."""
    from core import event_bus
    event_bus.subscribe("run.completed", run_completed_reactor)

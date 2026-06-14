"""Bot Telegram ENTRANT : reçoit les messages et fait répondre l'essaim.

Long-polling natif (`getUpdates`, aucune lib telegram), dans un thread de fond démarré au
boot du serveur si `TELEGRAM_BOT_TOKEN` est défini. Sécurité :
- **Pairing** (`core.telegram_pairing`) : un inconnu reçoit un code à faire approuver
  (UI Réglages → Messageries, ou `/approve <code>` depuis un chat déjà autorisé). Les chats
  de `TELEGRAM_CHAT_ID` sont autorisés d'office ; le tout premier contact est auto-approuvé
  (amorçage du propriétaire). Désactivable via `TELEGRAM_REQUIRE_PAIRING=false`.
- **Canal `telegram:<chat_id>`** → la politique `core.channels` interdit déjà shell/ssh.
- Confirmations d'outils sensibles : le canal telegram n'auto-approuve pas (cf. channels).

Commandes : /start, /help, /approve <code>, /reset.
"""
import os
import time
import html
import threading
from typing import Dict, List, Optional

import requests

from core import telegram_pairing

_API = "https://api.telegram.org/bot{token}/{method}"
_HISTORY: Dict[str, List[dict]] = {}     # chat_id -> messages (contexte de conversation)
_HISTORY_MAX = 20
_LOCK = threading.RLock()

_thread: Optional[threading.Thread] = None
_running = threading.Event()
_offset = 0
_last_error = ""


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def is_enabled() -> bool:
    return bool(_token())


def status() -> dict:
    return {
        "enabled": is_enabled(),
        "running": _running.is_set() and _thread is not None and _thread.is_alive(),
        "last_error": _last_error,
        "active_chats": len(_HISTORY),
    }


def _call(method: str, **params):
    r = requests.post(_API.format(token=_token(), method=method), json=params, timeout=40)
    return r.json()


def send_message(chat_id, text: str):
    """Envoie un message (découpé si > limite Telegram de 4096)."""
    text = text or "(réponse vide)"
    for i in range(0, len(text), 4000):
        try:
            resp = _call("sendMessage", chat_id=chat_id, text=text[i:i + 4000])
            if not resp.get("ok"):
                # Erreur côté Telegram (chat inconnu, bot bloqué…) — silencieuse avant, loggée ici.
                print(f"[Telegram] sendMessage refusé pour {chat_id} : {resp.get('description')}")
        except Exception as e:
            print(f"[Telegram] envoi échoué : {e}")
            return


# --- Exécution de l'essaim pour un message Telegram -------------------------
def _respond(chat_id: str, user_text: str) -> str:
    """Lance l'essaim sur le message (avec contexte de conversation) et renvoie la réponse."""
    import uuid
    from core.state import swarm, _orch_agent, _orch_name, _current_username
    from core import channels, approvals
    from core.run_context import registry as run_registry, current_run_id

    with _LOCK:
        chain = list(_HISTORY.get(chat_id, []))
    chain.append({"role": "user", "content": user_text, "id": uuid.uuid4().hex[:8]})

    run_id = None
    try:
        from core.tracing import run_store
        run_id = run_store.new_run_id()
    except Exception:
        pass
    rid_token = current_run_id.set(run_id) if run_id else None
    if run_id:
        run_registry.start(run_id)
    chan = f"telegram:{chat_id}"
    chan_token = channels.current_channel.set(chan)
    appr_token = approvals.auto_approve_var.set(channels.auto_approve_for(chan))
    user_token = _current_username.set("local")
    try:
        _next, new_chain, steps = swarm.run(_orch_agent(), chain)
        final = ""
        for m in reversed(new_chain):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                final = m["content"].strip()
                break
        # Mémorise le contexte (borné) pour les échanges suivants.
        with _LOCK:
            _HISTORY[chat_id] = new_chain[-_HISTORY_MAX:]
        return final or "(je n'ai pas de réponse à formuler)"
    finally:
        if run_id:
            run_registry.finish(run_id)
        if rid_token:
            current_run_id.reset(rid_token)
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)
        _current_username.reset(user_token)


# --- Traitement d'un message entrant ----------------------------------------
def _handle_message(msg: dict):
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", ""))
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    print(f"[Telegram] ← message de {chat_id} : {text[:80]!r} "
          f"(autorisé={telegram_pairing.is_allowed(chat_id)})")
    low = text.lower()

    # Commandes accessibles à tous.
    if low in ("/start", "/help"):
        send_message(chat_id,
                     "👋 Bonjour ! Je suis Athena. Écris-moi normalement et je te réponds.\n"
                     "Commandes : /reset (oublier la conversation), /approve <code> "
                     "(pour les administrateurs).")
        # On poursuit la logique de pairing ci-dessous pour /start (1er contact).

    if low == "/reset":
        with _LOCK:
            _HISTORY.pop(chat_id, None)
        send_message(chat_id, "🧹 Conversation oubliée.")
        return

    # /approve <code> : réservé aux chats DÉJÀ autorisés (l'admin approuve un inconnu).
    if low.startswith("/approve"):
        if not telegram_pairing.is_allowed(chat_id):
            send_message(chat_id, "⛔ Réservé à un compte autorisé.")
            return
        code = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
        cid = telegram_pairing.approve_code(code)
        if cid:
            send_message(chat_id, f"✅ Contact {cid} approuvé.")
            try:
                send_message(cid, "✅ Ton accès a été approuvé. Tu peux me parler !")
            except Exception:
                pass
        else:
            send_message(chat_id, "Code introuvable ou déjà utilisé.")
        return

    # --- Contrôle d'accès (pairing) ---
    if not telegram_pairing.is_allowed(chat_id):
        if telegram_pairing.maybe_bootstrap(chat_id):
            send_message(chat_id, "✅ Tu es le premier contact : accès accordé automatiquement. "
                                  "Écris-moi ce que tu veux !")
            return
        if telegram_pairing.required():
            code = telegram_pairing.request_pairing(chat_id)
            send_message(chat_id,
                         f"🔒 Accès non autorisé. Donne ce code à l'administrateur pour qu'il "
                         f"t'approuve (UI Réglages → Messageries, ou /approve {code}) :\n\n{code}")
            # Prévenir les chats déjà autorisés (le propriétaire).
            for owner in telegram_pairing.allowed_chats():
                try:
                    send_message(owner, f"🔔 Demande d'accès Telegram. Code à approuver : {code}")
                except Exception:
                    pass
            return
        # pairing désactivé → on laisse passer.

    if low in ("/start", "/help"):
        return  # déjà répondu, pas de passage à l'essaim

    # --- Réponse de l'essaim ---
    try:
        reply = _respond(chat_id, text)
        print(f"[Telegram] → réponse à {chat_id} ({len(reply)} car.)")
        send_message(chat_id, reply)
    except Exception as e:
        import traceback
        print(f"[Telegram] erreur essaim : {e}\n{traceback.format_exc()}")
        send_message(chat_id, f"⚠️ Erreur interne : {e}")


# --- Boucle de long-polling -------------------------------------------------
def _loop():
    global _offset, _last_error
    # On saute le backlog (messages reçus pendant l'arrêt) au démarrage.
    try:
        data = _call("getUpdates", offset=-1, timeout=0)
        results = data.get("result", []) if data.get("ok") else []
        if results:
            _offset = results[-1]["update_id"] + 1
    except Exception as e:
        _last_error = str(e)

    while _running.is_set():
        try:
            data = _call("getUpdates", offset=_offset, timeout=30)
            if not data.get("ok"):
                _last_error = str(data.get("description", "réponse non-ok"))
                time.sleep(3)
                continue
            _last_error = ""
            for upd in data.get("result", []):
                _offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    try:
                        _handle_message(msg)
                    except Exception as e:
                        print(f"[Telegram] handler : {e}")
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            _last_error = str(e)
            time.sleep(5)


def start():
    """Démarre le bot si un token est configuré (idempotent)."""
    global _thread
    if not is_enabled():
        print("[Telegram] désactivé (TELEGRAM_BOT_TOKEN absent).")
        return
    if _running.is_set():
        return
    _running.set()
    _thread = threading.Thread(target=_loop, name="telegram-bot", daemon=True)
    _thread.start()
    print("[Telegram] bot entrant démarré (long-polling).")


def stop():
    _running.clear()

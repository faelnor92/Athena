"""DM pairing Telegram : seuls les contacts APPROUVÉS peuvent dialoguer avec le bot.

Un inconnu reçoit un code de pairage ; l'administrateur l'approuve (commande
`/approve <code>` depuis un chat autorisé, ou via l'UI Réglages → Messageries).
Les chats listés dans TELEGRAM_CHAT_ID sont autorisés d'office. Désactivable via
TELEGRAM_REQUIRE_PAIRING=false. Au tout premier contact (aucun chat configuré ni
approuvé), ce contact est auto-approuvé (amorçage du propriétaire).
"""
import os
import secrets
import threading

from core import shared_store

# Persistance dans le store SQLite partagé (multi-worker-safe, pas de JSON corruptible).
# Migration douce de l'ancien fichier telegram_paired.json au premier accès.
_PATH = os.getenv("TELEGRAM_PAIRING_PATH", "telegram_paired.json")
_NS = "telegram_pairing"
_lock = threading.Lock()


def _load() -> dict:
    shared_store.migrate_json_dict(_PATH, _NS)   # importe l'ancien JSON une seule fois
    return {
        "approved": shared_store.get(_NS, "approved") or [],
        "pending": shared_store.get(_NS, "pending") or {},
        "users": shared_store.get(_NS, "users") or {},   # chat_id -> compte Athena
    }


def _save(d: dict):
    try:
        shared_store.set(_NS, "approved", d.get("approved", []))
        shared_store.set(_NS, "pending", d.get("pending", {}))
        shared_store.set(_NS, "users", d.get("users", {}))
    except Exception as e:
        print(f"[Pairing] écriture impossible : {e}")


def _configured() -> set:
    return {x.strip() for x in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if x.strip()}


def required() -> bool:
    return os.getenv("TELEGRAM_REQUIRE_PAIRING", "true").lower() in ("true", "1", "yes")


def is_allowed(chat_id) -> bool:
    cid = str(chat_id)
    if cid in _configured():
        return True
    with _lock:
        return cid in _load().get("approved", [])


def allowed_chats() -> list:
    """Chats autorisés (configurés + approuvés) — destinataires des notifications d'accès."""
    with _lock:
        return sorted(_configured() | set(_load().get("approved", [])))


def maybe_bootstrap(chat_id) -> bool:
    """Auto-approuve le 1er contact si aucun chat n'est configuré NI approuvé."""
    cid = str(chat_id)
    with _lock:
        d = _load()
        if not _configured() and not d.get("approved"):
            d["approved"].append(cid)
            _save(d)
            return True
    return False


def request_pairing(chat_id) -> str:
    """Crée (ou retrouve) un code de pairage pour ce chat inconnu."""
    cid = str(chat_id)
    with _lock:
        d = _load()
        for code, c in d["pending"].items():
            if c == cid:
                return code
        code = secrets.token_hex(3).upper()  # 6 caractères
        d["pending"][code] = cid
        _save(d)
        return code


def approve_code(code: str):
    """Approuve la demande correspondant au code. Renvoie le chat_id approuvé ou None."""
    code = (code or "").strip().upper()
    with _lock:
        d = _load()
        cid = d["pending"].pop(code, None)
        if cid and cid not in d["approved"]:
            d["approved"].append(cid)
        if cid:
            _save(d)
        return cid


def approve_chat(chat_id) -> bool:
    cid = str(chat_id)
    with _lock:
        d = _load()
        d["pending"] = {k: v for k, v in d["pending"].items() if v != cid}
        if cid not in d["approved"]:
            d["approved"].append(cid)
        _save(d)
        return True


def revoke_chat(chat_id) -> bool:
    cid = str(chat_id)
    with _lock:
        d = _load()
        before = len(d["approved"])
        d["approved"] = [c for c in d["approved"] if c != cid]
        d.get("users", {}).pop(cid, None)   # plus autorisé → on oublie son utilisateur lié
        _save(d)
        return len(d["approved"]) < before


def set_user(chat_id, username: str) -> bool:
    """Lie un chat Telegram à un utilisateur Athena (agenda/config/mémoire de CE compte).
    username vide = on retire la liaison (retour au compte par défaut)."""
    cid = str(chat_id)
    uname = (username or "").strip()
    with _lock:
        d = _load()
        users = d.setdefault("users", {})
        if uname:
            users[cid] = uname
        else:
            users.pop(cid, None)
        _save(d)
        return True


def user_for(chat_id) -> str:
    """Utilisateur Athena sous lequel exécuter les messages de ce chat.
    Priorité : liaison explicite → TELEGRAM_DEFAULT_USER → 'local'."""
    cid = str(chat_id)
    with _lock:
        u = (_load().get("users", {}) or {}).get(cid)
    return u or (os.getenv("TELEGRAM_DEFAULT_USER", "").strip() or "local")


def pending() -> dict:
    with _lock:
        return dict(_load().get("pending", {}))


def status() -> dict:
    with _lock:
        d = _load()
    return {"required": required(), "configured": sorted(_configured()),
            "approved": d.get("approved", []), "pending": d.get("pending", {}),
            "users": d.get("users", {})}

"""Plan d'action PERSISTANT et éditable (par canal/session).

Le plan affiché par l'agent (make_plan) est aussi mémorisé ici pour pouvoir être relu par
l'agent ET modifié par l'humain à la volée (cocher, ajouter, éditer, supprimer, réordonner)
via l'API/UI.

Persistance : store SQLite partagé (multi-worker-safe). Chaque plan est une entrée
(ns « plans », clé = '<utilisateur>::<client_id>'). Les mutations passent par
shared_store.update() → lecture-modification-écriture ATOMIQUE (BEGIN IMMEDIATE).
Migration douce de l'ancien plans.json au premier accès.
"""
import os
import threading

from core import shared_store

_NS = "plans"
_LOCK = threading.Lock()
_migrated = [False]
_VALID = ("pending", "in_progress", "done", "failed")


def _ensure_migrated():
    if _migrated[0]:
        return
    base = os.getenv("PLANS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plans.json")
    try:
        shared_store.migrate_json_dict(base, _NS)
    except Exception:
        pass
    _migrated[0] = True


def _cid(client_id):
    # Scope PAR UTILISATEUR (cohérent avec les conversations) : préfixe par l'utilisateur
    # courant pour que deux comptes sur le même client_id ne partagent pas leurs plans.
    cid = (client_id or "web").strip() or "web"
    try:
        from core.user_config import current_user_key
        return f"{current_user_key()}::{cid}"
    except Exception:
        return cid


def get_plan(client_id="web"):
    _ensure_migrated()
    return list(shared_store.get(_NS, _cid(client_id)) or [])


def set_plan(client_id, items):
    """Remplace le plan. items: liste de dicts {text, status} ou de str."""
    norm = []
    for it in items or []:
        if isinstance(it, str):
            norm.append({"text": it.strip(), "status": "pending"})
        elif isinstance(it, dict) and (it.get("text") or "").strip():
            st = (it.get("status") or "pending").strip().lower()
            norm.append({"text": it["text"].strip(), "status": st if st in _VALID else "pending"})
    _ensure_migrated()
    shared_store.set(_NS, _cid(client_id), norm)
    return norm


def update_step(client_id, index, status):
    status = (status or "done").strip().lower()
    if status not in _VALID:
        status = "done"
    _ensure_migrated()
    out = {"ok": False}

    def _f(items):
        items = list(items or [])
        if 0 <= index < len(items):
            items[index]["status"] = status
            out["ok"] = True
        return items
    shared_store.update(_NS, _cid(client_id), _f)
    return out["ok"]


def add_step(client_id, text, status="pending"):
    text = (text or "").strip()
    if not text:
        return False
    _ensure_migrated()

    def _f(items):
        items = list(items or [])
        items.append({"text": text, "status": status if status in _VALID else "pending"})
        return items
    shared_store.update(_NS, _cid(client_id), _f)
    return True


def edit_step(client_id, index, text):
    text = (text or "").strip()
    if not text:
        return False
    _ensure_migrated()
    out = {"ok": False}

    def _f(items):
        items = list(items or [])
        if 0 <= index < len(items):
            items[index]["text"] = text
            out["ok"] = True
        return items
    shared_store.update(_NS, _cid(client_id), _f)
    return out["ok"]


def remove_step(client_id, index):
    _ensure_migrated()
    out = {"ok": False}

    def _f(items):
        items = list(items or [])
        if 0 <= index < len(items):
            items.pop(index)
            out["ok"] = True
        return items
    shared_store.update(_NS, _cid(client_id), _f)
    return out["ok"]


def clear_plan(client_id):
    _ensure_migrated()
    shared_store.set(_NS, _cid(client_id), [])


def purge_user(user: str):
    """Supprime tous les plans d'un utilisateur (clés '<user>::...') — suppression de compte."""
    _ensure_migrated()
    pref = f"{(user or '').strip()}::"
    try:
        for k in list((shared_store.items(_NS) or {}).keys()):
            if k.startswith(pref):
                shared_store.delete(_NS, k)
    except Exception:
        pass

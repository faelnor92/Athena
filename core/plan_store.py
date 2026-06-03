"""Plan d'action PERSISTANT et éditable (par canal/session).

Le plan affiché par l'agent (make_plan) est aussi mémorisé ici pour pouvoir être
relu par l'agent ET modifié par l'humain à la volée (cocher, ajouter, éditer,
supprimer, réordonner) via l'API/UI. Écriture atomique + verrou.
"""
import json
import os
import tempfile
import threading

_LOCK = threading.Lock()
_PLANS = {}  # client_id -> [{"text": str, "status": "pending|in_progress|done|failed"}]
_LOADED = False

_VALID = ("pending", "in_progress", "done", "failed")


def _path():
    base = os.getenv("PLANS_PATH", "").strip()
    if base:
        return base
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plans.json")


def _load():
    global _LOADED
    if _LOADED:
        return
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _PLANS.update(data)
    except Exception:
        pass
    _LOADED = True


def _save():
    p = _path()
    directory = os.path.dirname(os.path.abspath(p)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".plans-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_PLANS, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


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
    with _LOCK:
        _load()
        return list(_PLANS.get(_cid(client_id), []))


def set_plan(client_id, items):
    """Remplace le plan. items: liste de dicts {text, status} ou de str."""
    norm = []
    for it in items or []:
        if isinstance(it, str):
            norm.append({"text": it.strip(), "status": "pending"})
        elif isinstance(it, dict) and (it.get("text") or "").strip():
            st = (it.get("status") or "pending").strip().lower()
            norm.append({"text": it["text"].strip(), "status": st if st in _VALID else "pending"})
    with _LOCK:
        _load()
        _PLANS[_cid(client_id)] = norm
        _save()
    return norm


def update_step(client_id, index, status):
    status = (status or "done").strip().lower()
    if status not in _VALID:
        status = "done"
    with _LOCK:
        _load()
        items = _PLANS.get(_cid(client_id), [])
        if 0 <= index < len(items):
            items[index]["status"] = status
            _save()
            return True
    return False


def add_step(client_id, text, status="pending"):
    text = (text or "").strip()
    if not text:
        return False
    with _LOCK:
        _load()
        items = _PLANS.setdefault(_cid(client_id), [])
        items.append({"text": text, "status": status if status in _VALID else "pending"})
        _save()
    return True


def edit_step(client_id, index, text):
    text = (text or "").strip()
    with _LOCK:
        _load()
        items = _PLANS.get(_cid(client_id), [])
        if 0 <= index < len(items) and text:
            items[index]["text"] = text
            _save()
            return True
    return False


def remove_step(client_id, index):
    with _LOCK:
        _load()
        items = _PLANS.get(_cid(client_id), [])
        if 0 <= index < len(items):
            items.pop(index)
            _save()
            return True
    return False


def clear_plan(client_id):
    with _LOCK:
        _load()
        _PLANS[_cid(client_id)] = []
        _save()

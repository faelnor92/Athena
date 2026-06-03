"""Configuration PAR UTILISATEUR (multi-tenant) — générique.

Chaque utilisateur authentifié a son propre jeu de réglages (agenda, et à terme
notifications/préférences…). En mode local sans auth, tout va dans le bucket "local".
Persistance atomique + verrou. Fichier gitignoré (peut contenir des secrets, ex.
mot de passe CalDAV — comme .env, en clair, à protéger au niveau FS).

Distinct de core/state.py (état runtime) et de .env (config GLOBALE du serveur).
"""
import json
import os
import tempfile
import threading

_LOCK = threading.Lock()
_DATA = {}            # {user: {key: value}}
_LOADED = False


def _path():
    p = os.getenv("USER_CONFIGS_PATH", "").strip()
    if p:
        return p
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_configs.json")


def _load():
    global _LOADED
    if _LOADED:
        return
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _DATA.update(data)
    except Exception:
        pass
    _LOADED = True


def _save():
    p = _path()
    directory = os.path.dirname(os.path.abspath(p)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".ucfg-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_DATA, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def current_user_key() -> str:
    """Utilisateur authentifié courant, ou 'local' (mode mono-utilisateur sans auth)."""
    try:
        from core.state import _current_username
        return (_current_username.get() or "local")
    except Exception:
        return "local"


def user_slug(user: str = None) -> str:
    """Forme du nom d'utilisateur sûre pour un nom de fichier (par-utilisateur)."""
    import re
    return re.sub(r"[^A-Za-z0-9_.-]", "_", (user or current_user_key())) or "local"


def get(key: str, default=None, user: str = None):
    user = user or current_user_key()
    with _LOCK:
        _load()
        return _DATA.get(user, {}).get(key, default)


def get_all(user: str = None) -> dict:
    user = user or current_user_key()
    with _LOCK:
        _load()
        return dict(_DATA.get(user, {}))


def set(key: str, value, user: str = None):
    user = user or current_user_key()
    with _LOCK:
        _load()
        _DATA.setdefault(user, {})[key] = value
        _save()


def set_many(mapping: dict, user: str = None):
    user = user or current_user_key()
    with _LOCK:
        _load()
        bucket = _DATA.setdefault(user, {})
        for k, v in (mapping or {}).items():
            bucket[k] = v
        _save()


def delete(key: str, user: str = None) -> bool:
    user = user or current_user_key()
    with _LOCK:
        _load()
        if key in _DATA.get(user, {}):
            del _DATA[user][key]
            _save()
            return True
    return False

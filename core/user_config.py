"""Configuration PAR UTILISATEUR (multi-tenant) — générique.

Chaque utilisateur authentifié a son propre jeu de réglages (agenda, et à terme
notifications/préférences…). En mode local sans auth, tout va dans le bucket "local".
Persistance atomique + verrou. Fichier gitignoré (peut contenir des secrets, ex.
mot de passe CalDAV — comme .env, en clair, à protéger au niveau FS).

Distinct de core/state.py (état runtime) et de .env (config GLOBALE du serveur).
"""
import os

from core import shared_store

_NS = "user_config"        # une entrée par utilisateur : user -> {key: value}
_migrated = False


def _ensure_migrated():
    """Importe une fois un éventuel user_configs.json hérité ({user:{...}}) dans SQLite."""
    global _migrated
    if _migrated:
        return
    legacy = os.getenv("USER_CONFIGS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_configs.json")
    shared_store.migrate_json_dict(legacy, _NS)
    _migrated = True


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
    _ensure_migrated()
    return (shared_store.get(_NS, user) or {}).get(key, default)


def get_all(user: str = None) -> dict:
    user = user or current_user_key()
    _ensure_migrated()
    return dict(shared_store.get(_NS, user) or {})


def set(key: str, value, user: str = None):
    user = user or current_user_key()
    _ensure_migrated()

    def _set(bucket):
        bucket = bucket or {}
        bucket[key] = value
        return bucket
    shared_store.update(_NS, user, _set)


def set_many(mapping: dict, user: str = None):
    user = user or current_user_key()
    _ensure_migrated()

    def _set(bucket):
        bucket = bucket or {}
        for k, v in (mapping or {}).items():
            bucket[k] = v
        return bucket
    shared_store.update(_NS, user, _set)


def delete(key: str, user: str = None) -> bool:
    user = user or current_user_key()
    _ensure_migrated()
    outcome = {"ok": False}

    def _del(bucket):
        bucket = bucket or {}
        if key in bucket:
            del bucket[key]
            outcome["ok"] = True
        return bucket
    shared_store.update(_NS, user, _del)
    return outcome["ok"]


def delete_user(user: str) -> bool:
    """Supprime entièrement la config d'un utilisateur (suppression de compte)."""
    _ensure_migrated()
    return shared_store.delete(_NS, user)

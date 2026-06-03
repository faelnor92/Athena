"""Comptes utilisateurs (multi-utilisateur du foyer) avec rôles.

Stocke username -> {hash PBKDF2, rôle}. Aucun mot de passe en clair. Si aucun
utilisateur n'existe et qu'ADMIN_PASSWORD est défini, ce dernier sert d'admin
« bootstrap » (cf. server.login) pour créer les premiers comptes.
"""
import hashlib
import json
import os
import secrets
import threading

USERS_PATH = os.getenv("USERS_PATH", "users.json")


def hash_password(password: str, salt: str = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"{salt}${h}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except (ValueError, AttributeError):
        return False
    candidate = hash_password(password, salt).split("$", 1)[1]
    return secrets.compare_digest(candidate, h)


_NS = "users"


class UserStore:
    """Comptes utilisateurs, adossés au store SQLite partagé (process-safe, multi-worker).

    L'argument `path` (compat) sert uniquement à migrer un éventuel users.json existant.
    """
    def __init__(self, path: str = None):
        from core import shared_store
        self._s = shared_store
        self._s.migrate_json_dict(path or USERS_PATH, _NS)

    def count(self) -> int:
        return self._s.count(_NS)

    def list(self) -> list:
        return [{"username": u, "role": d.get("role", "user"),
                 "quota_max_tokens": d.get("quota_max_tokens"),
                 "tokens_used_today": d.get("tokens_used_today", 0)}
                for u, d in self._s.items(_NS).items()]

    def create(self, username: str, password: str, role: str = "user") -> bool:
        username = (username or "").strip()
        if not username or not password:
            return False
        import datetime
        self._s.set(_NS, username, {
            "hash": hash_password(password),
            "role": role if role in ("admin", "user") else "user",
            "quota_max_tokens": None,  # None = illimité
            "tokens_used_today": 0,
            "last_reset_date": datetime.date.today().isoformat(),
        })
        return True

    def set_password(self, username: str, password: str) -> bool:
        def _set(d):
            if d is None:
                raise KeyError
            d["hash"] = hash_password(password)
            return d
        try:
            self._s.update(_NS, username, _set)
            return True
        except KeyError:
            return False

    def set_quota(self, username: str, max_tokens) -> bool:
        """Définit le quota journalier de tokens (None/0 = illimité)."""
        def _set(d):
            if d is None:
                raise KeyError
            d["quota_max_tokens"] = max_tokens
            return d
        try:
            self._s.update(_NS, username, _set)
            return True
        except KeyError:
            return False

    def delete(self, username: str) -> bool:
        return self._s.delete(_NS, username)

    def verify(self, username: str, password: str):
        """Renvoie le rôle si identifiants valides, sinon None."""
        d = self._s.get(_NS, username)
        if d and verify_password(password, d.get("hash", "")):
            return d.get("role", "user")
        return None

    def check_quota(self, username: str, required_tokens: int = 0) -> bool:
        """True si l'utilisateur a encore du quota aujourd'hui (False si dépassé)."""
        import datetime
        d = self._s.get(_NS, username)
        if not d:
            return True  # utilisateur inconnu (système) → on laisse passer
        quota_max = d.get("quota_max_tokens")
        if quota_max is None or quota_max <= 0:
            return True  # illimité
        today = datetime.date.today().isoformat()
        used = d.get("tokens_used_today", 0) if d.get("last_reset_date") == today else 0
        return (used + required_tokens) <= quota_max

    # --- 2FA / TOTP (secret stocké chiffré) ---------------------------------
    def set_mfa(self, username: str, secret_enc: str, enabled: bool) -> bool:
        def _set(d):
            if d is None:
                raise KeyError
            d["mfa"] = {"secret": secret_enc, "enabled": bool(enabled)}
            return d
        try:
            self._s.update(_NS, username, _set)
            return True
        except KeyError:
            return False

    def get_mfa(self, username: str):
        """Renvoie {'secret': <chiffré>, 'enabled': bool} ou None."""
        return (self._s.get(_NS, username) or {}).get("mfa")

    def mfa_enabled(self, username: str) -> bool:
        m = self.get_mfa(username)
        return bool(m and m.get("enabled"))

    def clear_mfa(self, username: str) -> bool:
        def _clr(d):
            if d is None:
                return None
            d.pop("mfa", None)
            return d
        self._s.update(_NS, username, _clr)
        return True

    def consume_tokens(self, username: str, amount: int):
        """Incrémente la conso du jour de façon ATOMIQUE (sûr en multi-process)."""
        import datetime
        if amount <= 0:
            return
        today = datetime.date.today().isoformat()

        def _bump(d):
            if d is None:
                return None  # utilisateur inconnu → ne rien créer
            if d.get("last_reset_date") != today:
                d["tokens_used_today"] = 0
                d["last_reset_date"] = today
            d["tokens_used_today"] = d.get("tokens_used_today", 0) + amount
            return d
        self._s.update(_NS, username, _bump)


user_store = UserStore()

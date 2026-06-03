"""Invitations d'inscription : un admin génère un code/lien ; l'invité crée lui-même
son compte via ce code (rôle pré-défini, expiration, usage unique). Évite la création
manuelle de chaque compte sans ouvrir l'inscription à tout le monde.
"""
import json
import os
import secrets
import threading
import time


_NS = "invites"


class InviteStore:
    """Invitations adossées au store SQLite partagé (process-safe, multi-worker)."""
    def __init__(self, path: str = None):
        from core import shared_store
        self._s = shared_store
        self._s.migrate_json_dict(path or os.getenv("INVITES_PATH", "invites.json"), _NS)

    def create(self, role: str = "user", expires_hours: int = 168, created_by: str = "") -> dict:
        code = secrets.token_urlsafe(16)
        inv = {
            "code": code,
            "role": role if role in ("admin", "user") else "user",
            "created_by": created_by,
            "created_at": time.time(),
            "expires_at": time.time() + max(1, int(expires_hours or 168)) * 3600,
            "used_by": None,
            "used_at": None,
        }
        self._s.set(_NS, code, inv)
        return inv

    def list(self) -> list:
        return self._s.values(_NS)

    def revoke(self, code: str) -> bool:
        return self._s.delete(_NS, code)

    def check(self, code: str):
        """Renvoie l'invitation si VALIDE (existe, non utilisée, non expirée), sinon None."""
        inv = self._s.get(_NS, code)
        if not inv or inv.get("used_by") or inv.get("expires_at", 0) < time.time():
            return None
        return inv

    def consume(self, code: str, username: str) -> bool:
        """Marque l'invitation comme utilisée de façon ATOMIQUE. False si déjà prise/invalide."""
        outcome = {"ok": False}

        def _use(inv):
            if not inv or inv.get("used_by") or inv.get("expires_at", 0) < time.time():
                return inv  # inchangé (invalide / déjà prise)
            inv["used_by"] = username
            inv["used_at"] = time.time()
            outcome["ok"] = True
            return inv
        if self._s.get(_NS, code) is None:
            return False
        self._s.update(_NS, code, _use)
        return outcome["ok"]


invite_store = InviteStore()

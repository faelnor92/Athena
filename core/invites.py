"""Invitations d'inscription : un admin génère un code/lien ; l'invité crée lui-même
son compte via ce code (rôle pré-défini, expiration, usage unique). Évite la création
manuelle de chaque compte sans ouvrir l'inscription à tout le monde.
"""
import json
import os
import secrets
import threading
import time


class InviteStore:
    def __init__(self, path: str = None):
        self.path = path or os.getenv("INVITES_PATH", "invites.json")
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Invites] sauvegarde impossible : {e}")

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
        with self._lock:
            self._data[code] = inv
            self._save()
        return inv

    def list(self) -> list:
        with self._lock:
            return list(self._data.values())

    def revoke(self, code: str) -> bool:
        with self._lock:
            if code in self._data:
                del self._data[code]
                self._save()
                return True
            return False

    def check(self, code: str):
        """Renvoie l'invitation si VALIDE (existe, non utilisée, non expirée), sinon None."""
        with self._lock:
            inv = self._data.get(code)
        if not inv or inv.get("used_by") or inv.get("expires_at", 0) < time.time():
            return None
        return inv

    def consume(self, code: str, username: str) -> bool:
        """Marque l'invitation comme utilisée (atomique). False si déjà prise/invalide."""
        with self._lock:
            inv = self._data.get(code)
            if not inv or inv.get("used_by") or inv.get("expires_at", 0) < time.time():
                return False
            inv["used_by"] = username
            inv["used_at"] = time.time()
            self._save()
            return True


invite_store = InviteStore()

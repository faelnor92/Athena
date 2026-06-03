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


class UserStore:
    def __init__(self, path: str = None):
        self.path = path or USERS_PATH
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
            print(f"[Users] sauvegarde impossible : {e}")

    def count(self) -> int:
        with self._lock:
            return len(self._data)

    def list(self) -> list:
        with self._lock:
            return [{"username": u, "role": d.get("role", "user"), "quota_max_tokens": d.get("quota_max_tokens"), "tokens_used_today": d.get("tokens_used_today", 0)} for u, d in self._data.items()]

    def create(self, username: str, password: str, role: str = "user") -> bool:
        username = (username or "").strip()
        if not username or not password:
            return False
        import datetime
        today = datetime.date.today().isoformat()
        with self._lock:
            self._data[username] = {
                "hash": hash_password(password), 
                "role": role if role in ("admin", "user") else "user",
                "quota_max_tokens": None, # None means unlimited
                "tokens_used_today": 0,
                "last_reset_date": today
            }
            self._save()
            return True

    def set_password(self, username: str, password: str) -> bool:
        with self._lock:
            if username not in self._data:
                return False
            self._data[username]["hash"] = hash_password(password)
            self._save()
            return True

    def delete(self, username: str) -> bool:
        with self._lock:
            if username in self._data:
                del self._data[username]
                self._save()
                return True
            return False

    def verify(self, username: str, password: str):
        """Renvoie le rôle si identifiants valides, sinon None."""
        with self._lock:
            d = self._data.get(username)
        if d and verify_password(password, d.get("hash", "")):
            return d.get("role", "user")
        return None

    def check_quota(self, username: str, required_tokens: int = 0) -> bool:
        """Vérifie si l'utilisateur a suffisamment de quota (True si OK, False si dépassé)."""
        import datetime
        with self._lock:
            d = self._data.get(username)
            if not d:
                return True # Si l'utilisateur n'existe pas (ex: système), on laisse passer
            
            quota_max = d.get("quota_max_tokens")
            if quota_max is None or quota_max <= 0:
                return True # Illimité
            
            today = datetime.date.today().isoformat()
            last_reset = d.get("last_reset_date", "")
            if last_reset != today:
                # Nouveau jour, on reset
                d["tokens_used_today"] = 0
                d["last_reset_date"] = today
                self._save()
                
            used = d.get("tokens_used_today", 0)
            return (used + required_tokens) <= quota_max

    def consume_tokens(self, username: str, amount: int):
        """Consomme des tokens pour l'utilisateur."""
        import datetime
        if amount <= 0: return
        with self._lock:
            d = self._data.get(username)
            if not d: return
            
            today = datetime.date.today().isoformat()
            last_reset = d.get("last_reset_date", "")
            if last_reset != today:
                d["tokens_used_today"] = 0
                d["last_reset_date"] = today
                
            d["tokens_used_today"] = d.get("tokens_used_today", 0) + amount
            self._save()


user_store = UserStore()

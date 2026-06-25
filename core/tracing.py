"""Persistance des runs de l'essaim (observabilité / tracing).

Chaque requête de chat reçoit un run_id et est sauvegardée (SQLite) avec ses
étapes, ses tokens, son coût, sa durée et son statut — afin de pouvoir
inspecter ou rejouer un run raté au lieu de tout perdre en RAM.
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_DEFAULT_DB = os.getenv("RUNS_DB_PATH", "runs.sqlite3")


def _enc(s):
    """Chiffre une chaîne (au repos) si possible ; sinon la renvoie telle quelle."""
    if not s:
        return s
    try:
        from core.state import _encrypt
        return _encrypt(s)
    except Exception:
        return s


def _dec(s):
    """Déchiffre une chaîne ; fallback migration douce (anciennes lignes en clair)."""
    if not s:
        return s
    try:
        from core.state import _decrypt
        return _decrypt(s)
    except Exception:
        return s


class RunStore:
    def __init__(self, db_path: str = _DEFAULT_DB):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id        TEXT PRIMARY KEY,
                    created_at    REAL,
                    agent         TEXT,
                    status        TEXT,
                    user_message  TEXT,
                    final_response TEXT,
                    duration_ms   INTEGER,
                    total_tokens  INTEGER,
                    total_cost    REAL,
                    error         TEXT,
                    steps_json    TEXT
                )
                """
            )
            # Migration : colonne `user` (usage par utilisateur). Idempotent.
            try:
                conn.execute("ALTER TABLE runs ADD COLUMN user TEXT")
            except Exception:
                pass  # colonne déjà présente

    @staticmethod
    def new_run_id() -> str:
        return uuid.uuid4().hex

    def save(
        self,
        run_id: str,
        agent: str,
        status: str,
        user_message: str = "",
        final_response: str = "",
        duration_ms: int = 0,
        total_tokens: int = 0,
        total_cost: float = 0.0,
        error: Optional[str] = None,
        steps: Optional[List[dict]] = None,
        created_at: Optional[float] = None,
    ):
        try:
            from core.redaction import redact_secrets
            # Redaction des secrets PUIS chiffrement au repos du contenu sensible.
            steps_json = _enc(redact_secrets(json.dumps(steps or [], ensure_ascii=False)))
            # Utilisateur courant (usage par compte), résolu sans changer les appelants.
            try:
                from core.user_config import current_user_key
                user = current_user_key()
            except Exception:
                user = "local"
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs
                    (run_id, created_at, agent, status, user_message, final_response,
                     duration_ms, total_tokens, total_cost, error, steps_json, user)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        run_id,
                        created_at if created_at is not None else time.time(),
                        agent,
                        status,
                        _enc(redact_secrets(user_message)),
                        _enc(redact_secrets(final_response)),
                        int(duration_ms),
                        int(total_tokens),
                        float(total_cost),
                        _enc(redact_secrets(error)),
                        steps_json,
                        user,
                    ),
                )
        except Exception:
            # L'observabilité ne doit jamais casser le chemin principal.
            pass

    def usage_by_user(self, since: float = None) -> list:
        """Agrège l'usage (requêtes, tokens, coût) par utilisateur depuis `since` (epoch)."""
        q = ("SELECT COALESCE(user,'local') AS u, COUNT(*) AS runs, "
             "COALESCE(SUM(total_tokens),0) AS tokens, COALESCE(SUM(total_cost),0) AS cost "
             "FROM runs")
        params = []
        if since:
            q += " WHERE created_at >= ?"
            params.append(since)
        q += " GROUP BY u ORDER BY cost DESC"
        try:
            with self._lock, self._connect() as conn:
                return [dict(r) for r in conn.execute(q, params).fetchall()]
        except Exception:
            return []

    def usage_for(self, user: str, since: float = None) -> dict:
        """Usage d'UN utilisateur (requêtes, tokens, coût) depuis `since`."""
        rows = self.usage_by_user(since)
        for r in rows:
            if r["u"] == user:
                return r
        return {"u": user, "runs": 0, "tokens": 0, "cost": 0.0}

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        # Déchiffrement du contenu sensible (au repos).
        for k in ("user_message", "final_response", "error"):
            if data.get(k):
                data[k] = _dec(data[k])
        try:
            data["steps"] = json.loads(_dec(data.pop("steps_json")) or "[]")
        except Exception:
            data["steps"] = []
        return data

    def cost_today(self) -> float:
        """Somme des coûts des runs depuis minuit (pour les alertes de budget)."""
        import datetime
        start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(total_cost), 0) FROM runs WHERE created_at >= ?", (start,)
                ).fetchone()
            return float(row[0] or 0)
        except Exception:
            return 0.0

    def list(self, limit: int = 50, status: Optional[str] = None,
             user: Optional[str] = None) -> List[Dict[str, Any]]:
        query = ("SELECT run_id, created_at, agent, status, user_message, duration_ms, "
                 "total_tokens, total_cost, error, user FROM runs")
        conds: list = []
        params: list = []
        if status:
            conds.append("status = ?")
            params.append(status)
        if user:
            conds.append("user = ?")
            params.append(user)
        if conds:
            query += " WHERE " + " AND ".join(conds)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("user_message"):
                d["user_message"] = _dec(d["user_message"])
            out.append(d)
        return out


# Singleton applicatif
run_store = RunStore()

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
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO runs
                    (run_id, created_at, agent, status, user_message, final_response,
                     duration_ms, total_tokens, total_cost, error, steps_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        run_id,
                        created_at if created_at is not None else time.time(),
                        agent,
                        status,
                        user_message,
                        final_response,
                        int(duration_ms),
                        int(total_tokens),
                        float(total_cost),
                        error,
                        json.dumps(steps or [], ensure_ascii=False),
                    ),
                )
        except Exception:
            # L'observabilité ne doit jamais casser le chemin principal.
            pass

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["steps"] = json.loads(data.pop("steps_json") or "[]")
        except Exception:
            data["steps"] = []
        return data

    def list(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT run_id, created_at, agent, status, user_message, duration_ms, total_tokens, total_cost, error FROM runs"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# Singleton applicatif
run_store = RunStore()

"""Journal d'audit — trace append-only des événements de sécurité.

Connexions (réussies/échouées), déconnexions, changements de mot de passe, gestion des
comptes et invitations, validations d'automatisations par un admin… Stocké dans la base
partagée (athena_state.sqlite3, WAL) → cohérent multi-worker, consultable par un admin.

Volontairement « best-effort » : journaliser ne doit jamais casser le chemin principal.
"""
import sqlite3
import threading
import time

from core import shared_store

_local = threading.local()
_init = False
_init_lock = threading.Lock()

_COLS = ["id", "ts", "actor", "role", "action", "target", "ip", "detail"]


def _conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(shared_store.db_path(), timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        _ensure_schema(c)
        _local.conn = c
    return c


def _ensure_schema(c):
    global _init
    if _init:
        return
    with _init_lock:
        if _init:
            return
        c.execute(
            """CREATE TABLE IF NOT EXISTS audit (
                   id      INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts      REAL,
                   actor   TEXT,
                   role    TEXT,
                   action  TEXT,
                   target  TEXT,
                   ip      TEXT,
                   detail  TEXT
               )"""
        )
        c.commit()
        _init = True


def log(action: str, actor: str = "?", role: str = "", target: str = "", ip: str = "", detail: str = ""):
    """Enregistre un événement (best-effort : avale toute erreur)."""
    try:
        from core.redaction import redact_secrets
        c = _conn()
        c.execute(
            "INSERT INTO audit (ts, actor, role, action, target, ip, detail) VALUES (?,?,?,?,?,?,?)",
            (time.time(), str(actor)[:120], str(role)[:32], str(action)[:64],
             str(target)[:300], str(ip)[:64], redact_secrets(str(detail))[:1000]),
        )
        c.commit()
    except Exception:
        pass


def recent(limit: int = 200, action: str = None) -> list:
    try:
        c = _conn()
        q = "SELECT id, ts, actor, role, action, target, ip, detail FROM audit"
        params = []
        if action:
            q += " WHERE action = ?"
            params.append(action)
        q += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        return [dict(zip(_COLS, r)) for r in c.execute(q, params).fetchall()]
    except Exception:
        return []


def client_ip(request) -> str:
    """IP de l'appelant en tenant compte d'un reverse-proxy (X-Forwarded-For)."""
    try:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "?"
    except Exception:
        return "?"

"""Stockage clé-valeur PARTAGÉ et process-safe (SQLite + WAL).

Backend commun des états mutables qui doivent rester cohérents entre plusieurs
workers uvicorn (`--workers N`) : comptes utilisateurs (+ quotas), routines,
invitations, projets partagés, config par-utilisateur, sessions d'auth.

Pourquoi : les anciens stores gardaient un dict en mémoire + un fichier JSON
réécrit en entier. C'est correct en mono-process, mais en multi-worker chaque
process a SA copie → les écritures s'écrasent et les quotas/sessions divergent.
Ici tout passe par une seule base SQLite en mode WAL : lectures concurrentes,
écritures sérialisées par SQLite, et `update()` atomique (transaction IMMEDIATE)
pour les compteurs (ex. quota de tokens). Sûr en multi-thread ET multi-process.

Modèle : table kv(ns, k, v_json, updated_at), clé primaire (ns, k).
"""
import json
import os
import sqlite3
import threading
import time

_DB_PATH = os.getenv("STATE_DB_PATH", "").strip() or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "athena_state.sqlite3")

# Une connexion par thread (les connexions SQLite ne se partagent pas entre threads).
_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(_DB_PATH, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        c.execute("PRAGMA synchronous=NORMAL")
        _ensure_schema(c)
        _local.conn = c
    return c


def _ensure_schema(c):
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        c.execute(
            """CREATE TABLE IF NOT EXISTS kv (
                   ns          TEXT NOT NULL,
                   k           TEXT NOT NULL,
                   v           TEXT,
                   updated_at  REAL,
                   PRIMARY KEY (ns, k)
               )"""
        )
        c.commit()
        _initialized = True


def get(ns: str, k: str, default=None):
    row = _conn().execute("SELECT v FROM kv WHERE ns=? AND k=?", (ns, k)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except Exception:
        return default


def set(ns: str, k: str, value) -> None:
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO kv (ns, k, v, updated_at) VALUES (?,?,?,?)",
        (ns, k, json.dumps(value, ensure_ascii=False), time.time()),
    )
    c.commit()


def delete(ns: str, k: str) -> bool:
    c = _conn()
    cur = c.execute("DELETE FROM kv WHERE ns=? AND k=?", (ns, k))
    c.commit()
    return cur.rowcount > 0


def items(ns: str) -> dict:
    """Tout le namespace sous forme {k: value}."""
    out = {}
    for k, v in _conn().execute("SELECT k, v FROM kv WHERE ns=?", (ns,)).fetchall():
        try:
            out[k] = json.loads(v)
        except Exception:
            continue
    return out


def values(ns: str) -> list:
    return list(items(ns).values())


def count(ns: str) -> int:
    return _conn().execute("SELECT COUNT(*) FROM kv WHERE ns=?", (ns,)).fetchone()[0]


def update(ns: str, k: str, fn, default=None):
    """Lecture-modification-écriture ATOMIQUE et inter-process (transaction IMMEDIATE).

    `fn(valeur_actuelle_ou_default) -> nouvelle_valeur`. Indispensable pour les
    compteurs concurrents (quota de tokens) afin d'éviter les pertes de mise à jour.
    Si `fn` renvoie None, l'entrée est supprimée.
    """
    c = _conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT v FROM kv WHERE ns=? AND k=?", (ns, k)).fetchone()
        cur = default
        if row:
            try:
                cur = json.loads(row[0])
            except Exception:
                cur = default
        new = fn(cur)
        if new is None:
            c.execute("DELETE FROM kv WHERE ns=? AND k=?", (ns, k))
        else:
            c.execute(
                "INSERT OR REPLACE INTO kv (ns, k, v, updated_at) VALUES (?,?,?,?)",
                (ns, k, json.dumps(new, ensure_ascii=False), time.time()),
            )
        c.commit()
        return new
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass
        raise


def db_path() -> str:
    return _DB_PATH


def checkpoint() -> None:
    """Rapatrie le WAL dans le fichier principal (cohérence pour une sauvegarde à froid)."""
    try:
        _conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _conn().commit()
    except Exception:
        pass


def migrate_json_dict(path: str, ns: str) -> bool:
    """Importe une fois un fichier JSON hérité {k: v} dans le namespace `ns`.

    NON destructif : le fichier source est CONSERVÉ (backup). L'idempotence repose
    sur un marqueur en base (namespace `_migrated`), pas sur le renommage du fichier
    — ainsi un import n'est jamais rejoué (même si l'utilisateur vide ensuite le
    namespace) et aucune donnée réelle n'est perdue si le code est importé dans un
    autre contexte (tests, autre base)."""
    if not path or not os.path.exists(path):
        return False
    # Déjà des données, ou migration déjà effectuée pour ce namespace → on ne touche à rien.
    if count(ns) > 0 or get("_migrated", ns):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    for k, v in data.items():
        set(ns, k, v)
    set("_migrated", ns, True)
    return True

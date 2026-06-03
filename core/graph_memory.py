"""Mémoire-graphe légère : stocke des relations (sujet, relation, objet) et permet
d'interroger le VOISINAGE d'une entité — complément du RAG vectoriel (ChromaDB) qui,
lui, ne capture que la similarité de texte. Pur-Python (aucune dépendance tierce), 
persistance atomique sous SQLite. Ce n'est PAS du GraphRAG complet (pas d'extraction 
massive ni de communautés) : juste un graphe de faits reliés, le « 20 % qui donne 80 % ».

PAR UTILISATEUR : chaque utilisateur a ses propres relations (graph_memory_<user>.db),
résolu à chaque accès via core.user_config.
"""
import json
import os
import sqlite3
import threading
from contextlib import closing

_MAX = int(os.getenv("GRAPH_MEMORY_MAX", "5000") or 5000)

def _key() -> str:
    from core.user_config import current_user_key
    return current_user_key()

def _base_path() -> str:
    return os.getenv("GRAPH_MEMORY_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graph_memory.json")

def _db_path() -> str:
    from core.user_config import user_slug
    base = _base_path()
    root, _ = os.path.splitext(base)
    return f"{root}_{user_slug()}.db"

def _json_path() -> str:
    from core.user_config import user_slug
    base = _base_path()
    root, ext = os.path.splitext(base)
    return f"{root}_{user_slug()}{ext or '.json'}"

def _get_conn():
    """Ouvre une connexion SQLite locale et effectue la migration si nécessaire."""
    db_file = _db_path()
    json_file = _json_path()
    needs_migration = not os.path.exists(db_file) and os.path.exists(json_file)
    
    os.makedirs(os.path.dirname(os.path.abspath(db_file)) or ".", exist_ok=True)
    
    # check_same_thread=False permet un usage multithread si nécessaire,
    # bien qu'on ouvre/ferme localement pour être 100% sûr et sans lock global.
    conn = sqlite3.connect(db_file, check_same_thread=False)
    
    # Mode WAL pour des performances concurrentes maximales
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Création du schéma
    conn.execute('''
        CREATE TABLE IF NOT EXISTS triples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            s TEXT NOT NULL,
            r TEXT NOT NULL,
            o TEXT NOT NULL,
            UNIQUE(s, r, o)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_s ON triples(s COLLATE NOCASE)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_o ON triples(o COLLATE NOCASE)')
    
    if needs_migration:
        _migrate_from_json(conn, json_file)
        
    return conn

def _migrate_from_json(conn, json_file):
    """Migre les données de l'ancien format JSON vers SQLite."""
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            with conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO triples (s, r, o) VALUES (?, ?, ?)",
                    [(t.get("s", ""), t.get("r", ""), t.get("o", "")) for t in data]
                )
        # Renomme le fichier JSON en backup
        os.rename(json_file, json_file + ".bak")
    except Exception:
        pass

def _norm(x):
    return " ".join((x or "").strip().split())

def add_triple(s, r, o):
    s, r, o = _norm(s), _norm(r), _norm(o)
    if not s or not o:
        return False
    with closing(_get_conn()) as conn:
        with conn:
            try:
                # Vérifie d'abord la limite MAX (optionnel mais maintient le comportement précédent)
                count = conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
                if count >= _MAX:
                    # Supprime le plus vieux (basé sur l'ID)
                    conn.execute("DELETE FROM triples WHERE id IN (SELECT id FROM triples ORDER BY id ASC LIMIT 1)")
                
                conn.execute("INSERT OR IGNORE INTO triples (s, r, o) VALUES (?, ?, ?)", (s, r, o))
                # sqlite3 cursor.rowcount vaut 0 si ignoré
            except Exception:
                return False
    return True

def add_triples(triples):
    n = 0
    with closing(_get_conn()) as conn:
        with conn:
            for t in triples or []:
                s, r, o = "", "", ""
                if isinstance(t, (list, tuple)) and len(t) >= 3:
                    s, r, o = _norm(t[0]), _norm(t[1]), _norm(t[2])
                elif isinstance(t, dict):
                    s, r, o = _norm(t.get("s")), _norm(t.get("r")), _norm(t.get("o"))
                
                if s and o:
                    try:
                        conn.execute("INSERT OR IGNORE INTO triples (s, r, o) VALUES (?, ?, ?)", (s, r, o))
                        n += 1
                    except Exception:
                        pass
    return n

def neighborhood(entity, depth=1):
    """Renvoie les triplets touchant `entity` (sujet OU objet), étendus de `depth` sauts."""
    ent = _norm(entity).lower()
    if not ent:
        return []
        
    result_triples = []
    seen_entities = set([ent])
    frontier = set([ent])
    
    with closing(_get_conn()) as conn:
        for _ in range(max(1, depth)):
            next_frontier = set()
            for f in frontier:
                # Recherche des triplets où la frontière est contenue dans le sujet ou l'objet (insensible à la casse)
                like_pattern = f"%{f}%"
                rows = conn.execute(
                    "SELECT s, r, o FROM triples WHERE s LIKE ? OR o LIKE ?", 
                    (like_pattern, like_pattern)
                ).fetchall()
                
                for row in rows:
                    s, r, o = row
                    t = {"s": s, "r": r, "o": o}
                    
                    if t not in result_triples:
                        result_triples.append(t)
                        sl, ol = s.lower(), o.lower()
                        if sl not in seen_entities:
                            seen_entities.add(sl)
                            next_frontier.add(sl)
                        if ol not in seen_entities:
                            seen_entities.add(ol)
                            next_frontier.add(ol)
            frontier = next_frontier
            if not frontier:
                break
                
    return result_triples

def stats():
    with closing(_get_conn()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
        return {"triples": count}

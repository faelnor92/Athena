"""Mémoire-graphe légère : stocke des relations (sujet, relation, objet) et permet
d'interroger le VOISINAGE d'une entité — complément du RAG vectoriel (ChromaDB) qui,
lui, ne capture que la similarité de texte. Pur-Python (aucune dépendance tierce), 
persistance atomique sous SQLite. Ce n'est PAS du GraphRAG complet (pas d'extraction 
massive ni de communautés) : juste un graphe de faits reliés, le « 20 % qui donne 80 % ».

PAR UTILISATEUR : chaque utilisateur a ses propres relations (graph_memory_<user>.db),
résolu à chaque accès via core.user_config.
"""
import glob as _glob
import json
import os
import sqlite3
import threading
import time
import unicodedata
from contextlib import closing

_MAX = int(os.getenv("GRAPH_MEMORY_MAX", "5000") or 5000)

# ── Hygiène long terme ─────────────────────────────────────────────────────────
# Sans consolidation, les faits s'accumulent sans fin et le RAG resurface du bruit :
# - DÉCROISSANCE : un fait jamais RE-confirmé depuis GRAPH_FACT_TTL_DAYS est ARCHIVÉ
#   (invisible des requêtes, pas supprimé) ; archivé depuis 2×TTL → purgé.
# - RE-CONFIRMATION : ré-apprendre un fait existant incrémente son compteur `seen`
#   et rafraîchit `last_seen` (et le désarchive) → les faits vivants ne meurent pas.
# - CONTRADICTION : pour une relation FONCTIONNELLE (une seule valeur possible :
#   domicile, âge, métier…), un nouveau (s, r, o2) ARCHIVE l'ancien (s, r, o1) —
#   le plus récent gagne, l'ancien reste consultable jusqu'à sa purge.
_FACT_TTL_DAYS = int(os.getenv("GRAPH_FACT_TTL_DAYS", "180") or 180)
_FUNCTIONAL_DEFAULT = ("habite,vit a,reside,travaille chez,travaille a,travaille pour,"
                       "a pour metier,a pour age,est age,a pour email,a pour adresse,"
                       "a pour telephone,s appelle,est marie,est en couple,"
                       "a pour anniversaire,est ne,a pour voiture,utilise comme modele")


def _fold(x: str) -> str:
    """Normalisation de comparaison : minuscules + accents retirés + espaces pliés."""
    x = unicodedata.normalize("NFKD", (x or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(x.lower().replace("'", " ").split())


def _is_functional(rel: str) -> bool:
    raw = os.getenv("GRAPH_FUNCTIONAL_RELATIONS", "").strip() or _FUNCTIONAL_DEFAULT
    rf = _fold(rel)
    return any(m.strip() and m.strip() in rf for m in raw.split(","))

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
    _migrate_columns(conn)
    
    if needs_migration:
        _migrate_from_json(conn, json_file)
        
    return conn

def _migrate_columns(conn):
    """Migration douce (hygiène long terme) : timestamps + compteur de re-confirmation
    + archivage. ALTER ignoré si les colonnes existent déjà."""
    _now = time.time()
    for coldef, backfill in (
            ("created_at REAL", f"UPDATE triples SET created_at={_now} WHERE created_at IS NULL"),
            ("last_seen REAL", f"UPDATE triples SET last_seen={_now} WHERE last_seen IS NULL"),
            ("seen INTEGER DEFAULT 1", "UPDATE triples SET seen=1 WHERE seen IS NULL"),
            ("archived INTEGER DEFAULT 0", "UPDATE triples SET archived=0 WHERE archived IS NULL")):
        try:
            conn.execute(f"ALTER TABLE triples ADD COLUMN {coldef}")
            conn.execute(backfill)
        except sqlite3.OperationalError:
            pass  # colonne déjà présente


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

def _upsert(conn, s, r, o):
    """Insertion avec hygiène : re-confirmation (seen+1, désarchive) si le fait existe
    (comparaison PLIÉE accents/casse), résolution de contradiction pour les relations
    fonctionnelles (l'ancien objet est archivé, le récent gagne)."""
    now = time.time()
    # Fait déjà connu (à la casse/aux accents près) → re-confirmation.
    for tid, es, er, eo in conn.execute("SELECT id, s, r, o FROM triples").fetchall():
        if _fold(es) == _fold(s) and _fold(er) == _fold(r) and _fold(eo) == _fold(o):
            conn.execute("UPDATE triples SET seen=COALESCE(seen,1)+1, last_seen=?, archived=0 WHERE id=?",
                         (now, tid))
            return True
    # Contradiction : relation FONCTIONNELLE avec un autre objet → archive l'ancien.
    if _is_functional(r):
        for tid, es, er, eo in conn.execute(
                "SELECT id, s, r, o FROM triples WHERE archived=0").fetchall():
            if _fold(es) == _fold(s) and _fold(er) == _fold(r) and _fold(eo) != _fold(o):
                conn.execute("UPDATE triples SET archived=1, last_seen=? WHERE id=?", (now, tid))
    count = conn.execute("SELECT COUNT(*) FROM triples").fetchone()[0]
    if count >= _MAX:
        # Purge en priorité les archivés les plus vieux, sinon le plus vieux tout court.
        conn.execute("""DELETE FROM triples WHERE id IN (
            SELECT id FROM triples ORDER BY archived DESC, COALESCE(last_seen, 0) ASC LIMIT 1)""")
    conn.execute("INSERT OR IGNORE INTO triples (s, r, o, created_at, last_seen, seen, archived) "
                 "VALUES (?, ?, ?, ?, ?, 1, 0)", (s, r, o, now, now))
    return True


def add_triple(s, r, o):
    s, r, o = _norm(s), _norm(r), _norm(o)
    if not s or not o:
        return False
    with closing(_get_conn()) as conn:
        with conn:
            try:
                return _upsert(conn, s, r, o)
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
                        _upsert(conn, s, r, o)
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
                    "SELECT s, r, o FROM triples WHERE archived=0 AND (s LIKE ? OR o LIKE ?)",
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

def entities():
    """Toutes les entités distinctes (sujets ∪ objets) — pour repérer celles citées dans un texte."""
    with closing(_get_conn()) as conn:
        rows = conn.execute("SELECT s FROM triples WHERE archived=0 "
                            "UNION SELECT o FROM triples WHERE archived=0").fetchall()
    return [r[0] for r in rows]


def relevant_triples(text, limit=12, min_len=3):
    """Triplets dont une entité (sujet ou objet) apparaît dans `text`. Sert à injecter un
    CONTEXTE-GRAPHE pertinent au début d'un run (« ce que je sais déjà »)."""
    t = (text or "").lower()
    if not t:
        return []
    hits = []
    seen_keys = set()
    seen_ent = set()
    for ent in entities():
        el = ent.lower().strip()
        if len(el) < min_len or el in seen_ent:
            continue
        if el in t:
            seen_ent.add(el)
            for tr in neighborhood(ent, depth=1):
                key = (tr["s"], tr["r"], tr["o"])
                if key not in seen_keys:
                    seen_keys.add(key)
                    hits.append(tr)
                    if len(hits) >= limit:
                        return hits
    return hits


def stats():
    with closing(_get_conn()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM triples WHERE archived=0").fetchone()[0]
        archived = conn.execute("SELECT COUNT(*) FROM triples WHERE archived=1").fetchone()[0]
        return {"triples": count, "archived": archived}


# ── Consolidation périodique (job d'hygiène) ───────────────────────────────────
def consolidate(db_file: str = None) -> dict:
    """Passe d'hygiène sur UNE base (celle de l'utilisateur courant par défaut) :
    - archive les faits jamais re-confirmés depuis GRAPH_FACT_TTL_DAYS (décroissance) ;
    - purge définitivement les archivés depuis plus de 2×TTL ;
    - fusionne les doublons à la normalisation près (accents/casse) : le plus confirmé
      absorbe les compteurs des autres.
    Renvoie {"archived": n, "purged": n, "merged": n}."""
    now = time.time()
    ttl = _FACT_TTL_DAYS * 86400
    out = {"archived": 0, "purged": 0, "merged": 0}
    conn = sqlite3.connect(db_file, check_same_thread=False) if db_file else _get_conn()
    with closing(conn):
        if db_file:
            _migrate_columns(conn)  # base d'un autre utilisateur, peut-être pré-migration
        with conn:
            # Fusion des doublons pliés (ex. « Habite à » / « habite a »).
            rows = conn.execute("SELECT id, s, r, o, COALESCE(seen,1), COALESCE(last_seen,0), "
                                "COALESCE(created_at,0), archived FROM triples").fetchall()
            groups = {}
            for row in rows:
                groups.setdefault((_fold(row[1]), _fold(row[2]), _fold(row[3])), []).append(row)
            for _key_f, grp in groups.items():
                if len(grp) < 2:
                    continue
                grp.sort(key=lambda x: (-x[4], -x[5]))  # le plus confirmé/récent absorbe
                keep = grp[0]
                total_seen = sum(g[4] for g in grp)
                last_seen = max(g[5] for g in grp)
                created = min(g[6] for g in grp) or keep[6]
                arch = 0 if any(g[7] == 0 for g in grp) else 1
                conn.execute("UPDATE triples SET seen=?, last_seen=?, created_at=?, archived=? WHERE id=?",
                             (total_seen, last_seen, created, arch, keep[0]))
                ids = [str(g[0]) for g in grp[1:]]
                conn.execute(f"DELETE FROM triples WHERE id IN ({','.join(ids)})")
                out["merged"] += len(ids)
            # Décroissance : jamais re-confirmé (seen ≤ 1) et pas vu depuis TTL → archivé.
            cur = conn.execute(
                "UPDATE triples SET archived=1 WHERE archived=0 AND COALESCE(seen,1) <= 1 "
                "AND COALESCE(last_seen, 0) < ?", (now - ttl,))
            out["archived"] = cur.rowcount
            # Purge : archivé et plus revu depuis 2×TTL → suppression définitive.
            cur = conn.execute(
                "DELETE FROM triples WHERE archived=1 AND COALESCE(last_seen, 0) < ?",
                (now - 2 * ttl,))
            out["purged"] = cur.rowcount
    return out


def consolidate_all() -> dict:
    """Consolide TOUTES les bases utilisateurs (graph_memory_*.db) — pour le job périodique."""
    base = _base_path()
    root, _ = os.path.splitext(base)
    total = {"archived": 0, "purged": 0, "merged": 0, "dbs": 0}
    for db_file in _glob.glob(f"{root}_*.db"):
        try:
            r = consolidate(db_file)
            total["dbs"] += 1
            for k in ("archived", "purged", "merged"):
                total[k] += r[k]
        except Exception as e:
            print(f"[graph_memory] consolidation de {os.path.basename(db_file)} échouée : {e}")
    return total


def start_consolidation_thread():
    """Job périodique d'hygiène (défaut : toutes les 24 h, 1re passe 5 min après le boot).
    GRAPH_CONSOLIDATE_HOURS=0 pour désactiver."""
    hours = float(os.getenv("GRAPH_CONSOLIDATE_HOURS", "24") or 24)
    if hours <= 0:
        return

    def _loop():
        time.sleep(300)  # laisser le serveur démarrer tranquillement
        while True:
            try:
                r = consolidate_all()
                if r["archived"] or r["purged"] or r["merged"]:
                    print(f"[graph_memory] consolidation : {r}")
            except Exception as e:
                print(f"[graph_memory] consolidation échouée : {e}")
            time.sleep(hours * 3600)

    threading.Thread(target=_loop, name="graph-consolidation", daemon=True).start()

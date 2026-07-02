"""Mémoire-graphe (SQLite, par-utilisateur) : triplets, voisinage multi-sauts, isolation."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DB isolée pour le test (évite de polluer le projet).
_TMP = tempfile.mkdtemp(prefix="graphtest-")
os.environ["GRAPH_MEMORY_PATH"] = os.path.join(_TMP, "graph_memory.db")

from core import graph_memory  # noqa: E402
from core.state import _current_username  # noqa: E402


def test_triples_and_neighborhood():
    graph_memory.add_triple("Gaëtan", "a écrit", "Univers Fantasy")
    n = graph_memory.add_triples([
        ("Univers Fantasy", "contient", "Héros Mystérieux"),
        ("Héros Mystérieux", "combat", "Dragon Rouge"),
    ])
    assert n == 2, f"add_triples devait insérer 2, got {n}"
    assert graph_memory.stats()["triples"] == 3

    # Voisinage : profondeur croissante = plus de sauts atteints.
    d1 = graph_memory.neighborhood("Gaëtan", depth=1)
    d2 = graph_memory.neighborhood("Gaëtan", depth=2)
    d3 = graph_memory.neighborhood("Gaëtan", depth=3)
    assert len(d1) == 1 and len(d2) == 2 and len(d3) == 3, (len(d1), len(d2), len(d3))

    # Dédup : ré-insertion ignorée.
    graph_memory.add_triple("Gaëtan", "a écrit", "Univers Fantasy")
    assert graph_memory.stats()["triples"] == 3
    print("OK : triplets + voisinage multi-sauts + dédup")


def test_per_user_isolation():
    t = _current_username.set("alice")
    graph_memory.add_triple("Alice", "possède", "Clé secrète")
    _current_username.reset(t)
    t = _current_username.set("bob")
    bob_sees = graph_memory.neighborhood("Alice", depth=2)
    _current_username.reset(t)
    assert bob_sees == [], "Bob ne doit PAS voir les relations d'Alice"
    print("OK : isolation par-utilisateur")


if __name__ == "__main__":
    test_triples_and_neighborhood()
    test_per_user_isolation()
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    print("\n✅ test_graph_memory OK")


def test_reconfirmation_et_contradiction():
    """Hygiène : ré-apprendre un fait le RE-confirme (seen+1) ; une relation
    FONCTIONNELLE avec un nouvel objet ARCHIVE l'ancien (le récent gagne)."""
    import sqlite3
    graph_memory.add_triple("Gaëtan", "habite à", "Strasbourg")
    graph_memory.add_triple("Gaëtan", "habite à", "Strasbourg")  # re-confirmation
    with sqlite3.connect(graph_memory._db_path()) as c:
        seen = c.execute("SELECT seen FROM triples WHERE o='Strasbourg'").fetchone()[0]
    assert seen == 2, f"re-confirmation attendue, seen={seen}"

    graph_memory.add_triple("Gaëtan", "habite à", "Colmar")  # déménagement
    trs = graph_memory.neighborhood("Gaëtan")
    objs = {t["o"] for t in trs if "habite" in t["r"]}
    assert objs == {"Colmar"}, f"l'ancien domicile doit être archivé : {objs}"
    with sqlite3.connect(graph_memory._db_path()) as c:
        arch = c.execute("SELECT archived FROM triples WHERE o='Strasbourg'").fetchone()[0]
    assert arch == 1, "Strasbourg archivé (pas supprimé)"
    # Relation NON fonctionnelle : pas de contradiction (multi-valuée).
    graph_memory.add_triple("Gaëtan", "aime", "la fantasy")
    graph_memory.add_triple("Gaëtan", "aime", "les échecs")
    objs = {t["o"] for t in graph_memory.neighborhood("Gaëtan") if t["r"] == "aime"}
    assert objs == {"la fantasy", "les échecs"}, objs
    print("OK: re-confirmation + contradiction fonctionnelle (archive, jamais multi-valué)")


def test_consolidation_decroissance_et_fusion():
    """Consolidation : faits jamais re-confirmés > TTL archivés ; doublons pliés
    (accents/casse) fusionnés ; archivés > 2×TTL purgés."""
    import sqlite3
    import time as _t
    ttl = graph_memory._FACT_TTL_DAYS * 86400
    now = _t.time()
    with sqlite3.connect(graph_memory._db_path()) as c:
        graph_memory._migrate_columns(c)
        # Fait périmé (jamais re-confirmé, vu il y a TTL+1j) et fait archivé très vieux.
        c.execute("INSERT INTO triples (s, r, o, created_at, last_seen, seen, archived) "
                  "VALUES ('Vieux','concerne','Fait périmé',?,?,1,0)", (now - ttl - 86400,) * 2)
        c.execute("INSERT INTO triples (s, r, o, created_at, last_seen, seen, archived) "
                  "VALUES ('Ancien','concerne','Fait purgeable',?,?,1,1)", (now - 3 * ttl,) * 2)
        # Doublons à la normalisation près.
        c.execute("INSERT INTO triples (s, r, o, created_at, last_seen, seen, archived) "
                  "VALUES ('Athéna','Utilise','ChromaDB',?,?,2,0)", (now,) * 2)
        c.execute("INSERT INTO triples (s, r, o, created_at, last_seen, seen, archived) "
                  "VALUES ('athena','utilise','chromadb',?,?,1,0)", (now,) * 2)
        c.commit()
    r = graph_memory.consolidate(graph_memory._db_path())
    assert r["archived"] >= 1, r
    assert r["purged"] >= 1, r
    assert r["merged"] >= 1, r
    with sqlite3.connect(graph_memory._db_path()) as c:
        n = c.execute("SELECT COUNT(*), MAX(seen) FROM triples WHERE s LIKE 'ath%'").fetchone()
    assert n[0] == 1 and n[1] == 3, f"fusion : 1 survivant avec seen cumulé, obtenu {n}"
    print("OK: consolidation (décroissance, purge, fusion des doublons pliés)")

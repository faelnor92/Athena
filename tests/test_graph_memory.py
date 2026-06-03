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

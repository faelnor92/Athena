"""Tests : gestionnaire d'objectifs persistants.

Exécution : python3 tests/test_goals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state import _current_username
import core.goals as g


def test_crud_and_isolation():
    _current_username.set("goal-tests-alice")
    g0 = g.create("migrer mail", "Postfix", "high", ["backup", "installer"])
    assert g0["status"] == "active" and g0["priority"] == "high"
    assert len(g.list_goals("active")) >= 1

    assert g.complete_step(g0["id"], "backup")
    done = [s for s in g.get(g0["id"])["steps"] if s["done"]]
    assert len(done) == 1, "une étape doit être cochée"

    assert g.set_status(g0["id"], "done")
    assert all(x["id"] != g0["id"] for x in g.list_goals("active")), "fait → plus actif"
    assert any(x["id"] == g0["id"] for x in g.list_goals("done"))

    # Isolation par utilisateur
    _current_username.set("goal-tests-bob")
    assert all(x["title"] != "migrer mail" for x in g.list_goals("all")), "objectifs cloisonnés par compte"
    print("OK: CRUD + étapes + statut + isolation par compte")


def test_summary_active_only():
    _current_username.set("goal-tests-sum")
    g.create("but A", priority="high")
    gb = g.create("but B")
    g.set_status(gb["id"], "paused")
    s = g.summary()
    assert "but A" in s and "but B" not in s, "le résumé ne montre que les objectifs actifs"
    print("OK: résumé situationnel = actifs seulement")


if __name__ == "__main__":
    test_crud_and_isolation()
    test_summary_active_only()
    print("\n✅ test_goals OK")

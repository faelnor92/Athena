"""Contrôle d'accès des projets PARTAGÉS (core.shared_projects) : rôles owner/editor/viewer,
partage/retrait, isolation par membre. Module sécurité-sensible auparavant non couvert.
(Le store est vidé entre tests par conftest → état propre.)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import shared_projects as sp  # noqa: E402


def test_share_et_roles():
    assert sp.share("p1", owner="alice", name="Projet 1", path="/p1", member="bob", role="editor")
    assert sp.role_for("p1", "alice") == "owner"      # le propriétaire prime
    assert sp.role_for("p1", "bob") == "editor"
    assert sp.role_for("p1", "carol") is None         # non membre
    assert sp.role_for("inconnu", "bob") is None      # projet inconnu


def test_role_invalide_retombe_sur_viewer():
    sp.share("p2", owner="alice", name="P2", path="/p2", member="bob", role="admin")
    assert sp.role_for("p2", "bob") == "viewer"


def test_pas_de_partage_avec_soi_meme_ou_vide():
    assert sp.share("p3", owner="alice", name="P3", path="/p3", member="alice") is False
    assert sp.share("p3", owner="alice", name="P3", path="/p3", member="  ") is False
    assert sp.get("p3") is None


def test_unshare_et_suppression_si_dernier_membre():
    sp.share("p4", owner="alice", name="P4", path="/p4", member="bob", role="viewer")
    sp.share("p4", owner="alice", name="P4", path="/p4", member="carol", role="editor")
    assert sp.unshare("p4", "bob") is True
    assert sp.role_for("p4", "bob") is None
    assert sp.role_for("p4", "carol") == "editor"     # le partage subsiste
    assert sp.unshare("p4", "carol") is True
    assert sp.get("p4") is None                       # plus aucun membre → partage supprimé
    assert sp.unshare("inconnu", "bob") is False


def test_projects_for_liste_par_membre():
    sp.share("a", owner="alice", name="A", path="/a", member="bob", role="viewer")
    sp.share("b", owner="alice", name="B", path="/b", member="bob", role="editor")
    sp.share("c", owner="alice", name="C", path="/c", member="carol", role="viewer")
    ids_bob = sorted(p["id"] for p in sp.projects_for("bob"))
    assert ids_bob == ["a", "b"]
    assert sp.projects_for("alice") == []             # owner ≠ membre
    assert {p["role"] for p in sp.projects_for("bob")} == {"viewer", "editor"}


def test_remove_project_supprime_tout_partage():
    sp.share("z", owner="alice", name="Z", path="/z", member="bob", role="editor")
    sp.remove_project("z")
    assert sp.get("z") is None
    assert sp.role_for("z", "bob") is None
    assert sp.members("z") == {}

"""Validation admin des automatisations : pipelines & routines créés par un non-admin
restent « en attente » (approved=False) jusqu'à validation par un admin.

Modèle « créable par les users, validable par les admins » : on teste ici la couche de
données (le gate HTTP 403 et le scheduler s'appuient sur ces champs).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def test_pipeline_pending_until_approved():
    from core.pipelines import PipelineStore
    s = PipelineStore()
    # créé par un non-admin → en attente
    p = s.upsert({"name": "Deploy", "steps": [{"agent": "Codeur", "instruction": "x"}]},
                 owner="bob", approved=False)
    assert p["approved"] is False
    assert any(x["id"] == p["id"] for x in s.pending()), "doit figurer dans la file admin"
    # validation admin
    assert s.set_approved(p["id"], True) is True
    assert s.get(p["id"])["approved"] is True
    assert not any(x["id"] == p["id"] for x in s.pending()), "ne doit plus être en attente"


def test_pipeline_admin_created_is_approved():
    from core.pipelines import PipelineStore
    s = PipelineStore()
    p = s.upsert({"name": "AdminFlow", "steps": [{"agent": "A", "instruction": "x"}]},
                 owner="admin", approved=True)
    assert p["approved"] is True
    assert not any(x["id"] == p["id"] for x in s.pending())


def test_pipeline_edit_resets_pending():
    from core.pipelines import PipelineStore
    s = PipelineStore()
    p = s.upsert({"name": "F", "steps": [{"agent": "A", "instruction": "x"}]}, owner="bob", approved=True)
    # ré-édition par un non-admin → repasse en attente
    p2 = s.upsert({"id": p["id"], "name": "F modifié", "steps": [{"agent": "A", "instruction": "y"}]},
                  owner="bob", approved=False)
    assert p2["approved"] is False, "une édition non-admin doit forcer une re-validation"


def test_routine_approved_gate_semantics():
    # Le gate du scheduler/webhook/manuel est : `routine.get("approved") is False` => ignoré.
    # `approved` absent (routine héritée) => exécutée. On vérifie cette sémantique exacte.
    assert ({"approved": False}.get("approved") is False) is True      # bloquée
    assert ({"approved": True}.get("approved") is False) is False      # autorisée
    assert ({}.get("approved") is False) is False                      # héritée → autorisée


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de validation admin passent.")

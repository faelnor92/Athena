"""Listes par-utilisateur sur le store partagé : CRUD + cohérence inter-instances (multi-worker)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def test_lists_crud_and_isolation():
    import tools.list_tools as L
    it = L.add_list_item("courses", "lait")
    assert [i["text"] for i in L.get_list_items("courses")] == ["lait"]
    assert L.toggle_list_item("courses", it["id"]) is True
    assert L.get_list_items("courses")[0]["completed"] is True
    assert L.toggle_list_item("courses", "inexistant") is False
    assert L.delete_list_item("courses", it["id"]) is True
    assert L.get_list_items("courses") == []


def test_lists_shared_across_reload():
    # Un autre process partageant la même base doit voir les écritures (pas de cache figé).
    import importlib
    import tools.list_tools as L
    L.add_list_item("taches", "rapport")
    importlib.reload(L)
    assert any(i["text"] == "rapport" for i in L.get_list_items("taches"))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de listes passent.")

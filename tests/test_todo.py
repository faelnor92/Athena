"""Liste de tâches de session (Phase 2) : outil todo_write + persistance + endpoint UI."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import todo_tools  # noqa: E402


def test_todo_write_cree_et_persiste():
    out = todo_tools.todo_write([
        {"content": "Écrire app.py", "status": "in_progress"},
        {"content": "Tester", "status": "pending"},
    ])
    assert "Écrire app.py" in out and "📋" in out
    items = todo_tools.get_todos()
    assert [i["content"] for i in items] == ["Écrire app.py", "Tester"]
    assert items[0]["status"] == "in_progress"


def test_remplace_entierement_la_liste():
    todo_tools.todo_write([{"content": "A"}])
    todo_tools.todo_write([{"content": "B"}, {"content": "C"}])
    assert [i["content"] for i in todo_tools.get_todos()] == ["B", "C"]


def test_normalisation_chaine_et_statut_invalide():
    todo_tools.todo_write(["tâche brute", {"content": "x", "status": "bidon"}])
    items = todo_tools.get_todos()
    assert items[0] == {"content": "tâche brute", "status": "pending"}
    assert items[1]["status"] == "pending"  # statut invalide → pending


def test_items_vides_ignores():
    todo_tools.todo_write([{"content": "  "}, {"status": "pending"}, {"content": "ok"}])
    assert [i["content"] for i in todo_tools.get_todos()] == ["ok"]


def test_avertit_si_plusieurs_in_progress():
    out = todo_tools.todo_write([
        {"content": "a", "status": "in_progress"},
        {"content": "b", "status": "in_progress"},
    ])
    assert "in_progress" in out and "⚠️" in out


def test_endpoint_api_todos():
    import server  # noqa: E402
    from fastapi.testclient import TestClient
    todo_tools.todo_write([{"content": "T1", "status": "completed"}, {"content": "T2"}])
    c = TestClient(server.app)
    r = c.get("/api/todos")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2 and data["completed"] == 1
    assert [i["content"] for i in data["items"]] == ["T1", "T2"]

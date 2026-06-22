"""Blindage : disjoncteur LSP (ne bloque jamais l'édition), bornes todo, taille import-code."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- Disjoncteur LSP -------------------------------------------------------
@pytest.fixture
def _reset_breaker():
    from tools import lsp_client
    lsp_client._lsp_fails = 0
    lsp_client._lsp_disabled_until = 0.0
    yield lsp_client
    lsp_client._lsp_fails = 0
    lsp_client._lsp_disabled_until = 0.0


def test_disjoncteur_lsp_ouvre_apres_echecs_et_retombe_sur_compile(_reset_breaker, monkeypatch, tmp_path):
    lsp = _reset_breaker

    class _FakeSrv:
        def diagnostics(self, *a, **k):
            raise TimeoutError("simulate slow LSP")

    monkeypatch.setattr(lsp, "_langserver_cmd", lambda: ["x"])  # prétend qu'un LSP existe
    monkeypatch.setattr(lsp, "_server_for", lambda p: _FakeSrv())
    monkeypatch.setenv("CODE_LSP_ENABLED", "true")

    p = str(tmp_path / "ok.py")
    # Code SANS erreur → le repli compile renvoie [] ; chaque appel compte un échec LSP.
    for _ in range(lsp._LSP_FAIL_THRESHOLD):
        assert lsp.diagnostics(p, "x = 1\n") == []
    assert lsp._breaker_open(), "le disjoncteur doit s'ouvrir après les échecs"

    # Disjoncteur ouvert → repli direct (toujours fonctionnel : détecte une vraie erreur de syntaxe).
    diags = lsp.diagnostics(p, "def f(:\n pass\n")
    assert any(d["severity"] == "error" for d in diags)


# --- Bornes todo -----------------------------------------------------------
def test_todo_borne_le_nombre_et_la_longueur():
    from tools import todo_tools
    todo_tools.set_todos([{"content": f"t{i}"} for i in range(150)])
    items = todo_tools.get_todos()
    assert len(items) == todo_tools._MAX_ITEMS  # plafonné
    todo_tools.set_todos([{"content": "x" * 5000}])
    assert len(todo_tools.get_todos()[0]["content"]) == todo_tools._MAX_CONTENT


# --- Taille import-code ----------------------------------------------------
def test_import_code_refuse_payload_enorme():
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    pid = c.post("/api/athenadesign/projects/new", json={"name": "H"}).json()["id"]
    r = c.post(f"/api/athenadesign/projects/{pid}/import-code",
               json={"code": "a" * 2_000_001, "type": "html"})
    assert r.status_code == 413

"""Boucle de feedback diagnostics (Phase 1) : les outils d'édition renvoient les erreurs
introduites, et l'onglet Code (/api/workspace/lint) partage le même moteur.

On teste surtout le REPLI déterministe (compile/ast, sans serveur) ; un test dédié couvre
le vrai LSP basedpyright s'il est installé.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import code_edit, lsp_client  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="athena_lsp_")


@pytest.fixture(autouse=True)
def _ws(monkeypatch):
    # Workspace isolé pour les outils d'édition (ACTIVE_WORKSPACE_DIR lu dynamiquement).
    monkeypatch.setenv("ACTIVE_WORKSPACE_DIR", _tmp)


@pytest.fixture
def _no_server(monkeypatch):
    """Force le mode REPLI (pas de serveur LSP) → diagnostics via compile/ruff, déterministe."""
    monkeypatch.setattr(lsp_client, "_langserver_cmd", lambda: None)


def test_repli_detecte_une_erreur_de_syntaxe(_no_server):
    diags = lsp_client.diagnostics(os.path.join(_tmp, "x.py"), "def f(:\n  pass\n")
    assert any(d["severity"] == "error" and "Syntax" in d["message"] for d in diags), diags


def test_repli_fichier_propre_ne_renvoie_rien(_no_server):
    assert lsp_client.diagnostics(os.path.join(_tmp, "ok.py"), "x = 1\n") == []


def test_repli_json_invalide(_no_server):
    diags = lsp_client.diagnostics(os.path.join(_tmp, "d.json"), "{bad}")
    assert diags and diags[0]["severity"] == "error"


def test_format_pour_agent_ignore_le_propre():
    assert lsp_client.format_for_agent("a.py", []) == ""
    bloc = lsp_client.format_for_agent("a.py", [
        {"line": 2, "column": 1, "severity": "error", "message": "boom", "code": "X"}])
    assert "boom" in bloc and "a.py:2:1" in bloc


def test_edit_file_ajoute_les_diagnostics(_no_server):
    """write_file/edit_file renvoient l'erreur introduite, puis plus rien une fois corrigée."""
    out = code_edit.write_file("m.py", "def f(:\n  pass\n")  # syntaxe cassée
    assert "Créé" in out and ("Erreur" in out or "rreur" in out) and ":" in out
    assert "Syntax" in out or "syntax" in out.lower()
    # Réécriture propre → pas de bloc diagnostic.
    out2 = code_edit.write_file("m.py", "def f():\n    return 1\n")
    assert "Créé" in out2 or "Remplacé" in out2
    assert "❌" not in out2


def test_desactivation_par_env(monkeypatch):
    monkeypatch.setenv("CODE_LSP_ENABLED", "false")
    assert lsp_client.diagnostics(os.path.join(_tmp, "x.py"), "def f(:\n pass\n") == []


@pytest.mark.skipif(not lsp_client.has_lsp(), reason="serveur LSP (basedpyright) non installé")
def test_lsp_reel_detecte_variable_non_definie():
    # Racine de projet pour pyright (sinon dossier du fichier) + fichier réel sur disque
    # (comme en usage réel : on écrit AVANT de diagnostiquer).
    open(os.path.join(_tmp, "pyproject.toml"), "w").write("[project]\nname='t'\n")
    upath = os.path.join(_tmp, "u.py")
    src = "def f():\n    return missing_xyz\n"
    open(upath, "w").write(src)
    diags = lsp_client.diagnostics(upath, src, timeout=15)
    assert any("missing_xyz" in d["message"] for d in diags), diags

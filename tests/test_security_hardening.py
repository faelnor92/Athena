"""Régressions de l'audit sécurité : outils sensibles (HITL), parsing XML durci (anti-XXE),
allowlist de colonne SQL (anti-injection)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_outils_sensibles_couvrent_les_actions_a_risque(monkeypatch):
    # On valide le DÉFAUT DU CODE (indépendant d'un éventuel override SENSITIVE_TOOLS dans .env).
    monkeypatch.delenv("SENSITIVE_TOOLS", raising=False)
    from core import approvals
    names = approvals.sensitive_tool_names()
    for t in ("run_tool_script", "self_update", "nextcloud_write_file", "nextcloud_delete_file",
              "execute_bash_command", "run_ssh_command", "write_file", "edit_file", "apply_patch"):
        assert t in names, f"{t} devrait être sensible (HITL) par défaut"


_XXE = (b'<?xml version="1.0"?>'
        b'<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>')


def test_parsing_xml_nextcloud_rejette_xxe():
    from tools import nextcloud_tools
    # Si defusedxml est actif, un DOCTYPE/entité externe doit être REFUSÉ (pas de lecture fichier).
    try:
        import defusedxml  # noqa: F401
    except Exception:
        pytest.skip("defusedxml non installé (repli stdlib)")
    with pytest.raises(Exception):
        nextcloud_tools._xml_fromstring(_XXE)


def test_update_conv_rejette_colonne_non_autorisee():
    from core.state import ConversationManager
    mgr = ConversationManager.__new__(ConversationManager)  # sans I/O
    mgr.client_id = "test"
    with pytest.raises(ValueError):
        mgr._update_conv("c1", "messages_json; DROP TABLE conversations;--", "x")

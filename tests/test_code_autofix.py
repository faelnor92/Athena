"""Code-Test-Fix : détection de la commande de vérification + lecture du verdict."""
import os
import sys
import json
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import code_autofix as ca  # noqa: E402


def test_checks_passed():
    assert ca.checks_passed("✅ PASS — `pytest -q` [hôte]\n...")
    assert not ca.checks_passed("❌ FAIL (code 1) — `pytest -q`\n...")
    assert not ca.checks_passed("")
    print("OK test_checks_passed")


def test_detect_check_command():
    # Projet Node (script test) → npm test
    d = tempfile.mkdtemp(prefix="ca_node_")
    json.dump({"scripts": {"test": "jest"}}, open(os.path.join(d, "package.json"), "w"))
    assert ca.detect_check_command(d) == "npm test --silent"

    # Projet Python (pyproject) → pytest
    d2 = tempfile.mkdtemp(prefix="ca_py_")
    open(os.path.join(d2, "pyproject.toml"), "w").close()
    assert ca.detect_check_command(d2) == "pytest -q"

    # Dossier vide → pas de commande (on ne devine pas)
    d3 = tempfile.mkdtemp(prefix="ca_empty_")
    assert ca.detect_check_command(d3) == ""

    # Override CODER_CHECK_CMD prioritaire
    with mock.patch.dict(os.environ, {"CODER_CHECK_CMD": "make test"}):
        assert ca.detect_check_command(d3) == "make test"
    print("OK test_detect_check_command")


def test_enabled_et_budget():
    with mock.patch.dict(os.environ, {"CODER_AUTOFIX": "false"}):
        assert ca.enabled() is False
    with mock.patch.dict(os.environ, {"CODER_AUTOFIX": "true", "CODER_AUTOFIX_MAX": "3"}):
        assert ca.enabled() is True and ca.max_attempts() == 3
    print("OK test_enabled_et_budget")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nTous les tests code_autofix passent.")

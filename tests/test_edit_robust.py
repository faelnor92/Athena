"""edit_file robuste (style Aider) : exact, repli tolérant aux espaces (réindentation),
erreur utile avec suggestion, ambiguïté."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp(prefix="athena_edit_")

from tools.code_edit import edit_file  # noqa: E402


# ACTIVE_WORKSPACE_DIR est GLOBAL et lu dynamiquement : plusieurs fichiers de test le
# posent au niveau module → « le dernier écrivain gagne » à la collecte. On le réaffirme
# donc PAR TEST pour pointer sur NOTRE dossier temporaire, quel que soit l'ordre.
@pytest.fixture(autouse=True)
def _workspace(monkeypatch):
    monkeypatch.setenv("ACTIVE_WORKSPACE_DIR", _tmp)


def _write(name, content):
    with open(os.path.join(_tmp, name), "w", encoding="utf-8") as f:
        f.write(content)


def _read(name):
    with open(os.path.join(_tmp, name), encoding="utf-8") as f:
        return f.read()


def test_exact_replace():
    _write("a.py", "def f():\n    return 1\n")
    r = edit_file("a.py", "return 1", "return 42")
    assert "Modifié" in r, r
    assert "return 42" in _read("a.py")


def test_flexible_whitespace_reindent():
    # Le fichier indente avec 4 espaces ; l'agent fournit old_string SANS indentation.
    _write("b.py", "class C:\n    def m(self):\n        x = old_value\n        return x\n")
    r = edit_file("b.py", "x = old_value", "x = new_value")
    assert "Modifié" in r, r
    out = _read("b.py")
    assert "x = new_value" in out
    assert "        x = new_value" in out, "la réindentation (8 espaces) doit être préservée :\n" + out


def test_flexible_multiline_block():
    _write("c.js", "function g() {\n    const a = 1;\n    const b = 2;\n}\n")
    # old_string mal indenté (2 espaces au lieu de 4)
    r = edit_file("c.js", "  const a = 1;\n  const b = 2;", "  const a = 10;\n  const b = 20;")
    assert "Modifié" in r, r
    out = _read("c.js")
    assert "    const a = 10;" in out and "    const b = 20;" in out, out


def test_not_found_suggests():
    _write("d.py", "alpha = 1\nbeta = 2\ngamma = 3\n")
    r = edit_file("d.py", "alpga = 1", "alpha = 99")  # typo
    assert "introuvable" in r.lower()
    assert "proche" in r.lower(), "doit suggérer le bloc le plus proche : " + r


def test_ambiguous():
    _write("e.py", "x = 1\nx = 1\n")
    r = edit_file("e.py", "x = 1", "x = 2")
    assert "ambig" in r.lower(), r
    r2 = edit_file("e.py", "x = 1", "x = 2", replace_all=True)
    assert "Modifié" in r2 and _read("e.py").count("x = 2") == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests edit_file robuste passent.")

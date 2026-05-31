"""Tests : sûreté et exécution de l'orchestration par script (run_tool_script).

Exécution : python3 tests/test_tool_script.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.tool_script import validate_tool_script, run_tool_script


def test_validation_rejette_dangers():
    for code in [
        "import os\nresult = 1",
        "while True:\n    pass",
        "result = eval('2')",
        "open('/etc/passwd')",
        "x = ().__class__.__bases__",
        "import subprocess",
    ]:
        ok, _ = validate_tool_script(code)
        assert not ok, f"script dangereux non bloqué : {code!r}"
    print("OK: validation bloque imports système, while, eval, open, dunder")


def test_execution_pure():
    out = run_tool_script("import math\ntotal = 0\nfor i in range(5):\n    total += i\nresult = total + math.floor(1.9)")
    assert "result = 11" in out, out
    print("OK: exécution d'un script de calcul (boucle for + import sûr)")


def test_refus_runtime_et_print():
    assert "refusé" in run_tool_script("import os").lower()
    out = run_tool_script("for i in range(3):\n    print('x', i)")
    assert "x 0" in out and "x 2" in out
    print("OK: refus d'import système + capture de print")


def test_desactivable():
    os.environ["TOOL_SCRIPTS"] = "false"
    assert "désactiv" in run_tool_script("result = 1").lower()
    os.environ["TOOL_SCRIPTS"] = "true"
    print("OK: désactivable via TOOL_SCRIPTS=false")


if __name__ == "__main__":
    test_validation_rejette_dangers()
    test_execution_pure()
    test_refus_runtime_et_print()
    test_desactivable()

"""Garde-fous de sécurité : sandbox d'orchestration (tool_script) + anti-SSRF (net_guard)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tool_script_blocks_escapes():
    from tools.tool_script import validate_tool_script as v
    # Évasions classiques refusées
    assert not v("import os")[0]
    assert not v("eval('1')")[0]
    assert not v("open('/etc/passwd')")[0]
    assert not v("x.__class__")[0]
    assert not v("getattr(x, 'y')")[0]
    assert not v("while True: pass")[0]
    # Évasion via str.format avec dunder dans une chaîne littérale (que l'AST ne « voit » pas)
    assert not v('"{0.__class__.__init__.__globals__}".format(print)')[0], "format-dunder doit être bloqué"
    # Script légitime accepté
    ok, _ = v("result = sum([web_search and 1 or 1 for _ in range(3)])\nprint('ok')")
    assert ok, "un script sûr doit être accepté"
    assert v("total = 0\nfor i in range(10):\n    total += i\nresult = total")[0]


def test_net_guard_blocks_internal():
    from tools.net_guard import is_blocked_url
    # IP littérales (pas de DNS) : interne/métadonnées → bloquées
    assert is_blocked_url("http://127.0.0.1/")           # loopback
    assert is_blocked_url("http://169.254.169.254/latest/meta-data/")  # métadonnées cloud
    assert is_blocked_url("http://10.1.2.3/")            # privé
    assert is_blocked_url("http://192.168.0.5/admin")    # privé
    # IP publique → autorisée
    assert not is_blocked_url("http://8.8.8.8/")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests d'audit sécurité passent.")

"""RBAC par outil : ADMIN_ONLY_TOOLS retire des outils pour les non-admins.

None (mode local/no-auth) ou rôle 'admin' → aucune restriction. Rôle 'user' → les outils
listés dans ADMIN_ONLY_TOOLS disparaissent (du schéma, donc le modèle ne peut pas les appeler).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_caller_is_restricted_by_role():
    from core import approvals
    from core.state import _current_role
    tok = _current_role.set("user")
    try:
        assert approvals.caller_is_restricted() is True
    finally:
        _current_role.reset(tok)
    tok = _current_role.set("admin")
    try:
        assert approvals.caller_is_restricted() is False
    finally:
        _current_role.reset(tok)
    # défaut None (local/no-auth) → non restreint
    assert approvals.caller_is_restricted() is False


def test_admin_only_parsing_and_filter():
    from core import approvals
    from core.state import _current_role
    os.environ["ADMIN_ONLY_TOOLS"] = "execute_bash_command, run_ssh_command"
    assert approvals.admin_only_tool_names() == {"execute_bash_command", "run_ssh_command"}

    def mk(n):
        f = lambda: None
        f.__name__ = n
        return f
    tools = [mk("get_weather"), mk("execute_bash_command"), mk("run_ssh_command"), mk("remember")]

    def filtered():
        if approvals.caller_is_restricted():
            ao = approvals.admin_only_tool_names()
            return [f for f in tools if f.__name__ not in ao]
        return tools

    tok = _current_role.set("user")
    try:
        names = [f.__name__ for f in filtered()]
        assert "execute_bash_command" not in names and "run_ssh_command" not in names
        assert "get_weather" in names and "remember" in names
    finally:
        _current_role.reset(tok)
    # admin → tout reste
    tok = _current_role.set("admin")
    try:
        assert len(filtered()) == 4
    finally:
        _current_role.reset(tok)
    os.environ.pop("ADMIN_ONLY_TOOLS", None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests RBAC par outil passent.")

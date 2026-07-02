"""Allowlist/denylist d'outils par session (core.tool_policy) + application dans le swarm."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core import tool_policy  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.swarm import Swarm  # noqa: E402


def test_no_policy_allows_all():
    assert tool_policy.active() is False
    assert tool_policy.allowed("anything") is True


def test_deny_wins_over_allow():
    tok = tool_policy.set_policy(allow=["a", "b"], deny=["b"])
    try:
        assert tool_policy.active() is True
        assert tool_policy.allowed("a") is True
        assert tool_policy.allowed("b") is False        # deny prioritaire
        assert tool_policy.allowed("c") is False        # hors allowlist
    finally:
        tool_policy.reset_policy(tok)
    assert tool_policy.active() is False                # bien réinitialisé


def test_prefix_patterns():
    tok = tool_policy.set_policy(deny=["transfer_to_*"])
    try:
        assert tool_policy.allowed("transfer_to_Codeur") is False
        assert tool_policy.allowed("delegate_to_Codeur") is True
    finally:
        tool_policy.reset_policy(tok)


def _noop():
    """Outil de test."""
    return "ok"


def test_swarm_filters_denied_tool():
    """Un outil refusé par la politique de session est retiré → traité comme inexistant
    (message « n'existe pas » + liste des outils réellement disponibles)."""
    os.environ["SELF_IMPROVE"] = "false"

    class _F:
        name = "_noop"; arguments = "{}"

    class _TC:
        id = "c1"; function = _F()

    def _msg(content, tcs):
        class _M:
            def __init__(self): self.content = content; self.tool_calls = tcs
            def model_dump(self, exclude_none=True): return {"role": "assistant", "content": content}
        return _M()

    state = {"i": 0}

    def fake(**kw):
        state["i"] += 1
        m = _msg("j'appelle", [_TC()]) if state["i"] == 1 else _msg("fini", None)
        return type("R", (), {"choices": [type("C", (), {"message": m})()],
                              "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()})()

    swarm_mod.completion = fake
    s = Swarm.__new__(Swarm)
    ag = Agent(name="Tester", system_prompt="t", model="gpt-4o")
    ag.tools = [_noop]
    s.agents = {"Tester": ag}

    tok = tool_policy.set_policy(deny=["_noop"])
    try:
        _, _msgs, steps = s.run(ag, [{"role": "user", "content": "go"}], max_turns=4)
    finally:
        tool_policy.reset_policy(tok)
    outs = " ".join(str(st.get("output", "")) for st in steps if st.get("type") == "tool_output")
    # L'outil refusé est retiré des outils effectifs → le moteur répond « n'existe pas »
    # (même chemin qu'un outil inventé) et ne l'exécute jamais.
    assert "n'existe pas" in outs.lower() or "introuvable ou non autoris" in outs.lower(), outs
    assert "ok" not in [str(st.get("output")) for st in steps], "l'outil refusé ne doit pas s'exécuter"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests tool_policy passent.")

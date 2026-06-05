"""Délégation enrichie (façon Hermes) : garde de profondeur, sous-agent isolé (feuille),
résultat structuré (résumé + métriques), sécurité enfant (outils clampés)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.swarm import Swarm  # noqa: E402


def _child_tool():
    """Outil de test du sous-agent."""
    return "fait"


def _two_turn_completion():
    """Fake : tour 1 → appel d'outil ; tour 2 → résumé final."""
    state = {"i": 0}

    class _F:
        name = "_child_tool"; arguments = "{}"

    class _TC:
        id = "c1"; function = _F()

    def _msg(content, tcs):
        class _M:
            def __init__(self): self.content = content; self.tool_calls = tcs
            def model_dump(self, exclude_none=True): return {"role": "assistant", "content": content}
        return _M()

    def fake(**kw):
        state["i"] += 1
        m = _msg("je travaille", [_TC()]) if state["i"] == 1 else _msg("Résumé : tâche faite, fichier a.py créé.", None)
        return type("R", (), {"choices": [type("C", (), {"message": m})()],
                              "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()})()
    return fake


def _swarm_with_child():
    s = Swarm.__new__(Swarm)
    s.orchestrator_name = "Athena"
    child = Agent(name="Worker", system_prompt="spec", model="gpt-4o", description="fait des trucs")
    child.tools = [_child_tool]
    s.agents = {"Athena": Agent(name="Athena", system_prompt="orch", model="gpt-4o"), "Worker": child}
    return s, child


def test_delegate_returns_structured_summary():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _two_turn_completion()
    s, child = _swarm_with_child()
    out = s.create_delegate_function(child)("Crée a.py", context="projet X")
    assert out.startswith("[Sous-agent Worker"), out      # en-tête structuré
    assert "outil(s)" in out                              # métriques
    assert "tâche faite" in out.lower()                   # résumé de l'enfant


def test_delegate_depth_guard():
    os.environ["DELEGATE_MAX_DEPTH"] = "1"
    s, child = _swarm_with_child()
    tok = swarm_mod._delegate_depth.set(1)                # déjà à la profondeur max
    try:
        out = s.create_delegate_function(child)("refais")
    finally:
        swarm_mod._delegate_depth.reset(tok)
    assert "profondeur maximale" in out.lower(), out      # délégation refusée


def test_blocked_tools_list_sane():
    # Les outils dangereux pour un enfant sont bien interdits.
    blk = swarm_mod.DELEGATE_BLOCKED_TOOLS
    assert "delegate_to_*" in blk and "create_agent" in blk and "memorize_fact" in blk


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de délégation passent.")

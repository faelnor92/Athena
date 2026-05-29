"""Tests du gate human-in-the-loop (approbation des outils sensibles)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core import approvals
from core.agent import Agent
from core.swarm import Swarm


def danger(x: str = ""):
    """Outil dangereux de test."""
    return f"BOOM-{x}"


danger._requires_approval = True


def _one_shot_completion(tool_args_json):
    """1er tour : appelle danger(args) ; 2e tour : termine."""
    state = {"i": 0}

    class _F:
        name = "danger"
        arguments = tool_args_json

    class _TC:
        id = "c1"
        function = _F()

    def _msg(content, tool_calls):
        class _M:
            def __init__(self):
                self.content = content
                self.tool_calls = tool_calls
            def model_dump(self, exclude_none=True):
                return {"role": "assistant", "content": content}
        return _M()

    class _U:
        prompt_tokens = 1
        completion_tokens = 1

    def fake(**kwargs):
        state["i"] += 1
        m = _msg(None, [_TC()]) if state["i"] == 1 else _msg("fini", None)
        class _C:
            message = m
        class _R:
            choices = [_C()]
            usage = _U()
        return _R()
    return fake


def _make_swarm():
    s = Swarm.__new__(Swarm)
    agent = Agent(name="T", system_prompt="t", model="gpt-4o")
    agent.tools = [danger]
    s.agents = {"T": agent}
    return s, agent


def test_outil_sensible_bloque_sans_confirmation():
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["AUTO_APPROVE_SENSITIVE"] = "false"
    swarm_mod.completion = _one_shot_completion('{"x":"a"}')
    s, agent = _make_swarm()
    _, messages, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=3)

    assert any(st.get("type") == "approval_required" for st in steps), "pas de demande d'approbation"
    tool_msgs = [m["content"] for m in messages if m.get("role") == "tool"]
    assert not any("BOOM" in c for c in tool_msgs), "l'outil sensible a été exécuté sans accord !"
    print("OK: outil sensible bloqué sans confirmation")


def test_outil_sensible_execute_si_confirme():
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["AUTO_APPROVE_SENSITIVE"] = "false"
    swarm_mod.completion = _one_shot_completion('{"x":"a","user_confirmed":true}')
    s, agent = _make_swarm()
    _, messages, _steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=3)
    tool_msgs = [m["content"] for m in messages if m.get("role") == "tool"]
    assert any("BOOM-a" in c for c in tool_msgs), f"l'outil n'a pas été exécuté: {tool_msgs}"
    print("OK: outil sensible exécuté après user_confirmed=True")


def test_auto_approve_bypass():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _one_shot_completion('{"x":"z"}')
    token = approvals.auto_approve_var.set(True)
    try:
        s, agent = _make_swarm()
        _, messages, _steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=3)
        tool_msgs = [m["content"] for m in messages if m.get("role") == "tool"]
        assert any("BOOM-z" in c for c in tool_msgs), "auto-approve n'a pas exécuté l'outil"
    finally:
        approvals.auto_approve_var.reset(token)
    print("OK: canal auto-approuvé exécute sans confirmation")


if __name__ == "__main__":
    test_outil_sensible_bloque_sans_confirmation()
    test_outil_sensible_execute_si_confirme()
    test_auto_approve_bypass()

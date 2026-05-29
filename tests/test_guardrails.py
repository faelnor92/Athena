"""Tests des garde-fous : coercition d'arguments, budget temps, retries LLM."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm, coerce_arguments


def test_coercition_des_arguments():
    def outil(a: int, b: bool = False, c: float = 0.0, d: str = "", e: list = None):
        """outil de test."""
        return "ok"

    out = coerce_arguments(outil, {"a": "5", "b": "true", "c": "1.5", "d": "x", "e": "[1,2]"})
    assert out == {"a": 5, "b": True, "c": 1.5, "d": "x", "e": [1, 2]}, out
    # valeurs non convertibles : laissées telles quelles (pas d'exception)
    out2 = coerce_arguments(outil, {"a": "pas_un_int"})
    assert out2 == {"a": "pas_un_int"}
    print("OK: coercition des arguments selon le schéma")


def _looping_completion():
    class _F:
        name = "slow"
        arguments = "{}"

    class _TC:
        id = "c1"
        function = _F()

    class _M:
        content = "encore"
        tool_calls = [_TC()]
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "encore"}

    class _U:
        prompt_tokens = 10
        completion_tokens = 10

    def fake(**kwargs):
        class _C:
            message = _M()
        class _R:
            choices = [_C()]
            usage = _U()
        return _R()
    return fake


def test_budget_temps_arrete_le_run():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _looping_completion()

    def slow():
        """dort."""
        time.sleep(0.2)
        return "lent"

    s = Swarm.__new__(Swarm)
    agent = Agent(name="T", system_prompt="t", model="gpt-4o")
    agent.tools = [slow]
    s.agents = {"T": agent}

    _, _msgs, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=100, max_seconds=0.1)
    assert any("Budget temps atteint" in str(st.get("content", "")) for st in steps), "pas d'arrêt budget temps"
    print("OK: le budget temps arrête le run")


def test_budget_tokens_arrete_le_run():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _looping_completion()  # 20 tokens/tour

    def noop():
        """rien."""
        return "x"

    s = Swarm.__new__(Swarm)
    agent = Agent(name="T", system_prompt="t", model="gpt-4o")
    agent.tools = [noop]
    s.agents = {"T": agent}

    _, _msgs, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=100, max_tokens=50)
    assert any("Budget tokens atteint" in str(st.get("content", "")) for st in steps), "pas d'arrêt budget tokens"
    print("OK: le budget tokens arrête le run")


def test_retry_llm():
    os.environ["LLM_MAX_RETRIES"] = "2"
    calls = {"n": 0}

    class _M:
        content = "fini"
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "fini"}

    class _U:
        prompt_tokens = 1
        completion_tokens = 1

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("erreur transitoire simulée")
        class _C:
            message = _M()
        class _R:
            choices = [_C()]
            usage = _U()
        return _R()

    swarm_mod.completion = flaky
    s = Swarm.__new__(Swarm)
    resp = s._complete("gpt-4o", [{"role": "user", "content": "x"}])
    assert calls["n"] == 2, f"attendu 2 appels (1 échec + 1 succès), obtenu {calls['n']}"
    assert resp.choices[0].message.content == "fini"
    print("OK: retry LLM après échec transitoire")


if __name__ == "__main__":
    test_coercition_des_arguments()
    test_budget_temps_arrete_le_run()
    test_budget_tokens_arrete_le_run()
    test_retry_llm()

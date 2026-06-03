"""Tests du harnais d'éval et du rejeu de runs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm


def _fixed_completion(text):
    class _M:
        content = text
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": text}

    class _U:
        prompt_tokens = 1
        completion_tokens = 1

    def fake(**kwargs):
        class _C:
            message = _M()
        class _R:
            choices = [_C()]
            usage = _U()
        return _R()
    return fake


def _make_swarm():
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Athena", system_prompt="t", model="gpt-4o")
    agent.tools = []
    s.agents = {"Athena": agent}
    return s


def test_run_eval_contains():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _fixed_completion("Bonjour à toi, comment puis-je aider ?")
    from core.eval import run_eval
    s = _make_swarm()
    report = run_eval(s, [
        {"name": "salutation", "message": "salut", "expect_contains": "bonjour"},
        {"name": "agent final", "message": "salut", "expect_agent": "Athena"},
        {"name": "doit échouer", "message": "salut", "expect_contains": "au revoir"},
    ])
    assert report["total"] == 3 and report["passed"] == 2 and report["failed"] == 1, report
    print("OK: run_eval évalue correctement les assertions")


def test_replay_run():
    os.environ["SELF_IMPROVE"] = "false"
    from core.tracing import run_store
    from core.eval import replay_run

    rid = run_store.new_run_id()
    run_store.save(run_id=rid, agent="Athena", status="success",
                   user_message="quelle heure est-il ?", final_response="ancienne réponse")

    swarm_mod.completion = _fixed_completion("nouvelle réponse rejouée")
    s = _make_swarm()
    res = replay_run(s, rid, persist=False)
    assert res["replay_of"] == rid, res
    assert "rejouée" in res["new_response"], res
    assert res["original_response"] == "ancienne réponse", res
    print("OK: replay_run rejoue le message et compare")


if __name__ == "__main__":
    test_run_eval_contains()
    test_replay_run()

"""Reprise des runs swarm interrompus par un redémarrage : checkpoint par tour dans le
shared_store, listing des runs interrompus, resume_run() qui repart de l'historique."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm
from core import run_context, shared_store


def _final_completion():
    """Réponse SANS tool_call → le run se termine au premier tour."""
    class _Msg:
        content = "réponse finale"
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "réponse finale"}

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    def _fake(**kwargs):
        return _Resp()
    return _fake


def _mk_swarm():
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="test", model="gpt-4o")
    agent.tools = []
    s.agents = {"Tester": agent}
    return s, agent


def test_checkpoint_efface_en_fin_de_run():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _final_completion()
    s, agent = _mk_swarm()
    rid = "run-ckpt-test-1"
    token = run_context.current_run_id.set(rid)
    try:
        s.run(agent, [{"role": "user", "content": "salut"}], max_turns=3)
    finally:
        run_context.current_run_id.reset(token)
    assert shared_store.get("swarm_runs", rid) is None, \
        "le checkpoint doit être effacé quand le run se termine normalement"
    print("OK: checkpoint effacé en fin de run")


def test_resume_run_repart_du_checkpoint():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _final_completion()
    s, agent = _mk_swarm()
    rid = "run-ckpt-test-2"
    # Simule un run interrompu : checkpoint présent (comme après un kill au tour 2).
    shared_store.set("swarm_runs", rid, {
        "agent": "Tester", "turn": 2, "updated": __import__("time").time(),
        "messages": [{"role": "user", "content": "génère le livre audio"},
                     {"role": "assistant", "content": "chapitre 1 fait"}]})
    listed = s.list_interrupted_runs()
    assert any(r["run_id"] == rid for r in listed), listed
    got = [r for r in listed if r["run_id"] == rid][0]
    assert got["agent"] == "Tester" and got["turn"] == 2
    assert "livre audio" in got["last_user"]

    res = s.resume_run(rid, max_turns=3)
    assert res is not None
    _agent, messages, _steps = res
    # L'historique du checkpoint a été conservé et le run a continué jusqu'à la réponse.
    assert messages[0]["content"] == "génère le livre audio"
    assert messages[-1]["role"] == "assistant" and messages[-1]["content"] == "réponse finale"
    assert shared_store.get("swarm_runs", rid) is None, "repris et terminé → checkpoint effacé"
    print("OK: resume_run repart du checkpoint et nettoie derrière lui")


def test_resume_run_sans_checkpoint():
    s, _ = _mk_swarm()
    assert s.resume_run("run-inexistant") is None
    print("OK: resume_run sans checkpoint → None")


if __name__ == "__main__":
    test_checkpoint_efface_en_fin_de_run()
    test_resume_run_repart_du_checkpoint()
    test_resume_run_sans_checkpoint()
    print("\nTous les tests de reprise de run passent.")

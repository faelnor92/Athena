"""Steering : injecter une consigne dans un run EN COURS pour le réorienter (sans relancer)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.swarm import Swarm  # noqa: E402
from core.run_context import registry, current_run_id  # noqa: E402


def test_registry_steer_queue():
    registry.start("r1")
    assert registry.steer("r1", "va à gauche") is True
    assert registry.steer("r1", "  ") is False           # message vide ignoré
    assert registry.pop_steers("r1") == ["va à gauche"]
    assert registry.pop_steers("r1") == []               # vidé après lecture
    registry.finish("r1")
    assert registry.steer("r1", "trop tard") is False     # run terminé → refusé


def _noop():
    """Outil de test."""
    return "ok"


def _two_turn():
    state = {"i": 0}

    class _F:
        name = "_noop"; arguments = "{}"

    class _TC:
        id = "c1"; function = _F()

    def _msg(c, tcs):
        class _M:
            def __init__(self): self.content = c; self.tool_calls = tcs
            def model_dump(self, exclude_none=True): return {"role": "assistant", "content": c}
        return _M()

    def fake(**kw):
        state["i"] += 1
        m = _msg("je bosse", [_TC()]) if state["i"] == 1 else _msg("ok fini", None)
        return type("R", (), {"choices": [type("C", (), {"message": m})()],
                              "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()})()
    return fake


def test_swarm_injects_steering_message():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _two_turn()
    s = Swarm.__new__(Swarm)
    ag = Agent(name="Tester", system_prompt="t", model="gpt-4o")
    ag.tools = [_noop]
    s.agents = {"Tester": ag}

    rid = "rs1"
    registry.start(rid)
    tok = current_run_id.set(rid)
    registry.steer(rid, "réoriente vers la tâche B")     # steering AVANT le 1er tour
    try:
        _, msgs, steps = s.run(ag, [{"role": "user", "content": "go"}], max_turns=4)
    finally:
        current_run_id.reset(tok)
        registry.finish(rid)

    assert any(st.get("type") == "steer" for st in steps), "pas de step 'steer'"
    assert any("réoriente vers la tâche B" in str(m.get("content", "")) for m in msgs), \
        "la consigne de steering n'a pas été injectée dans la conversation"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de steering passent.")

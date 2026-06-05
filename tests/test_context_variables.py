"""État partagé du run (context_variables, façon openai/swarm) :
- masqué du schéma exposé au modèle,
- injecté dans l'outil qui le déclare (lecture/écriture directe),
- mis à jour quand un outil renvoie Result(context_variables=…),
- l'appelant relit l'état final via le dict qu'il a fourni."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core.agent import Agent, Result  # noqa: E402
from core.swarm import Swarm, function_to_schema  # noqa: E402


def set_state(note: str = "", context_variables=None):
    """Range une note dans l'état partagé.
    note: la note à mémoriser."""
    if context_variables is not None:
        context_variables["live_write"] = "direct"   # écriture directe dans le dict injecté
    return Result(value="rangé", context_variables={"via_result": note or "x"})


def test_schema_hides_context_variables():
    sch = function_to_schema(set_state)
    props = sch["function"]["parameters"]["properties"]
    assert "context_variables" not in props
    assert "note" in props  # les autres paramètres restent exposés


def _drive_one_tool_call():
    """Fake completion : 1) appelle set_state(note='hello'), 2) termine."""
    state = {"i": 0}

    class _ToolFunc:
        name = "set_state"
        arguments = '{"note": "hello"}'

    class _ToolCall:
        id = "c1"
        function = _ToolFunc()

    def _msg(content, tool_calls):
        class _M:
            def __init__(self):
                self.content = content
                self.tool_calls = tool_calls
            def model_dump(self, exclude_none=True):
                return {"role": "assistant", "content": content}
        return _M()

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1

    def fake(**kwargs):
        state["i"] += 1
        m = _msg("j'utilise un outil", [_ToolCall()]) if state["i"] == 1 else _msg("fini", None)

        class _Choice:
            message = m

        class _Resp:
            choices = [_Choice()]
            usage = _Usage()
        return _Resp()

    return fake


def test_context_variables_injected_and_updated():
    os.environ["SELF_IMPROVE"] = "false"
    swarm_mod.completion = _drive_one_tool_call()

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="test", model="gpt-4o")
    agent.tools = [set_state]
    s.agents = {"Tester": agent}

    cv = {"projet": "demo"}
    s.run(agent, [{"role": "user", "content": "range hello"}], max_turns=4, context_variables=cv)

    # L'outil a pu ÉCRIRE directement dans le dict injecté…
    assert cv.get("live_write") == "direct", cv
    # …et la valeur du Result a été fusionnée dans l'état du run.
    assert cv.get("via_result") == "hello", cv
    # L'état initial fourni par l'appelant est préservé.
    assert cv.get("projet") == "demo", cv


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests context_variables passent.")

"""Tests des garde-fous qualité : validation JSON-schema + cache d'outils."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm, validate_args_schema


def test_validation_schema_args():
    def outil(a=None):
        """outil mcp."""
        return "ok"
    outil._mcp_schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}

    assert validate_args_schema(outil, {"a": 5}) is None, "args valides rejetés"
    err = validate_args_schema(outil, {"b": 1})
    assert err and "invalides" in err.lower(), f"args invalides non détectés: {err}"
    print("OK: validation JSON-schema des arguments")


def test_cache_outils():
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["TOOL_CACHE_TTL"] = "300"
    os.environ["CACHEABLE_TOOLS"] = "web_search"
    swarm_mod._TOOL_CACHE.clear()

    calls = {"n": 0}

    def web_search(query: str = ""):
        """recherche web (factice)."""
        calls["n"] += 1
        return f"résultats pour {query}"

    state = {"i": 0}

    class _F:
        name = "web_search"
        arguments = '{"query":"openai"}'

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
        # Deux tours appellent web_search avec les MÊMES args, puis on termine.
        m = _msg(None, [_TC()]) if state["i"] <= 2 else _msg("fini", None)

        class _C:
            message = m

        class _R:
            choices = [_C()]
            usage = _U()
        return _R()

    swarm_mod.completion = fake
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="t", model="gpt-4o")
    agent.tools = [web_search]
    s.agents = {"Tester": agent}

    s.run(agent, [{"role": "user", "content": "go"}], max_turns=5)
    assert calls["n"] == 1, f"l'outil a été appelé {calls['n']} fois (cache inactif)"
    print("OK: cache d'outils — 2 appels identiques => 1 exécution réelle")


def test_auto_continuation():
    os.environ["LLM_MAX_CONTINUATIONS"] = "3"
    state = {"i": 0}

    def fake(**kwargs):
        state["i"] += 1
        content, fr = ("Début de la réponse", "length") if state["i"] == 1 else (" — et la suite.", "stop")

        class _M:
            def __init__(self):
                self.content = content
                self.tool_calls = None

        class _Choice:
            def __init__(self):
                self.message = _M()
                self.finish_reason = fr

        class _R:
            def __init__(self):
                self.choices = [_Choice()]
        return _R()

    swarm_mod.completion = fake
    s = Swarm.__new__(Swarm)
    resp = s._complete("gpt-4o", [{"role": "user", "content": "écris long"}])
    assert resp.choices[0].message.content == "Début de la réponse — et la suite.", resp.choices[0].message.content
    assert resp.choices[0].finish_reason == "stop"
    print("OK: auto-continuation recolle une réponse tronquée (finish_reason=length)")


def test_streaming_tokens():
    os.environ["STREAM_TOKENS"] = "true"

    def fake(**kwargs):
        assert kwargs.get("stream") is True, "streaming non activé"
        def gen():
            for piece, fr in [("Bonjour", None), (" le", None), (" monde.", "stop")]:
                class _D:
                    content = piece
                    tool_calls = None
                class _C:
                    delta = _D()
                    finish_reason = fr
                class _K:
                    choices = [_C()]
                yield _K()
        return gen()

    swarm_mod.completion = fake
    s = Swarm.__new__(Swarm)
    deltas = []
    resp = s._complete("gpt-4o", [{"role": "user", "content": "x"}], on_delta=lambda c: deltas.append(c))
    assert "".join(deltas) == "Bonjour le monde.", deltas
    assert resp.choices[0].message.content == "Bonjour le monde."
    assert resp.choices[0].message.model_dump()["content"] == "Bonjour le monde."
    print("OK: streaming token-par-token (deltas + message reconstruit)")


if __name__ == "__main__":
    test_validation_schema_args()
    test_cache_outils()
    test_auto_continuation()
    test_streaming_tokens()

"""Tests unitaires minimaux pour l'orchestrateur Swarm.

Exécution : python3 -m pytest tests/ (ou python3 tests/test_swarm.py)
Nécessite les dépendances du projet (litellm, chromadb, ...).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm


def _fake_completion_factory(calls):
    """Renvoie une fonction completion factice qui demande TOUJOURS un tool_call,
    ce qui ferait boucler l'orchestrateur à l'infini sans garde-fou max_turns."""
    class _Func:
        name = "noop_tool"
        arguments = "{}"

    class _ToolCall:
        id = "call_1"
        function = _Func()

    class _Msg:
        content = "je réfléchis"
        tool_calls = [_ToolCall()]
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "je réfléchis"}

    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    def _fake(**kwargs):
        calls["n"] += 1
        return _Resp()

    return _fake


def noop_tool():
    """Outil de test qui ne fait rien."""
    return "ok"


def test_max_turns_borne_la_boucle(monkeypatch=None):
    # Isole le test de la boucle du hook d'auto-amélioration (qui ferait +1 appel).
    os.environ["SELF_IMPROVE"] = "false"
    calls = {"n": 0}
    fake = _fake_completion_factory(calls)
    # Patch du symbole completion utilisé dans core.swarm
    swarm_mod.completion = fake

    # Swarm minimal sans agents.yaml
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="test", model="gpt-4o")
    agent.tools = [noop_tool]
    s.agents = {"Tester": agent}

    _, messages, steps = s.run(agent, [{"role": "user", "content": "salut"}], max_turns=3)

    # La completion ne doit avoir été appelée que max_turns fois
    assert calls["n"] == 3, f"attendu 3 appels, obtenu {calls['n']}"
    # Un message de limite doit avoir été produit
    assert any("Limite d'orchestration" in str(s_.get("content", "")) for s_ in steps), \
        "le message de limite d'orchestration est absent des steps"
    print("OK: max_turns borne bien la boucle d'orchestration")


def test_hook_auto_amelioration_archive_un_retour():
    """Après une tâche avec outil, un retour d'expérience doit être archivé."""
    os.environ["SELF_IMPROVE"] = "true"

    # Séquence de réponses : 1) tool_call, 2) fin (sans tool), 3) compte-rendu.
    state = {"i": 0}

    class _ToolFunc:
        name = "noop_tool"
        arguments = "{}"

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
        if state["i"] == 1:
            m = _msg("j'utilise un outil", [_ToolCall()])
        elif state["i"] == 2:
            m = _msg("voici le résultat final", None)
        else:
            m = _msg("- Tâche: test\n- A marché: l'outil\n- À retenir: rien", None)

        class _Choice:
            message = m

        class _Resp:
            choices = [_Choice()]
            usage = _Usage()

        return _Resp()

    swarm_mod.completion = fake

    # Capture des archivages mémoire sans toucher ChromaDB.
    import tools.memory_tools as mt
    stored = []
    mt.store_document = lambda content, source="general": stored.append((source, content)) or "ok"

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="test", model="gpt-4o")
    agent.tools = [noop_tool]
    s.agents = {"Tester": agent}

    _, _messages, steps = s.run(agent, [{"role": "user", "content": "fais un truc"}], max_turns=5)

    assert any(st.get("type") == "self_improve" for st in steps), "pas de step self_improve"
    assert stored and stored[0][0] == "retour_experience", f"archivage incorrect: {stored}"
    print("OK: le hook d'auto-amélioration archive un retour d'expérience")


if __name__ == "__main__":
    test_max_turns_borne_la_boucle()
    test_hook_auto_amelioration_archive_un_retour()

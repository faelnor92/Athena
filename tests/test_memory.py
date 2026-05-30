"""Test de la compaction mémoire (résumé de l'historique long)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm


def _resp(text, tool_calls=None):
    class _M:
        def __init__(self):
            self.content = text
            self.tool_calls = tool_calls
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": text}

    class _U:
        prompt_tokens = 1
        completion_tokens = 1

    class _C:
        message = _M()

    class _R:
        choices = [_C()]
        usage = _U()

    return _R()


def test_compaction_historique_long():
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["MEMORY_MAX_MESSAGES"] = "40"
    os.environ["MEMORY_KEEP_RECENT"] = "12"

    captured = {"main_len": None}

    def fake_complete(self, model, messages, tools_schema=None):
        sys0 = messages[0]["content"] if messages else ""
        if "Résume la conversation" in sys0:
            return _resp("RÉSUMÉ CONDENSÉ DES ÉCHANGES")
        captured["main_len"] = len(messages)  # system + historique compacté
        return _resp("réponse finale", tool_calls=None)

    swarm_mod.Swarm._complete = fake_complete

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Jarvis", system_prompt="t", model="gpt-4o")
    agent.tools = []
    s.agents = {"Jarvis": agent}

    # 50 messages d'historique (alternance user/assistant, tous avec contenu).
    history = []
    for i in range(50):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"message numéro {i}"})

    _, _msgs, steps = s.run(agent, history, max_turns=1)

    assert any(st.get("type") == "memory_compaction" for st in steps), "pas d'étape de compaction"
    # system(1) + résumé(1) + 12 récents = 14 (au lieu de 1 + 50 = 51)
    assert captured["main_len"] == 14, f"vue LLM non compactée: {captured['main_len']}"
    print(f"OK: historique long compacté (vue LLM = {captured['main_len']} msgs au lieu de 51)")


if __name__ == "__main__":
    test_compaction_historique_long()

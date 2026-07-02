"""Test de la compaction mémoire (résumé ROULANT INCRÉMENTAL de l'historique long)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod
from core.agent import Agent
from core.swarm import Swarm

# Marqueur présent dans le system prompt du résumeur (voir core/swarm/context.py:_fold).
_SUMMARIZER_MARKER = "RÉSUMÉ ÉVOLUTIF"


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
    """Bout-en-bout via Swarm.run : un historique long est bien compacté dans la vue LLM,
    le DERNIER message reste verbatim (pas de perte de la queue), et une étape de
    compaction est émise."""
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["MEMORY_MAX_MESSAGES"] = "40"
    os.environ["MEMORY_KEEP_RECENT"] = "12"
    os.environ["MEMORY_FOLD_BATCH"] = "12"

    captured = {"main_msgs": None}

    def fake_complete(self, model, messages, tools_schema=None, allow_continuation=True,
                      on_delta=None, allow_fallback=True, max_tokens=None):
        sys0 = messages[0]["content"] if messages else ""
        if _SUMMARIZER_MARKER in sys0:
            return _resp("RÉSUMÉ CONDENSÉ DES ÉCHANGES")
        captured["main_msgs"] = messages  # system + vue compactée + volatile
        return _resp("réponse finale", tool_calls=None)

    swarm_mod.Swarm._complete = fake_complete

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Athena", system_prompt="t", model="gpt-4o")
    agent.tools = []
    s.agents = {"Athena": agent}

    history = []
    for i in range(50):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"message numéro {i}"})

    _, _msgs, steps = s.run(agent, history, max_turns=1)

    assert any(st.get("type") == "memory_compaction" for st in steps), "pas d'étape de compaction"
    msgs = captured["main_msgs"]
    assert msgs is not None, "l'appel principal n'a pas eu lieu"
    # Vue COMPACTÉE, nettement plus courte que 1 + 50.
    assert len(msgs) < 1 + 50, f"vue LLM non compactée: {len(msgs)}"
    # Exactement un message de résumé roulant.
    summaries = [m for m in msgs if isinstance(m.get("content"), str)
                 and m["content"].startswith("[RÉSUMÉ DE LA CONVERSATION")]
    assert len(summaries) == 1, f"attendu 1 résumé, trouvé {len(summaries)}"
    # La QUEUE est préservée verbatim (le dernier message doit être intact).
    contents = [m.get("content") for m in msgs]
    assert "message numéro 49" in contents, "le dernier message n'est plus verbatim"
    print(f"OK: historique long compacté (vue LLM = {len(msgs)} msgs au lieu de 51)")


def test_resume_roulant_incremental():
    """Le résumé roulant NE re-résume PAS tout à chaque tour : entre deux tours qui
    n'ajoutent que quelques messages, le checkpoint précédent est réutilisé (0 ou 1
    nouveau pli), et le milieu de la conversation n'est jamais perdu."""
    os.environ["MEMORY_MAX_MESSAGES"] = "10"
    os.environ["MEMORY_KEEP_RECENT"] = "4"
    os.environ["MEMORY_FOLD_BATCH"] = "4"
    os.environ["MEMORY_MAX_FOLDS_PER_TURN"] = "10"

    calls = {"n": 0, "last_user": None}

    def fake_complete(self, model, messages, tools_schema=None, allow_continuation=True,
                      on_delta=None, allow_fallback=True, max_tokens=None):
        calls["n"] += 1
        calls["last_user"] = messages[-1]["content"]
        return _resp(f"SUMMARY#{calls['n']}")

    Swarm._complete = fake_complete
    Swarm._utility_model = lambda self, model: model

    s = Swarm.__new__(Swarm)

    def hist(n):
        return [{"role": "user" if i % 2 == 0 else "assistant",
                 "content": f"m{i}"} for i in range(n)]

    # Tour 1 : reconstruction à froid de 20 messages (cutoff=16, batch=4 → 4 plis).
    view1 = s._maybe_compact("gpt-4o", hist(20), [])
    cold = calls["n"]
    assert cold == 4, f"plis à froid attendus=4, obtenus={cold}"
    assert view1[0]["content"].startswith("[RÉSUMÉ")

    # Tour 2 : +2 messages (22). Le checkpoint à m=16 reste valide → AUCUN nouveau pli.
    calls["n"] = 0
    s._maybe_compact("gpt-4o", hist(22), [])
    assert calls["n"] == 0, f"attendu 0 nouveau pli (réutilisation), obtenu {calls['n']}"

    # Tour 3 : +2 encore (24 → cutoff=20). On franchit un batch → exactement 1 pli.
    calls["n"] = 0
    view3 = s._maybe_compact("gpt-4o", hist(24), [])
    assert calls["n"] == 1, f"attendu 1 pli incrémental, obtenu {calls['n']}"
    # Le pli incrémental part bien du résumé PRÉCÉDENT (pas d'un re-résumé complet)
    # et ne contient que les NOUVEAUX messages bruts (m16..m19).
    assert "m16" in calls["last_user"] and "m19" in calls["last_user"]
    assert "m0" not in calls["last_user"], "le pli incrémental re-résume tout (fuite du début)"
    # La queue verbatim couvre les derniers messages (m20..m23 présents).
    tail = [m.get("content") for m in view3]
    assert "m23" in tail and "m20" in tail
    print("OK: résumé roulant incrémental (réutilisation des checkpoints, pas de re-résumé global)")


if __name__ == "__main__":
    test_compaction_historique_long()
    test_resume_roulant_incremental()

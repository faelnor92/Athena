"""Tests unitaires minimaux pour l'orchestrateur Swarm.

Exécution : python3 -m pytest tests/ (ou python3 tests/test_swarm.py)
Nécessite les dépendances du projet (litellm, chromadb, ...).
"""
import os
import sys
import json

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

    # Désactive le disjoncteur de répétition pour isoler le test du budget de tours.
    os.environ["SWARM_REPEAT_LIMIT"] = "0"
    _, messages, steps = s.run(agent, [{"role": "user", "content": "salut"}], max_turns=3)
    os.environ.pop("SWARM_REPEAT_LIMIT", None)

    # La boucle est bornée : max_turns appels DANS la boucle + 1 appel de SYNTHÈSE finale
    # (rattrapage sans outils → l'utilisateur obtient une réponse, pas une erreur de limite).
    assert calls["n"] == 4, f"attendu 4 appels (3 boucle + 1 synthèse), obtenu {calls['n']}"
    # Le rattrapage a produit une réponse finale d'assistant (synthèse réussie ici).
    assert messages[-1].get("role") == "assistant" and (messages[-1].get("content") or "").strip(), \
        "la synthèse finale (réponse d'assistant) est absente"
    print("OK: max_turns borne la boucle + synthèse finale de rattrapage")


def test_parse_text_tool_calls(monkeypatch=None):
    """Le parseur récupère un tool-call écrit en TEXTE (bloc ```json, balise <tool_call>)
    et ignore le JSON dont le nom n'est pas un outil disponible (anti faux-positif)."""
    from core.swarm import parse_text_tool_calls
    valid = {"web_search", "get_time"}

    # 1) Bloc ```json avec clé "tool" + "tool_input" (format observé chez qwen3).
    txt = 'Voici :\n```json\n[{"tool": "web_search", "tool_input": {"query": "IA 2026"}}]\n```'
    tcs = parse_text_tool_calls(txt, valid)
    assert len(tcs) == 1 and tcs[0].function.name == "web_search", "bloc json non récupéré"
    assert json.loads(tcs[0].function.arguments) == {"query": "IA 2026"}, "args non préservés"

    # 2) Balise <tool_call> style Hermes/Qwen.
    txt2 = '<tool_call>{"name": "get_time", "arguments": {}}</tool_call>'
    tcs2 = parse_text_tool_calls(txt2, valid)
    assert len(tcs2) == 1 and tcs2[0].function.name == "get_time", "balise tool_call non récupérée"

    # 3) Anti faux-positif : nom inconnu → ignoré (le modèle montre juste du JSON).
    txt3 = '```json\n{"tool": "rm_rf", "args": {}}\n```'
    assert parse_text_tool_calls(txt3, valid) == [], "un nom d'outil inconnu ne doit PAS être exécuté"

    # 4) Texte normal sans appel → rien.
    assert parse_text_tool_calls("Bonjour, comment vas-tu ?", valid) == [], "faux positif sur du texte"

    print("OK: parse_text_tool_calls récupère les appels texte et évite les faux positifs")


def test_disjoncteur_repetition_coupe_les_appels_identiques(monkeypatch=None):
    """Le même outil rappelé avec les mêmes arguments ne doit être EXÉCUTÉ qu'un nombre
    borné de fois (SWARM_REPEAT_LIMIT) ; au-delà, on renvoie un rappel sans ré-exécuter."""
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["SWARM_REPEAT_LIMIT"] = "2"
    calls = {"n": 0}
    swarm_mod.completion = _fake_completion_factory(calls)

    runs = {"n": 0}
    def counting_tool():
        """Outil de test qui compte ses exécutions réelles."""
        runs["n"] += 1
        return "ok"

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="test", model="gpt-4o")
    agent.tools = [counting_tool]
    s.agents = {"Tester": agent}
    # Le fake appelle TOUJOURS "noop_tool" ; on aligne l'outil compté sur ce nom.
    counting_tool.__name__ = "noop_tool"

    _, messages, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=6)
    os.environ.pop("SWARM_REPEAT_LIMIT", None)

    # L'outil n'a été RÉELLEMENT exécuté que SWARM_REPEAT_LIMIT fois, malgré 6 tours.
    assert runs["n"] == 2, f"attendu 2 exécutions réelles, obtenu {runs['n']}"
    # Et un rappel anti-répétition a été émis.
    assert any("DÉJÀ appelé" in str(s_.get("output", "")) for s_ in steps), \
        "le rappel anti-répétition est absent des steps"
    print("OK: le disjoncteur borne les appels d'outil identiques")


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


def test_outils_multiples_executes_en_parallele():
    """Plusieurs tool_calls dans un même tour doivent s'exécuter concurremment,
    en préservant l'ordre des résultats."""
    import time
    os.environ["SELF_IMPROVE"] = "false"

    def slow_tool(x: str = ""):
        """Outil lent de test."""
        time.sleep(0.5)
        return f"done-{x}"

    class _F:
        def __init__(self, name, args):
            self.name = name
            self.arguments = args

    class _TC:
        def __init__(self, cid, name, args):
            self.id = cid
            self.function = _F(name, args)

    state = {"i": 0}

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
            m = _msg(None, [
                _TC("c1", "slow_tool", '{"x":"a"}'),
                _TC("c2", "slow_tool", '{"x":"b"}'),
                _TC("c3", "slow_tool", '{"x":"c"}'),
            ])
        else:
            m = _msg("terminé", None)

        class _Choice:
            message = m

        class _Resp:
            choices = [_Choice()]
            usage = _Usage()

        return _Resp()

    swarm_mod.completion = fake

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="t", model="gpt-4o")
    agent.tools = [slow_tool]
    s.agents = {"Tester": agent}

    t0 = time.time()
    _, messages, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=5)
    elapsed = time.time() - t0

    # 3 outils à 0.5s : en parallèle ~0.5s, en séquentiel ~1.5s.
    assert elapsed < 1.0, f"exécution non parallèle (durée {elapsed:.2f}s)"
    # Résultats présents et dans l'ordre a, b, c.
    tool_outputs = [m["content"] for m in messages if m.get("role") == "tool"]
    assert tool_outputs == ["done-a", "done-b", "done-c"], f"ordre/résultats: {tool_outputs}"
    print(f"OK: 3 outils exécutés en parallèle en {elapsed:.2f}s, ordre préservé")


def test_annulation_arrete_le_run():
    """Un run annulé doit s'arrêter sans appeler le LLM."""
    os.environ["SELF_IMPROVE"] = "false"
    from core import run_context

    calls = {"n": 0}
    swarm_mod.completion = _fake_completion_factory(calls)  # boucle sans fin sinon

    s = Swarm.__new__(Swarm)
    agent = Agent(name="Tester", system_prompt="t", model="gpt-4o")
    agent.tools = [noop_tool]
    s.agents = {"Tester": agent}

    rid = "cancel-test"
    token = run_context.current_run_id.set(rid)
    run_context.registry.start(rid)
    run_context.registry.cancel(rid)  # annulé avant le 1er tour
    try:
        _, _msgs, steps = s.run(agent, [{"role": "user", "content": "go"}], max_turns=10)
    finally:
        run_context.current_run_id.reset(token)

    assert calls["n"] == 0, f"LLM appelé malgré l'annulation ({calls['n']})"
    assert any("annulé" in str(st.get("content", "")) for st in steps), "pas de message d'annulation"
    print("OK: l'annulation arrête le run avant tout appel LLM")


if __name__ == "__main__":
    test_max_turns_borne_la_boucle()
    test_parse_text_tool_calls()
    test_disjoncteur_repetition_coupe_les_appels_identiques()
    test_hook_auto_amelioration_archive_un_retour()
    test_outils_multiples_executes_en_parallele()
    test_annulation_arrete_le_run()

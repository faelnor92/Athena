"""Workflows / pipelines déterministes : store (owner-scopé) + runner (chaînage, verrou).

Mode « chaîne de montage » type CrewAI : étapes séquentielles, chaque agent verrouillé
(pas de transfert NI de délégation), sortie d'une étape = entrée de la suivante, chaque
étape tracée. Le swarm.run est mocké pour ne pas appeler de vrai LLM.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def test_store_crud_owner_scoped():
    from core.pipelines import PipelineStore
    s = PipelineStore()
    p = s.upsert({"name": "Qualité", "steps": [
        {"agent": "Codeur", "instruction": "écris"},
        {"agent": "", "instruction": "ignorée"},          # étape invalide → filtrée
        {"agent": "Testeur", "instruction": "teste", "expected_output": "rapport"},
    ]}, owner="alice")
    assert len(p["steps"]) == 2, "les étapes invalides doivent être filtrées"
    assert s.get_owned(p["id"], owner="alice") is not None
    assert s.get_owned(p["id"], owner="bob") is None, "isolation par propriétaire"
    assert s.list(owner="bob") == []
    assert s.delete(p["id"], owner="bob") is False     # pas le propriétaire
    assert s.delete(p["id"], owner="alice") is True


def test_runner_chains_and_locks(monkeypatch=None):
    import core.state as st
    st.swarm.agents = {"A": type("Ag", (), {"name": "A"})(), "B": type("Ag", (), {"name": "B"})()}
    calls = []

    def fake_run(starting_agent, messages, max_turns=10, locked=False, lock_delegation=False, **kw):
        calls.append({"agent": starting_agent.name, "locked": locked,
                      "lock_delegation": lock_delegation, "content": messages[0]["content"]})
        out = f"[out-{starting_agent.name}]"
        return starting_agent, [{"role": "assistant", "content": out}], [{"type": "message", "content": out}]
    st.swarm.run = fake_run

    from tools.pipeline_tools import run_pipeline
    res = run_pipeline({"name": "T", "steps": [
        {"agent": "A", "instruction": "s1", "expected_output": "json"},
        {"agent": "B", "instruction": "s2"},
    ]}, initial_input="INIT")

    assert all(c["locked"] and c["lock_delegation"] for c in calls), "chaque étape doit être verrouillée"
    assert "INIT" in calls[0]["content"]
    assert "[out-A]" in calls[1]["content"], "sortie étape 1 -> entrée étape 2"
    assert res["final"] == "[out-B]"
    assert len(res["steps"]) == 2 and all("run_id" in s for s in res["steps"])


def test_runner_unknown_agent():
    import core.state as st
    st.swarm.agents = {}
    from tools.pipeline_tools import run_pipeline
    res = run_pipeline({"name": "X", "steps": [{"agent": "Nope", "instruction": "x"}]})
    assert res.get("error") and "introuvable" in res["error"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests pipelines passent.")

"""Champ `description` d'agent → routage + docstrings de transfert/délégation.

Vérifie que la spécialité explicite (renseignée à la création) est utilisée par le
mini-routeur ET dans les docstrings transfer_to_/delegate_to_, avec repli sur la 1ʳᵉ
phrase du system_prompt si description vide."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent import Agent  # noqa: E402
from core.swarm import Swarm  # noqa: E402


def _swarm(agents):
    s = Swarm.__new__(Swarm)
    s.orchestrator_name = "Athena"
    s.agents = {a.name: a for a in agents}
    return s


def test_handoff_docstring_uses_description():
    codeur = Agent(name="Codeur", system_prompt="...", model="gpt-4o",
                   description="Développe et débogue du code Python/JS")
    s = _swarm([Agent(name="Athena", system_prompt="orch", model="gpt-4o"), codeur])
    ho = s.create_handoff_function(codeur)
    dg = s.create_delegate_function(codeur)
    assert "Développe et débogue du code Python/JS" in ho.__doc__
    assert "Développe et débogue du code Python/JS" in dg.__doc__


def test_router_prompt_prefers_description():
    from core.agent_router import _agent_desc
    codeur = Agent(name="Codeur", system_prompt="Je suis Robert. Bla bla.",
                   model="gpt-4o", description="Spécialité CODE distinctive")
    desc = _agent_desc(codeur)
    # La description explicite doit être préférée.
    assert desc == "Spécialité CODE distinctive"


def test_router_falls_back_to_prompt_when_no_description():
    from core.agent_router import _agent_desc
    auteur = Agent(name="Auteur", system_prompt="Rédige des romans captivants. Etc.",
                   model="gpt-4o")  # pas de description
    desc = _agent_desc(auteur)
    # Repli sur le system_prompt (les 2 premières phrases).
    assert "Rédige des romans captivants" in desc
    assert "Etc" in desc



if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests du champ description passent.")

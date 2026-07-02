"""Bug #3 (routage qui fuit) : quand le routeur force la délégation vers un spécialiste,
l'orchestrateur PERD les outils-métier de ce spécialiste — y compris execute_bash_command
quand AUCUN hôte SSH n'est configuré (sinon il codait lui-même via bash). Avec un hôte SSH
configuré, bash reste (usage légitime : « connecte-toi à Prod »)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.swarm import Swarm  # noqa: E402


def _bash(command: str = ""):
    """Outil bash de test."""
    return "ok"


def _write_file(path: str = "", content: str = ""):
    """Outil d'écriture de test."""
    return "ok"


_bash.__name__ = "execute_bash_command"
_write_file.__name__ = "write_file"


def _completion_capture(seen):
    """Fake completion : capture le schéma d'outils envoyé au modèle, répond sans outil."""
    def fake(**kw):
        seen.append({t["function"]["name"] for t in (kw.get("tools") or [])})

        class _M:
            content = "ok"; tool_calls = None
            def model_dump(self, exclude_none=True): return {"role": "assistant", "content": "ok"}
        return type("R", (), {"choices": [type("C", (), {"message": _M()})()],
                              "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()})()
    return fake


def _swarm():
    s = Swarm.__new__(Swarm)
    s.orchestrator_name = "Athena"
    codeur = Agent(name="Codeur", system_prompt="dev", model="gpt-4o",
                   description="écrit et débogue du code")
    codeur.tools = [_bash, _write_file]
    orch = Agent(name="Athena", system_prompt="orchestre", model="gpt-4o", handoffs=["Codeur"])
    # L'orchestrateur porte AUSSI les outils code (config permissive) : c'est le cas qui fuit.
    orch.tools = [_bash, _write_file,
                  swarm_mod.create_delegate_function(s, "Codeur", codeur)
                  if hasattr(swarm_mod, "create_delegate_function") else _bash]
    s.agents = {"Athena": orch, "Codeur": codeur}
    return s, orch


def _run(monkey_hosts):
    os.environ["SELF_IMPROVE"] = "false"
    os.environ["TOOL_FILTER_ENABLED"] = "false"
    seen = []
    swarm_mod.completion = _completion_capture(seen)
    s, orch = _swarm()
    with mock.patch("core.swarm.engine.Swarm._route_target", return_value="Codeur"), \
         mock.patch("tools.ssh_hosts.list_hosts", return_value=monkey_hosts):
        s.run(orch, [{"role": "user", "content": "écris un script python qui trie une liste"}],
              max_turns=2)
    assert seen, "le fake completion n'a pas été appelé"
    return seen[0]


def test_routage_force_retire_les_outils_code_sans_ssh():
    exposed = _run(monkey_hosts=[])
    assert "write_file" not in exposed, exposed
    assert "execute_bash_command" not in exposed, \
        f"bash doit être retiré à l'orchestrateur sans hôte SSH (fuite bug #3) : {exposed}"


def test_routage_force_garde_bash_si_hote_ssh():
    exposed = _run(monkey_hosts=[{"id": "prod", "label": "Prod"}])
    assert "execute_bash_command" in exposed, \
        f"avec un hôte SSH configuré, l'orchestrateur garde bash (usage distant) : {exposed}"
    assert "write_file" not in exposed, exposed


if __name__ == "__main__":
    test_routage_force_retire_les_outils_code_sans_ssh()
    test_routage_force_garde_bash_si_hote_ssh()
    print("Tests anti-fuite de routage OK.")

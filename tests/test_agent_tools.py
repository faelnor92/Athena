"""Tests : création d'agents par Athena + suppression effective au hot-reload.

Exécution : python3 tests/test_agent_tools.py
"""
import os
import sys
import types
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from core.swarm import Swarm
import tools.agent_tools as at


def _fresh_swarm(tmp_yaml):
    """Un essaim minimal avec seulement Athena, chargé depuis un YAML temporaire."""
    with open(tmp_yaml, "w", encoding="utf-8") as f:
        yaml.safe_dump({"agents": [
            {"name": "Athena", "system_prompt": "orchestrateur", "model": "qwen3",
             "tools": [], "handoffs": []}
        ]}, f, allow_unicode=True)
    s = Swarm.__new__(Swarm)
    s.agents = {}
    s.load_agents(tmp_yaml)
    return s


def _install(swarm, tmp_yaml):
    """Branche le module 'server' factice et le chemin YAML attendus par l'outil."""
    server = types.ModuleType("server")
    server.swarm = swarm
    sys.modules["server"] = server
    at.AGENTS_PATH = tmp_yaml


def test_create_agent_cree_active_et_cable_le_handoff():
    tmp = tempfile.mktemp(suffix=".yaml")
    s = _fresh_swarm(tmp)
    _install(s, tmp)

    msg = at.create_agent(
        "Analyste", "Tu es un analyste de données.",
        tools="web_search, outil_bidon", avatar_type="scientist_blue",
    )
    assert "Analyste" in s.agents, "l'agent n'a pas été activé"
    assert "web_search" in msg and "outil_bidon" in msg, "whitelist d'outils non rapportée"
    # Le YAML doit porter l'avatar choisi (le frontend lit avatar_type depuis le YAML).
    data = yaml.safe_load(open(tmp))
    entry = next(a for a in data["agents"] if a["name"] == "Analyste")
    assert entry["avatar_type"] == "scientist_blue"
    assert entry["tools"] == ["web_search"], "un outil inconnu a été accordé"
    # Athena doit pouvoir transférer vers le nouvel agent.
    athena = s.agents["Athena"]
    assert any(getattr(f, "__name__", "") == "transfer_to_Analyste" for f in athena.tools)
    print("OK: create_agent crée, active, whitelist les outils et câble le handoff")


def test_create_agent_garde_fous():
    tmp = tempfile.mktemp(suffix=".yaml")
    s = _fresh_swarm(tmp)
    _install(s, tmp)

    assert at.create_agent("Athena", "x").startswith("Erreur"), "Athena devrait être protégé"
    assert "invalide" in at.create_agent("nom invalide!", "x"), "nom invalide non rejeté"
    assert "requis" in at.create_agent("Ok", ""), "system_prompt vide non rejeté"
    assert "Athena" in s.agents and len(s.agents) == 1, "aucun agent ne doit avoir été créé"
    print("OK: garde-fous (Athena protégé, nom/prompt invalides) respectés")


def test_suppression_effective_au_reload():
    """Le fix : un agent retiré de agents.yaml disparaît réellement après reload."""
    tmp = tempfile.mktemp(suffix=".yaml")
    s = _fresh_swarm(tmp)
    _install(s, tmp)

    at.create_agent("Ephemere", "agent temporaire")
    assert "Ephemere" in s.agents

    data = yaml.safe_load(open(tmp))
    data["agents"] = [a for a in data["agents"] if a["name"] != "Ephemere"]
    yaml.safe_dump(data, open(tmp, "w"), allow_unicode=True)
    s.load_agents(tmp)

    assert "Ephemere" not in s.agents, "agent supprimé toujours présent après reload"
    print("OK: suppression effective au hot-reload (self.agents réinitialisé)")


if __name__ == "__main__":
    test_create_agent_cree_active_et_cable_le_handoff()
    test_create_agent_garde_fous()
    test_suppression_effective_au_reload()

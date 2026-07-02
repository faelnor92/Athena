"""Evals de ROUTAGE D'OUTILS en CI (déterministes : chemin keyword, sans LLM ni
embeddings). Point faible historique instrumenté : le bon sous-ensemble d'outils
doit être exposé pour des requêtes types FR/EN — les cas vivent dans
evals/routing_cases.json (en ajouter un suffit, ce test les rejoue tous)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "evals", "routing_cases.json")


def _all_tool_names():
    from core.swarm.engine import AVAILABLE_TOOLS
    return set(AVAILABLE_TOOLS.keys())


def test_routing_evals():
    from core.swarm.text_tools import select_tool_subset
    with open(_CASES, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    assert cases, "aucun cas d'eval de routage"
    names = _all_tool_names()
    failures = []
    for case in cases:
        kept = select_tool_subset(case["query"], names)
        for t in case.get("must_include", []):
            if t not in names:
                failures.append(f"[{case['name']}] outil inconnu dans must_include : {t}")
            elif t not in kept:
                failures.append(f"[{case['name']}] outil ATTENDU non exposé : {t}")
        for t in case.get("must_exclude", []):
            if t in kept:
                failures.append(f"[{case['name']}] outil HORS-SUJET exposé : {t}")
    assert not failures, "évals de routage en échec :\n" + "\n".join(failures)
    print(f"OK: {len(cases)} evals de routage keyword passent")


def test_surete_outil_inconnu_jamais_filtre():
    """Principe de sûreté du routeur : un outil non rangé dans un groupe (cœur, skill
    dynamique, MCP) n'est JAMAIS retiré, quelle que soit la requête."""
    from core.swarm.text_tools import select_tool_subset
    names = _all_tool_names() | {"skill_inconnue_du_routeur"}
    kept = select_tool_subset("allume la lumière", names)
    assert "skill_inconnue_du_routeur" in kept
    print("OK: un outil inconnu du routeur reste toujours exposé")


if __name__ == "__main__":
    test_routing_evals()
    test_surete_outil_inconnu_jamais_filtre()
    print("\nEvals de routage : tout passe.")

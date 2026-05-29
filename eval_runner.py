#!/usr/bin/env python3
"""Lanceur d'évaluation en ligne de commande.

Usage :
    python3 eval_runner.py [chemin_cases.json]

Charge des cas d'éval (défaut: evals/cases.json), les exécute via l'essaim et
affiche un rapport pass/fail. Nécessite un LLM configuré (.env).
"""
import json
import os
import sys

from dotenv import load_dotenv


def main():
    load_dotenv()
    path = sys.argv[1] if len(sys.argv) > 1 else "evals/cases.json"
    if not os.path.exists(path):
        print(f"Fichier de cas introuvable : {path}")
        print("Astuce : copiez evals/cases.example.json en evals/cases.json")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    if isinstance(cases, dict):
        cases = cases.get("cases", [])

    from core.swarm import Swarm
    from core.eval import run_eval

    swarm = Swarm("agents.yaml")
    report = run_eval(swarm, cases)

    print("\n=== RAPPORT D'ÉVALUATION ===")
    for r in report["results"]:
        mark = "✅" if r.get("passed") else "❌"
        print(f"{mark} {r['name']}")
        if r.get("error"):
            print(f"    erreur: {r['error']}")
        for c in r.get("checks", []):
            cm = "ok" if c.get("ok") else "ÉCHEC"
            print(f"    - [{cm}] {c['type']} attendu={c.get('expected')}")
    print(f"\nTotal: {report['total']} | Réussis: {report['passed']} | Échoués: {report['failed']}")
    sys.exit(0 if report["failed"] == 0 else 1)


if __name__ == "__main__":
    main()

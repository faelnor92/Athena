#!/usr/bin/env python3
"""Banc de test du sous-système CODE : fait corriger un vrai bug par le Codeur et mesure le
résultat (outils appelés, éditions, tokens, tours, SUCCÈS vérifié). À lancer sur le serveur :

    .venv/bin/python scripts/bench_coder.py
    .venv/bin/python scripts/bench_coder.py --model custom/qwen-coder   # forcer un modèle
    .venv/bin/python scripts/bench_coder.py --agent Codeur --turns 12

Tâche : un solver.py contient un bug (`total = n` au lieu de `+=`). On demande à l'agent de le
corriger, puis on EXÉCUTE le code pour vérifier que solve([1,2,3]) == 6. Mesure où ça coince :
édition (les edits s'appliquent-ils ?), raisonnement (trouve-t-il le bug ?), tours/tokens.
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
for _cand in (".venv/bin/python", "venv/bin/python", ".venv/bin/python3", "venv/bin/python3"):
    _vp = os.path.join(ROOT, _cand)
    if os.path.exists(_vp) and os.path.realpath(_vp) != os.path.realpath(sys.executable):
        os.execv(_vp, [_vp, os.path.abspath(__file__)] + sys.argv[1:])
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    for _l in open(_env, encoding="utf-8"):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--model", default="", help="forcer un modèle (ex. custom/qwen-coder)")
ap.add_argument("--agent", default="", help="agent à utiliser (défaut : Codeur sinon orchestrateur)")
ap.add_argument("--turns", type=int, default=12)
args = ap.parse_args()

# Projet temporaire = workspace actif ; sandbox off (on mesure édition+raisonnement, pas Docker).
proj = tempfile.mkdtemp(prefix="bench_coder_")
os.environ["ACTIVE_WORKSPACE_DIR"] = proj
os.environ.setdefault("SANDBOX_MODE", "off")
BUG = ("def solve(nums):\n"
       "    total = 0\n"
       "    for n in nums:\n"
       "        total = n   # BUG: devrait accumuler\n"
       "    return total\n")
open(os.path.join(proj, "solver.py"), "w").write(BUG)

from core.state import swarm, _forced_model  # noqa: E402

agent = swarm.agents.get(args.agent) if args.agent else (
    swarm.agents.get("Codeur") or swarm.agents.get(getattr(swarm, "orchestrator_name", "Athena")))
if not agent:
    print("❌ Aucun agent disponible."); sys.exit(1)

task = ("Dans le fichier solver.py du projet, la fonction solve(nums) est boguée : elle renvoie le "
        "dernier élément au lieu de la SOMME des nombres. Corrige-la (édite le fichier) pour qu'elle "
        "renvoie la somme. Ne réécris pas tout, corrige juste la ligne fautive.")

print(f"🧪 Banc Codeur — agent={agent.name} modèle={(args.model or agent.model)}  projet={proj}")
tok = _forced_model.set(args.model) if args.model else None
t0 = time.time()
try:
    _next, chain, steps = swarm.run(agent, [{"role": "user", "content": task}],
                                    max_turns=args.turns, locked=True)
finally:
    if tok is not None:
        _forced_model.reset(tok)
dt = time.time() - t0

# Analyse des steps
from collections import Counter
tools = Counter(s.get("tool") for s in steps if s.get("type") == "tool_call")
edit_fail = sum(1 for s in steps if s.get("type") == "tool_output"
                and "introuvable" in str(s.get("output", "")).lower())
pin = sum(int(s.get("prompt_tokens", 0) or 0) for s in steps if s.get("type") == "usage")
pout = sum(int(s.get("completion_tokens", 0) or 0) for s in steps if s.get("type") == "usage")
turns = sum(1 for s in steps if s.get("type") == "usage")

# Vérif RÉELLE : on exécute le code produit
verdict, detail = "❌ ÉCHEC", ""
try:
    ns = {}
    exec(open(os.path.join(proj, "solver.py")).read(), ns)
    got = ns["solve"]([1, 2, 3])
    if got == 6:
        verdict, detail = "✅ RÉUSSI", "solve([1,2,3]) == 6"
    else:
        detail = f"solve([1,2,3]) == {got} (attendu 6)"
except Exception as e:  # noqa: BLE001
    detail = f"code cassé : {e}"

print("\n────────── RÉSULTAT ──────────")
print(f"{verdict}  ({detail})")
print(f"⏱  {dt:.1f}s · {turns} tours · tokens ↓{pin} ↑{pout}")
print(f"🔧 outils: {dict(tools) or '— aucun —'}")
print(f"✏️  éditions en échec (old_string introuvable): {edit_fail}")
print("\nDiagnostic :")
if verdict.startswith("✅"):
    print("  Le modèle a trouvé le bug ET appliqué l'édition correctement.")
else:
    if not tools:
        print("  ⚠️ AUCUN outil appelé → le modèle n'agit pas (capacité/format tool-calling).")
    elif edit_fail:
        print("  ⚠️ Éditions rejetées (old_string introuvable) → le modèle ne reproduit pas le code exact.")
    elif "write_file" in tools or "edit_file" in tools:
        print("  ⚠️ A édité mais le résultat est faux → raisonnement (n'a pas bien corrigé).")
    if turns >= args.turns:
        print("  ⚠️ Budget de tours atteint → boucle / pas de convergence.")

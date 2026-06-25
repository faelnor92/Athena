#!/usr/bin/env python3
"""Banc de test du sous-système CODE : fait corriger de vrais bugs par le Codeur et VÉRIFIE le
résultat en exécutant le code. Mesure outils, éditions rejetées, tokens, tours, succès.

    .venv/bin/python scripts/bench_coder.py                 # tâche SIMPLE (1 bug, 1 fichier)
    .venv/bin/python scripts/bench_coder.py --hard          # tâche DURE (3 bugs, 3 fichiers, tests)
    .venv/bin/python scripts/bench_coder.py --hard --model custom/<gros-coder>
    .venv/bin/python scripts/bench_coder.py --agent Codeur --turns 20

--hard : un package shop/ avec 3 bugs RÉPARTIS (subtotal ignore les quantités ; remise traitée
comme un montant absolu au lieu d'un % ; import manquant) + test_shop.py qui échoue. On ne dit PAS
où sont les bugs → ça teste navigation multi-fichiers, raisonnement et éditions multiples.
"""
import os
import sys
import tempfile
import time
import subprocess

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
ap.add_argument("--model", default="")
ap.add_argument("--agent", default="")
ap.add_argument("--hard", action="store_true", help="tâche dure (multi-fichiers + tests)")
ap.add_argument("--turns", type=int, default=0)
args = ap.parse_args()

proj = tempfile.mkdtemp(prefix="bench_coder_")
os.environ["ACTIVE_WORKSPACE_DIR"] = proj
os.environ.setdefault("SANDBOX_MODE", "off")


def _w(rel, content):
    p = os.path.join(proj, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True) if os.path.dirname(rel) else None
    open(p, "w").write(content)


if args.hard:
    _w("shop/__init__.py", "")
    _w("shop/cart.py",
       "class Cart:\n    def __init__(self):\n        self.items = []\n"
       "    def add(self, name, price, qty=1):\n        self.items.append((name, price, qty))\n"
       "    def subtotal(self):\n        return sum(price for name, price, qty in self.items)\n")
    _w("shop/discount.py",
       "def apply_discount(amount, percent):\n    return amount - percent\n")
    _w("shop/checkout.py",
       "from shop.cart import Cart\n\n"
       "def checkout(cart, percent=0):\n    return apply_discount(cart.subtotal(), percent)\n")
    _w("test_shop.py",
       "from shop.cart import Cart\nfrom shop.checkout import checkout\n\n"
       "def run():\n    c = Cart()\n    c.add('a', 10, 2)\n    c.add('b', 5)\n"
       "    assert c.subtotal() == 25, ('subtotal', c.subtotal())\n"
       "    assert checkout(c, 10) == 22.5, ('checkout', checkout(c, 10))\n    return 'OK'\n")
    task = ("Le projet contient un package shop/ et un fichier test_shop.py dont les tests ÉCHOUENT. "
            "Corrige le code de shop/ pour que `test_shop.run()` passe sans erreur. NE modifie PAS "
            "test_shop.py. Trouve les bugs toi-même (lis les fichiers).")
    default_turns = 25
else:
    _w("solver.py",
       "def solve(nums):\n    total = 0\n    for n in nums:\n        total = n   # BUG\n    return total\n")
    task = ("Dans solver.py, solve(nums) est boguée : elle renvoie le dernier élément au lieu de la "
            "SOMME. Corrige-la (édite le fichier, ne réécris pas tout).")
    default_turns = 12

turns = args.turns or default_turns

from core.state import swarm, _forced_model  # noqa: E402

agent = swarm.agents.get(args.agent) if args.agent else (
    swarm.agents.get("Codeur") or swarm.agents.get(getattr(swarm, "orchestrator_name", "Athena")))
if not agent:
    print("❌ Aucun agent disponible."); sys.exit(1)

print(f"🧪 Banc Codeur [{'DUR' if args.hard else 'simple'}] — agent={agent.name} "
      f"modèle={(args.model or agent.model)} turns={turns}\n   projet={proj}")
tok = _forced_model.set(args.model) if args.model else None
t0 = time.time()
try:
    _next, chain, steps = swarm.run(agent, [{"role": "user", "content": task}],
                                    max_turns=turns, locked=True)
finally:
    if tok is not None:
        _forced_model.reset(tok)
dt = time.time() - t0

from collections import Counter
tools = Counter(s.get("tool") for s in steps if s.get("type") == "tool_call")
edit_fail = sum(1 for s in steps if s.get("type") == "tool_output"
                and "introuvable" in str(s.get("output", "")).lower())
pin = sum(int(s.get("prompt_tokens", 0) or 0) for s in steps if s.get("type") == "usage")
pout = sum(int(s.get("completion_tokens", 0) or 0) for s in steps if s.get("type") == "usage")
nturns = sum(1 for s in steps if s.get("type") == "usage")

# Vérification RÉELLE
verdict, detail = "❌ ÉCHEC", ""
try:
    if args.hard:
        r = subprocess.run([sys.executable, "-c",
                            f"import sys; sys.path.insert(0, {proj!r}); import test_shop; print(test_shop.run())"],
                           cwd=proj, capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and "OK" in r.stdout:
            verdict, detail = "✅ RÉUSSI", "tous les tests passent"
        else:
            detail = (r.stderr.strip().splitlines() or [r.stdout.strip()])[-1][:160] if (r.stderr or r.stdout) else "tests KO"
    else:
        ns = {}
        exec(open(os.path.join(proj, "solver.py")).read(), ns)
        got = ns["solve"]([1, 2, 3])
        verdict, detail = ("✅ RÉUSSI", "solve([1,2,3])==6") if got == 6 else ("❌ ÉCHEC", f"renvoie {got}")
except Exception as e:  # noqa: BLE001
    detail = f"code cassé : {e}"

print("\n────────── RÉSULTAT ──────────")
print(f"{verdict}  ({detail})")
print(f"⏱  {dt:.1f}s · {nturns} tours · tokens ↓{pin} ↑{pout}")
print(f"🔧 outils: {dict(tools) or '— aucun —'}")
print(f"✏️  éditions rejetées (old_string introuvable): {edit_fail}")
print("\nDiagnostic :")
if verdict.startswith("✅"):
    print("  Bugs trouvés ET corrigés correctement" + (" sur plusieurs fichiers." if args.hard else "."))
else:
    if not tools:
        print("  ⚠️ Aucun outil appelé → capacité / format tool-calling du modèle.")
    if edit_fail:
        print(f"  ⚠️ {edit_fail} édition(s) rejetée(s) → le modèle ne reproduit pas le code exact.")
    if args.hard and tools.get("read_file", 0) < 2:
        print("  ⚠️ Peu de lecture de fichiers → n'a pas exploré le multi-fichiers.")
    if (tools.get("edit_file", 0) + tools.get("write_file", 0)) and not edit_fail:
        print("  ⚠️ A édité mais résultat faux → raisonnement (bugs mal compris / partiellement corrigés).")
    if nturns >= turns:
        print("  ⚠️ Budget de tours atteint → pas de convergence / boucle.")

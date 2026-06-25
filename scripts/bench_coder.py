#!/usr/bin/env python3
"""Banc de test du sous-système CODE : fait corriger de vrais problèmes par le Codeur et VÉRIFIE le
résultat en EXÉCUTANT le code. Mesure outils, éditions rejetées, tokens, tours, succès.

    .venv/bin/python scripts/bench_coder.py                 # SIMPLE (1 bug, 1 fichier)
    .venv/bin/python scripts/bench_coder.py --hard          # DUR (3 bugs, 3 fichiers, tests)
    .venv/bin/python scripts/bench_coder.py --security      # SÉCURITÉ (3 failles à corriger)
    .venv/bin/python scripts/bench_coder.py --security --model custom/<gros-coder>
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
ap.add_argument("--hard", action="store_true")
ap.add_argument("--security", action="store_true")
ap.add_argument("--turns", type=int, default=0)
args = ap.parse_args()

proj = tempfile.mkdtemp(prefix="bench_coder_")
os.environ["ACTIVE_WORKSPACE_DIR"] = proj
os.environ.setdefault("SANDBOX_MODE", "off")
SECRET = "sk-live-SECRET-0001"


def _w(rel, content):
    p = os.path.join(proj, rel)
    if os.path.dirname(rel):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(content)


if args.security:
    scenario, default_turns = "SÉCURITÉ", 40
    _w("app/__init__.py", "")
    # 1) Injection SQL (concaténation)
    _w("app/db.py",
       "def get_user(db, name):\n"
       "    cur = db.execute(\"SELECT id FROM users WHERE name = '%s'\" % name)\n"
       "    return cur.fetchone()\n")
    # 2) Traversée de chemin
    _w("app/files.py",
       "import os\n\n"
       "def read_doc(name):\n"
       "    return open(os.path.join('docs', name)).read()\n")
    # 3) Injection de commande (shell=True)
    _w("app/ops.py",
       "import subprocess\n\n"
       "def count_lines(path):\n"
       "    return subprocess.check_output('wc -l ' + path, shell=True, text=True)\n")
    # 4) eval sur entrée utilisateur
    _w("app/calc.py",
       "def calc(expr):\n    return eval(expr)\n")
    # 5) Secret en dur + 6) hash MD5 pour mots de passe
    _w("app/config.py", f"API_KEY = \"{SECRET}\"\n")
    _w("app/auth.py",
       "import hashlib\n\n"
       "def hash_password(pw):\n    return hashlib.md5(pw.encode()).hexdigest()\n")
    # LEURRE : paraît dangereux (subprocess) mais est SAIN (shell=False, args fixes) → NE PAS « corriger »
    _w("app/util.py",
       "import subprocess\n\n"
       "def disk_free():\n    # sûr : pas de shell, arguments fixes\n"
       "    return subprocess.check_output(['df', '-h'], text=True)\n")
    _w("docs/ok.txt", "l1\nl2\nl3\n")
    _w("secret.txt", "TOP_SECRET_DATA")
    _w("test_security.py",
       "import sqlite3, os\n"
       "import app.db as dbm, app.files as fm, app.ops as ops, app.calc as calc\n\n"
       "def run():\n"
       "    conn = sqlite3.connect(':memory:')\n"
       "    conn.execute('CREATE TABLE users(id INTEGER, name TEXT)')\n"
       "    conn.executemany('INSERT INTO users VALUES (?,?)', [(1,'alice'),(2,'bob')])\n"
       "    assert dbm.get_user(conn, 'alice') is not None, 'fonction db cassée'\n"
       "    assert dbm.get_user(conn, \"zzz' OR '1'='1\") is None, 'FAILLE injection SQL'\n"
       "    assert 'l2' in fm.read_doc('ok.txt'), 'fonction files cassée'\n"
       "    leaked = ''\n"
       "    try:\n        leaked = fm.read_doc('../secret.txt') or ''\n    except Exception:\n        leaked = ''\n"
       "    assert 'TOP_SECRET' not in leaked, 'FAILLE traversée de chemin'\n"
       "    out = ''\n"
       "    try:\n        out = ops.count_lines('/dev/null; echo PWNED') or ''\n    except Exception:\n        out = ''\n"
       "    assert 'PWNED' not in str(out), 'FAILLE injection de commande'\n"
       "    assert '3' in str(ops.count_lines('docs/ok.txt')), 'fonction ops cassée'\n"
       "    assert calc.calc('42') == 42, 'fonction calc cassée'\n"
       "    marker = os.path.join(os.path.dirname(__file__), 'PWNED_EVAL')\n"
       "    if os.path.exists(marker):\n        os.remove(marker)\n"
       "    try:\n        calc.calc(\"open(%r,'w').write('x')\" % marker)\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(marker), 'FAILLE eval (exécution arbitraire)'\n"
       "    return 'OK'\n")
    task = ("Le package app/ contient PLUSIEURS failles de sécurité (à toi de les trouver TOUTES, "
            "à plusieurs endroits) : corrige-les SANS casser les fonctionnalités normales. "
            "test_security.py vérifie le comportement — NE le modifie PAS. Attention : "
            "(a) retire tout secret d'API en dur (lis-le depuis l'environnement), "
            "(b) n'utilise PAS MD5/SHA1 pour les mots de passe (primitive forte salée), "
            "(c) ne casse pas du code déjà sûr. Lis les fichiers avant d'éditer.")
elif args.hard:
    scenario, default_turns = "DUR", 25
    _w("shop/__init__.py", "")
    _w("shop/cart.py",
       "class Cart:\n    def __init__(self):\n        self.items = []\n"
       "    def add(self, name, price, qty=1):\n        self.items.append((name, price, qty))\n"
       "    def subtotal(self):\n        return sum(price for name, price, qty in self.items)\n")
    _w("shop/discount.py", "def apply_discount(amount, percent):\n    return amount - percent\n")
    _w("shop/checkout.py",
       "from shop.cart import Cart\n\n"
       "def checkout(cart, percent=0):\n    return apply_discount(cart.subtotal(), percent)\n")
    _w("test_shop.py",
       "from shop.cart import Cart\nfrom shop.checkout import checkout\n\n"
       "def run():\n    c = Cart()\n    c.add('a', 10, 2)\n    c.add('b', 5)\n"
       "    assert c.subtotal() == 25, ('subtotal', c.subtotal())\n"
       "    assert checkout(c, 10) == 22.5, ('checkout', checkout(c, 10))\n    return 'OK'\n")
    task = ("Le projet contient un package shop/ et test_shop.py dont les tests ÉCHOUENT. Corrige le "
            "code de shop/ pour que `test_shop.run()` passe. NE modifie PAS test_shop.py. Trouve les "
            "bugs toi-même (lis les fichiers).")
else:
    scenario, default_turns = "simple", 12
    _w("solver.py",
       "def solve(nums):\n    total = 0\n    for n in nums:\n        total = n   # BUG\n    return total\n")
    task = ("Dans solver.py, solve(nums) renvoie le dernier élément au lieu de la SOMME. Corrige-la "
            "(édite le fichier, ne réécris pas tout).")

turns = args.turns or default_turns

from core.state import swarm, _forced_model  # noqa: E402

agent = swarm.agents.get(args.agent) if args.agent else (
    swarm.agents.get("Codeur") or swarm.agents.get(getattr(swarm, "orchestrator_name", "Athena")))
if not agent:
    print("❌ Aucun agent disponible."); sys.exit(1)

print(f"🧪 Banc Codeur [{scenario}] — agent={agent.name} modèle={(args.model or agent.model)} "
      f"turns={turns}\n   projet={proj}")
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


def _run_test(module):
    r = subprocess.run([sys.executable, "-c",
                        f"import sys; sys.path.insert(0, {proj!r}); import {module} as t; print(t.run())"],
                       cwd=proj, capture_output=True, text=True, timeout=25)
    return r


verdict, detail = "❌ ÉCHEC", ""
try:
    if args.security:
        r = _run_test("test_security")
        secret_gone = SECRET not in open(os.path.join(proj, "app/config.py")).read()
        _auth = open(os.path.join(proj, "app/auth.py")).read().lower()
        auth_hardened = ("md5" not in _auth and "sha1(" not in _auth
                         and any(x in _auth for x in ("pbkdf2", "scrypt", "bcrypt", "sha256", "argon2")))
        _util = open(os.path.join(proj, "app/util.py")).read()
        leurre_ok = "shell=true" not in _util.lower()  # le leurre sûr ne doit pas avoir été « corrigé » en pire
        tests_ok = r.returncode == 0 and "OK" in r.stdout
        if tests_ok and secret_gone and auth_hardened and leurre_ok:
            verdict, detail = "✅ RÉUSSI", "5 failles corrigées, fonctions intactes, leurre épargné"
        else:
            bits = []
            if not tests_ok:
                bits.append((r.stderr.strip().splitlines() or ["tests KO"])[-1][:120])
            if not secret_gone:
                bits.append("secret en dur présent")
            if not auth_hardened:
                bits.append("hash mot de passe non durci (MD5/SHA1 ?)")
            if not leurre_ok:
                bits.append("leurre cassé (a introduit shell=True)")
            detail = " ; ".join(bits)
    elif args.hard:
        r = _run_test("test_shop")
        verdict, detail = ("✅ RÉUSSI", "tous les tests passent") if (r.returncode == 0 and "OK" in r.stdout) \
            else ("❌ ÉCHEC", (r.stderr.strip().splitlines() or ["tests KO"])[-1][:140])
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
    extra = " (3 failles)" if args.security else (" (multi-fichiers)" if args.hard else "")
    print(f"  Problèmes trouvés ET corrigés correctement{extra}.")
else:
    if not tools:
        print("  ⚠️ Aucun outil appelé → capacité / format tool-calling du modèle.")
    if edit_fail:
        print(f"  ⚠️ {edit_fail} édition(s) rejetée(s) → ne reproduit pas le code exact.")
    if (args.hard or args.security) and tools.get("read_file", 0) < 2:
        print("  ⚠️ Peu de lecture → n'a pas exploré tous les fichiers.")
    if (tools.get("edit_file", 0) + tools.get("write_file", 0)) and not edit_fail:
        print("  ⚠️ A édité mais résultat incorrect → raisonnement (corrections partielles/erronées).")
    if args.security:
        print("  ⚠️ Sécurité : une faille subsiste ou une fonction a été cassée (sur-correction).")
    if nturns >= turns:
        print("  ⚠️ Budget de tours atteint → pas de convergence / boucle.")

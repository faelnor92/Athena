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
ap.add_argument("--brutal", action="store_true", help="sécurité EXTRÊME (9 failles dont subtiles)")
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


if args.brutal:
    scenario, default_turns = "BRUTAL", 60
    _w("app/__init__.py", "")
    # 1) Injection SQL (concaténation) — facile
    _w("app/db.py",
       "def get_user(db, name):\n"
       "    return db.execute(\"SELECT id FROM users WHERE name = '%s'\" % name).fetchone()\n\n"
       "def get_log(db, lid):\n"
       "    # LEURRE : déjà paramétré, NE PAS 'corriger'\n"
       "    return db.execute('SELECT msg FROM logs WHERE id = ?', (lid,)).fetchone()\n")
    # 2) Injection de commande (shell=True)
    _w("app/ops.py",
       "import subprocess\n\n"
       "def count_lines(path):\n"
       "    return subprocess.check_output('wc -l ' + path, shell=True, text=True)\n")
    # 3) Traversée de chemin
    _w("app/files.py",
       "import os\n\ndef read_doc(name):\n    return open(os.path.join('docs', name)).read()\n")
    # 4) eval sur entrée
    _w("app/calc.py", "def calc(expr):\n    return eval(expr)\n")
    # 5) Désérialisation pickle d'une donnée non fiable (RCE) — SUBTIL
    _w("app/cache.py",
       "import pickle\n\n"
       "def load(blob):\n    # charge un objet sérialisé reçu du réseau/cache\n"
       "    return pickle.loads(blob)\n")
    # 6) Porte dérobée d'authentification (mot de passe maître) — SUBTIL, logique
    # 7) + hash à sel STATIQUE (faux-correct) — SUBTIL, crypto
    _w("app/auth.py",
       "import hashlib\n\n"
       "_USERS = {'alice': 'wonderland'}\n\n"
       "def login(user, pw):\n"
       "    if pw == 'master-2024':\n        return True\n"
       "    return _USERS.get(user) == pw\n\n"
       "def hash_password(pw):\n    return hashlib.md5(pw.encode()).hexdigest()\n")
    # 8) Mass-assignment → élévation de privilèges — SUBTIL, logique
    _w("app/users.py",
       "class User:\n    def __init__(self):\n        self.name = ''\n        self.is_admin = False\n\n"
       "def update_profile(user, data):\n    for k, v in data.items():\n        setattr(user, k, v)\n")
    # 9) Secret en dur
    _w("app/config.py", f"API_KEY = \"{SECRET}\"\n")
    # LEURRES : code qui PARAÎT dangereux mais est SAIN → NE PAS toucher
    _w("app/util.py",
       "import subprocess\n\n"
       "def disk_free():\n    # sûr : pas de shell, args fixes\n"
       "    return subprocess.check_output(['df', '-h'], text=True)\n\n"
       "# NOTE : ne PAS utiliser eval() ici (ce commentaire n'est pas du code)\n")
    _w("docs/ok.txt", "l1\nl2\nl3\n")
    _w("secret.txt", "TOP_SECRET_DATA")
    _w("test_brutal.py",
       "import sqlite3, os, json\n"
       "import app.db as dbm, app.files as fm, app.ops as ops, app.calc as calc\n"
       "import app.auth as auth, app.users as users, app.cache as cache\n\n"
       "def run():\n"
       "    conn = sqlite3.connect(':memory:')\n"
       "    conn.execute('CREATE TABLE users(id INTEGER, name TEXT)')\n"
       "    conn.executemany('INSERT INTO users VALUES (?,?)', [(1,'alice'),(2,'bob')])\n"
       "    conn.execute('CREATE TABLE logs(id INTEGER, msg TEXT)')\n"
       "    conn.execute(\"INSERT INTO logs VALUES (1,'hi')\")\n"
       "    # 1 SQLi\n"
       "    assert dbm.get_user(conn, 'alice') is not None, 'fonction db cassée'\n"
       "    assert dbm.get_user(conn, \"zzz' OR '1'='1\") is None, 'FAILLE injection SQL'\n"
       "    assert dbm.get_log(conn, 1) is not None, 'leurre db cassé'\n"
       "    # 2 cmd injection\n"
       "    cm = os.path.join(os.path.dirname(__file__), 'PWNED_CMD')\n"
       "    if os.path.exists(cm):\n        os.remove(cm)\n"
       "    try:\n        ops.count_lines('/dev/null; touch ' + cm)\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(cm), 'FAILLE injection de commande'\n"
       "    assert '3' in str(ops.count_lines('docs/ok.txt')), 'fonction ops cassée'\n"
       "    # 3 path traversal\n"
       "    leaked = ''\n"
       "    try:\n        leaked = fm.read_doc('../secret.txt') or ''\n    except Exception:\n        leaked = ''\n"
       "    assert 'TOP_SECRET' not in leaked, 'FAILLE traversée de chemin'\n"
       "    assert 'l2' in fm.read_doc('ok.txt'), 'fonction files cassée'\n"
       "    # 4 eval\n"
       "    me = os.path.join(os.path.dirname(__file__), 'PWNED_EVAL')\n"
       "    if os.path.exists(me):\n        os.remove(me)\n"
       "    try:\n        calc.calc(\"open(%r,'w').write('x')\" % me)\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(me), 'FAILLE eval'\n"
       "    assert calc.calc('42') == 42, 'fonction calc cassée'\n"
       "    # 5 pickle RCE\n"
       "    mp = os.path.join(os.path.dirname(__file__), 'PWNED_PICKLE')\n"
       "    if os.path.exists(mp):\n        os.remove(mp)\n"
       "    import pickle as _pk\n"
       "    class _Evil:\n        def __reduce__(self):\n            return (os.system, ('touch ' + mp,))\n"
       "    try:\n        cache.load(_pk.dumps(_Evil()))\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(mp), 'FAILLE désérialisation pickle (RCE)'\n"
       "    # 6 backdoor auth\n"
       "    assert auth.login('alice', 'wonderland'), 'fonction login cassée'\n"
       "    assert not auth.login('alice', 'master-2024'), 'FAILLE porte dérobée (mot de passe maître)'\n"
       "    assert not auth.login('intrus', 'x'), 'login accepte un inconnu'\n"
       "    # 7 sel statique / MD5\n"
       "    assert auth.hash_password('s3cret') != auth.hash_password('s3cret'), 'FAILLE hash (MD5/sel statique)'\n"
       "    # 8 mass assignment / privesc\n"
       "    u = users.User()\n"
       "    users.update_profile(u, {'name': 'Bob', 'is_admin': True})\n"
       "    assert u.name == 'Bob', 'fonction users cassée'\n"
       "    assert u.is_admin is False, 'FAILLE mass-assignment (élévation de privilèges)'\n"
       "    return 'OK'\n")
    task = ("Le package app/ est une mini-appli avec de NOMBREUSES failles de sécurité, certaines "
            "ÉVIDENTES, d'autres SUBTILES (logique, crypto, désérialisation). Trouve-les TOUTES et "
            "corrige-les SANS casser les fonctionnalités ni 'corriger' du code déjà sûr. test_brutal.py "
            "vérifie — NE le modifie PAS. Indices : pense injection (SQL/commande/chemin/eval), "
            "désérialisation non sûre, AUTHENTIFICATION (porte dérobée ?), gestion des PRIVILÈGES "
            "(affectation en masse ?), CRYPTO des mots de passe (algo + sel), secrets en dur. "
            "Lis chaque fichier attentivement avant d'éditer.")
elif args.security:
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
       "import app.db as dbm, app.files as fm, app.ops as ops, app.calc as calc\n"
       "import app.auth as auth\n\n"
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
       "    cmd_marker = os.path.join(os.path.dirname(__file__), 'PWNED_CMD')\n"
       "    if os.path.exists(cmd_marker):\n        os.remove(cmd_marker)\n"
       "    try:\n        ops.count_lines('/dev/null; touch ' + cmd_marker)\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(cmd_marker), 'FAILLE injection de commande'\n"
       "    assert '3' in str(ops.count_lines('docs/ok.txt')), 'fonction ops cassée'\n"
       "    assert calc.calc('42') == 42, 'fonction calc cassée'\n"
       "    marker = os.path.join(os.path.dirname(__file__), 'PWNED_EVAL')\n"
       "    if os.path.exists(marker):\n        os.remove(marker)\n"
       "    try:\n        calc.calc(\"open(%r,'w').write('x')\" % marker)\n    except Exception:\n        pass\n"
       "    assert not os.path.exists(marker), 'FAILLE eval (exécution arbitraire)'\n"
       "    h1 = auth.hash_password('s3cret'); h2 = auth.hash_password('s3cret')\n"
       "    assert h1 != h2, 'FAILLE hash : déterministe (MD5 ou sel statique/partagé) — sel aléatoire par mot de passe attendu'\n"
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
    if args.brutal:
        r = _run_test("test_brutal")
        secret_gone = SECRET not in open(os.path.join(proj, "app/config.py")).read()
        _util = open(os.path.join(proj, "app/util.py")).read().lower()
        leurre_ok = "shell=true" not in _util  # leurre sûr non « corrigé » en pire
        tests_ok = r.returncode == 0 and "OK" in r.stdout
        if tests_ok and secret_gone and leurre_ok:
            verdict, detail = "✅ RÉUSSI", "9 failles corrigées, fonctions intactes, leurres épargnés"
        else:
            bits = []
            if not tests_ok:
                bits.append((r.stderr.strip().splitlines() or ["tests KO"])[-1][:140])
            if not secret_gone:
                bits.append("secret en dur présent")
            if not leurre_ok:
                bits.append("leurre cassé (shell=True introduit)")
            detail = " ; ".join(bits)
    elif args.security:
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
    extra = (" (9 failles + leurres)" if args.brutal else " (5 failles + leurre)" if args.security
             else (" (multi-fichiers)" if args.hard else ""))
    print(f"  Problèmes trouvés ET corrigés correctement{extra}.")
else:
    if not tools:
        print("  ⚠️ Aucun outil appelé → capacité / format tool-calling du modèle.")
    if edit_fail:
        print(f"  ⚠️ {edit_fail} édition(s) rejetée(s) → ne reproduit pas le code exact.")
    if (args.hard or args.security or args.brutal) and tools.get("read_file", 0) < 2:
        print("  ⚠️ Peu de lecture → n'a pas exploré tous les fichiers.")
    if (tools.get("edit_file", 0) + tools.get("write_file", 0)) and not edit_fail:
        print("  ⚠️ A édité mais résultat incorrect → raisonnement (corrections partielles/erronées).")
    if args.security or args.brutal:
        print("  ⚠️ Sécurité : une faille subsiste (souvent une SUBTILE : porte dérobée, pickle, "
              "mass-assignment, sel statique) ou une fonction cassée (sur-correction).")
    if nturns >= turns:
        print("  ⚠️ Budget de tours atteint → pas de convergence / boucle.")

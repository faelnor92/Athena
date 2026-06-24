#!/usr/bin/env python3
"""Diagnostic du ROUTAGE D'OUTILS — répond en 2 s : l'outil existe-t-il ? l'embedder est-il bon ?
la requête expose-t-elle bien get_driving_route ? À lancer sur le serveur Athena :

    python3 scripts/diag_tools.py
    python3 scripts/diag_tools.py "temps en voiture entre strasbourg et paris"
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Re-exécute avec le PYTHON DU VENV du projet si on tourne sur le python système (sinon
# ModuleNotFoundError: litellm). Athena s'exécute dans un venv qui a les dépendances.
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

from core.swarm.engine import AVAILABLE_TOOLS  # noqa: E402
import core.tool_router as tr                  # noqa: E402

WATCH = ["get_driving_route", "get_traffic_incidents", "get_weather"]

print("═══ 1) Les outils sont-ils CHARGÉS (code à jour + restart) ? ═══")
for name in WATCH:
    print(f"   {'✅' if name in AVAILABLE_TOOLS else '❌ MANQUANT'}  {name}")
missing = [n for n in WATCH if n not in AVAILABLE_TOOLS]
if missing:
    print("\n⚠️ Des outils MANQUENT → le serveur ne tourne pas le dernier code.\n"
          "   Fais `git pull` (ou update.sh) PUIS redémarre le service Athena, puis relance ce diag.")

print("\n═══ 2) Quel EMBEDDER pour le routage sémantique ? ═══")
ef = tr._get_embedder()
ef_name = type(ef).__name__ if ef is not None else "AUCUN"
print(f"   embedder = {ef_name}")
if ef is None:
    print("   ⚠️ Aucun embedder → routage en mode MOTS-CLÉS uniquement (médiocre pour les paraphrases FR).")
elif "Default" in ef_name or "MiniLM" in ef_name:
    print("   ⚠️ all-MiniLM (repli local, anglo-centré) → mauvais en français. Configure bge-m3 :")
    print("      Réglages → Mémoire → Moteur = Endpoint, EMBEDDING_MODEL=bge-m3, EMBEDDING_API_BASE joignable.")
else:
    print("   ✅ Embedder dédié (probablement bge-m3 via endpoint) — idéal.")

print("\n═══ 3) Pour ta requête, get_driving_route est-il EXPOSÉ ? ═══")
queries = sys.argv[1:] or [
    "donne moi le temps en voiture entre strasbourg et paris",
    "combien de temps entre preuschdorf et strasbourg",
    "des bouchons sur l'A4 ?",
]
funcs = list(AVAILABLE_TOOLS.values())
for q in queries:
    try:
        sel = tr.select_tools(q, funcs)
    except Exception as e:  # noqa: BLE001
        print(f"   {q!r} → ERREUR routeur: {e}")
        continue
    expo = "get_driving_route" in sel
    transp = sorted(n for n in sel if n in WATCH)
    print(f"   {'✅' if expo else '❌'} {q!r}")
    print(f"       transport exposés: {transp or '— AUCUN —'}")

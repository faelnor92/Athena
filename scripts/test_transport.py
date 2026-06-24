#!/usr/bin/env python3
"""Teste les outils TRANSPORT (Navitia/Transitland) avec la config d'Athena, et affiche le résultat
BRUT — pour voir l'erreur réelle (clé absente / 401 / arrêt non résolu / hors couverture). Usage :

    python3 scripts/test_transport.py
    python3 scripts/test_transport.py "Haguenau" "Strasbourg"
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Bascule sur le python du venv si besoin (dépendances), comme diag_tools.
for _cand in (".venv/bin/python", "venv/bin/python", ".venv/bin/python3", "venv/bin/python3"):
    _vp = os.path.join(ROOT, _cand)
    if os.path.exists(_vp) and os.path.realpath(_vp) != os.path.realpath(sys.executable):
        os.execv(_vp, [_vp, os.path.abspath(__file__)] + sys.argv[1:])
# Charge le .env (clés saisies dans l'UI).
_env = os.path.join(ROOT, ".env")
if os.path.exists(_env):
    for _l in open(_env, encoding="utf-8"):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from tools import transport_tools as t  # noqa: E402


def _mask(v):
    v = (v or "").strip()
    return (f"{v[:4]}…{v[-4:]}" if len(v) > 8 else ("***" if v else "—"))


origin = sys.argv[1] if len(sys.argv) > 1 else "Haguenau"
dest = sys.argv[2] if len(sys.argv) > 2 else "Strasbourg"

print("═══ Configuration transport ═══")
print(f"   TRANSPORT_PROVIDER = {t._cfg('TRANSPORT_PROVIDER') or '(auto)'}  → provider actif : {t._provider()}")
print(f"   NAVITIA_API_KEY    = {_mask(t._cfg('NAVITIA_API_KEY') or t._cfg('NAVITIA_KEY'))}")
print(f"   NAVITIA_API_BASE   = {t._cfg('NAVITIA_API_BASE') or 'https://api.navitia.io/v1 (défaut)'}")
print(f"   TRANSITLAND_API_KEY= {_mask(t._cfg('TRANSITLAND_API_KEY'))}")

print(f"\n═══ ① Prochains départs à « {origin} » ═══")
print(t.get_next_departures(origin))

print(f"\n═══ ② Itinéraire {origin} → {dest} ═══")
print(t.get_journey(origin, dest))

print(f"\n═══ ③ Perturbations « {dest} » ═══")
print(t.get_disruptions(dest))

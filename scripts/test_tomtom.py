#!/usr/bin/env python3
"""Teste la clé TomTom ENREGISTRÉE DANS ATHENA, de bout en bout, via le MÊME code que l'assistant
(tools.traffic_tools). À lancer sur le serveur où Athena est configurée :

    python3 scripts/test_tomtom.py
    python3 scripts/test_tomtom.py "Preuschdorf" "Strasbourg"

Lit la clé comme le fait l'outil : config par-utilisateur puis .env (TOMTOM_API_KEY). Distingue
clairement « clé absente », « clé refusée (403) » et « ça marche ».
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Charge le .env (comme le serveur) → la clé saisie dans l'UI (Réglages → Intégrations externes,
# écrite dans .env) devient visible via os.getenv. Parsing inline = pas d'effet de bord lourd.
_env_path = os.path.join(ROOT, ".env")
if os.path.exists(_env_path):
    for _line in open(_env_path, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from tools import traffic_tools as t  # noqa: E402

origin = sys.argv[1] if len(sys.argv) > 1 else "Strasbourg"
dest = sys.argv[2] if len(sys.argv) > 2 else "Paris"


def main() -> int:
    key = t._key()
    if not key:
        print("❌ Aucune clé TomTom trouvée (TOMTOM_API_KEY) dans la config d'Athena.\n"
              "   → Réglages → Comportement → Intégrations externes → Clé TomTom, puis Enregistrer.\n"
              "   (ou ajoute TOMTOM_API_KEY=... dans le .env)")
        return 1
    masked = f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "***"
    print(f"🔑 Clé TomTom détectée : {masked} ({len(key)} caractères)\n")

    # 1) Géocodage seul (isole la validité de la clé / l'API Search).
    print(f"① Géocodage de « {dest} »…")
    g = t._geocode(dest, key)
    if not g:
        print("   ❌ Échec — clé probablement INVALIDE/refusée (403) ou produit Search non activé.\n"
              "      Vérifie la clé sur developer.tomtom.com.")
        return 2
    print(f"   ✅ OK → {g[2]}  ({g[0]:.4f}, {g[1]:.4f})\n")

    # 2) Itinéraire voiture avec trafic (Routing API).
    print(f"② Trajet voiture {origin} → {dest} (trafic temps réel)…")
    route = t.get_driving_route(origin, dest)
    print("   " + route.replace("\n", "\n   ") + "\n")

    # 3) Incidents routiers (Traffic API).
    print(f"③ Incidents routiers autour de « {dest} »…")
    inc = t.get_traffic_incidents(dest)
    print("   " + inc.replace("\n", "\n   ") + "\n")

    ok = ("🚗" in route and "introuvable" not in route and "refusée" not in route
          and "Aucune clé" not in route)
    print("───────────────────────────────")
    print("✅ TomTom fonctionne." if ok else "⚠️ TomTom n'a pas renvoyé d'itinéraire — voir les messages ci-dessus.")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())

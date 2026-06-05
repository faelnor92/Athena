#!/usr/bin/env python3
"""Migration UNIQUE : déplace les projets de l'ancien emplacement
`workspace/projects/<user>/…` vers `athena_projects/<user>/…` (hors workspace de base)
et met à jour les chemins en config. Idempotent — relançable sans risque.

Usage (depuis la racine du repo, MÊME environnement que le serveur) :
    python scripts/migrate_projects.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import projects  # noqa: E402

res = projects.migrate_legacy_projects()
print(f"Projets déplacés : {len(res['moved'])}")
for src, dst in res["moved"]:
    print(f"  {src}\n   → {dst}")
if res["errors"]:
    print("Erreurs :")
    for e in res["errors"]:
        print("  -", e)
print("Terminé." if not res["errors"] else "Terminé avec des erreurs.")

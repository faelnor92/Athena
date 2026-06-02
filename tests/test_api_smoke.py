"""Filet de sécurité du refactor en APIRouter : garantit qu'AUCUNE route /api n'est
perdue, renommée ou voit sa méthode changer pendant le découpage de server.py.

La référence (api_routes_baseline.json) a été figée AVANT le refactor. Si tu ajoutes
volontairement une route, régénère la baseline (voir le bas du fichier).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

_BASELINE = os.path.join(os.path.dirname(__file__), "api_routes_baseline.json")


def _current_routes():
    return sorted(
        f"{sorted(r.methods)[0]} {r.path}"
        for r in server.app.routes
        if hasattr(r, "methods") and r.methods and str(r.path).startswith("/api/")
    )


def test_routes_unchanged():
    baseline = set(json.load(open(_BASELINE, encoding="utf-8")))
    current = set(_current_routes())
    missing = baseline - current
    added = current - baseline
    assert not missing, f"Routes PERDUES par le refactor : {sorted(missing)}"
    # Des ajouts volontaires sont tolérés mais signalés.
    if added:
        print(f"[info] routes ajoutées depuis la baseline : {sorted(added)}")
    print(f"OK : {len(current)} routes /api (aucune perdue).")


def test_app_boots_and_key_endpoints():
    from fastapi.testclient import TestClient
    with TestClient(server.app) as client:
        # En test (ni ADMIN_PASSWORD ni users), l'auth est inactive → endpoints ouverts.
        assert client.get("/api/platform").status_code == 200
        assert client.get("/api/me").status_code == 200
        r = client.post("/api/login", json={"password": ""})
        assert r.status_code in (200, 401)
    print("OK : app démarre, endpoints clés répondent.")


if __name__ == "__main__":
    test_routes_unchanged()
    test_app_boots_and_key_endpoints()
    print("\n✅ Smoke API OK")
    # Pour régénérer la baseline après un ajout VOLONTAIRE de route :
    #   python3 -c "import json,server; json.dump(sorted(f'{sorted(r.methods)[0]} {r.path}' \
    #     for r in server.app.routes if getattr(r,'methods',None) and str(r.path).startswith('/api/')), \
    #     open('tests/api_routes_baseline.json','w'), indent=1)"

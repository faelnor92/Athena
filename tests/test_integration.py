"""Tests d'INTÉGRATION HTTP (TestClient) : flux réels auth → endpoint → réponse.

Couvre ce que le smoke (présence des routes) ne teste pas : en-têtes de sécurité,
exigence d'authentification, login, RBAC admin/user, déconnexion qui invalide le jeton,
politique de mot de passe. Environnement totalement isolé (bases temporaires, auth active
via ADMIN_PASSWORD) pour ne rien toucher au dépôt.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Isolation TOTALE avant d'importer le serveur (config lue à l'import) ----
_tmp = tempfile.mkdtemp(prefix="athena_it_")
os.environ.update({
    "HOST": "127.0.0.1",                       # évite le garde-fou réseau
    "MIN_PASSWORD_LENGTH": "8",
    "RATE_LIMIT_PER_MIN": "100000",            # neutralise le rate-limit dans les tests
    "STATE_DB_PATH": os.path.join(_tmp, "state.sqlite3"),
    "RUNS_DB_PATH": os.path.join(_tmp, "runs.sqlite3"),
    "CONVERSATIONS_DB_PATH": os.path.join(_tmp, "conv.sqlite3"),
    "CHROMA_DB_PATH": os.path.join(_tmp, "chroma"),
    "CORE_MEMORY_PATH": os.path.join(_tmp, "core_memory.json"),
    "ROUTINES_PATH": os.path.join(_tmp, "routines.json"),   # inexistant → pas de migration du dépôt
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402

client = TestClient(server.app)
_ADMIN = "admin-secret-itest"


# ADMIN_PASSWORD active l'authentification. On le pose PAR TEST (et non au niveau module)
# pour ne pas contaminer les autres fichiers via os.environ pendant la collecte pytest :
# sinon test_api_smoke verrait l'auth active et recevrait 401 au lieu de 200.
# (auth.py relit ADMIN_PASSWORD dynamiquement à chaque requête → une fixture suffit.)
@pytest.fixture(autouse=True)
def _auth_active(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", _ADMIN)


def _admin_token():
    r = client.post("/api/login", json={"password": _ADMIN})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_security_headers_present():
    r = client.get("/")
    assert r.status_code == 200
    # SAMEORIGIN (et non DENY) : Athena embarque ses propres pages (AthenaDesign Studio)
    # mais reste protégée du framing externe (anti-clickjacking).
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in r.headers
    assert "frame-ancestors 'self'" in r.headers.get("content-security-policy", "")


def test_auth_required_without_token():
    r = client.get("/api/me")
    assert r.status_code == 401


def test_login_wrong_password():
    r = client.post("/api/login", json={"password": "mauvais"})
    assert r.status_code == 401


def test_login_admin_and_me():
    tok = _admin_token()
    me = client.get("/api/me", headers=_h(tok))
    assert me.status_code == 200 and me.json().get("role") == "admin"


def test_rbac_user_forbidden_on_admin_endpoint():
    admin = _admin_token()
    # création d'un compte « user »
    cr = client.post("/api/users", headers=_h(admin),
                     json={"username": "itest_user", "password": "userpass8", "role": "user"})
    assert cr.status_code == 200, cr.text
    # connexion en tant que user
    lr = client.post("/api/login", json={"username": "itest_user", "password": "userpass8"})
    assert lr.status_code == 200, lr.text
    utok = lr.json()["token"]
    assert lr.json()["role"] == "user"
    # un user ne voit pas la liste des comptes (admin-only) → 403
    assert client.get("/api/users", headers=_h(utok)).status_code == 403
    # mais accède à son propre /api/me
    assert client.get("/api/me", headers=_h(utok)).json().get("role") == "user"


def test_logout_invalidates_token():
    tok = _admin_token()
    assert client.get("/api/me", headers=_h(tok)).status_code == 200
    assert client.post("/api/logout", headers=_h(tok)).status_code == 200
    assert client.get("/api/me", headers=_h(tok)).status_code == 401, "le jeton doit être invalide après logout"


def test_password_policy_enforced():
    admin = _admin_token()
    r = client.post("/api/users", headers=_h(admin),
                    json={"username": "shorty", "password": "abc", "role": "user"})
    assert r.status_code == 400, "mot de passe trop court doit être refusé"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print("\n" + ("Tous les tests d'intégration passent." if not failures else f"{failures} échec(s)."))
    sys.exit(1 if failures else 0)

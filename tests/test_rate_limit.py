"""Rate-limiting : module core/throttle + brute-force /api/register + throttle LLM."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DB_PATH", tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name)


def test_throttle_fenetre_glissante():
    from core import throttle
    ns, key = "t_test", "1.2.3.4"
    throttle.clear(ns, key)
    assert not throttle.too_many(ns, key, max_events=2, window=300)
    throttle.record(ns, key, window=300)
    throttle.record(ns, key, window=300)
    assert throttle.too_many(ns, key, max_events=2, window=300)
    # max_events=0 → désactivé, jamais bloquant.
    assert not throttle.too_many(ns, key, max_events=0, window=300)
    throttle.clear(ns, key)
    assert not throttle.too_many(ns, key, max_events=2, window=300)


def test_throttle_allow_consomme():
    from core import throttle
    ns, key = "t_allow", "user1"
    throttle.clear(ns, key)
    assert throttle.allow(ns, key, max_events=3, window=60)
    assert throttle.allow(ns, key, max_events=3, window=60)
    assert throttle.allow(ns, key, max_events=3, window=60)
    assert not throttle.allow(ns, key, max_events=3, window=60), "la 4e requête doit être refusée"
    # 0/négatif = illimité.
    assert throttle.allow(ns, key, max_events=0, window=60)
    throttle.clear(ns, key)


def test_register_brute_force_bloque():
    """Après N codes d'invitation invalides, /api/register renvoie 429 (plus de 403)."""
    from fastapi.testclient import TestClient
    import server
    client = TestClient(server.app)
    from core import throttle
    payload = {"code": "code-bidon", "username": "attaquant", "password": "longmotdepasse"}
    max_fails = int(os.getenv("LOGIN_MAX_FAILS", "8") or 8)
    throttle.clear("register_fail", "testclient")
    try:
        for _ in range(max_fails):
            r = client.post("/api/register", json=payload)
            assert r.status_code == 403, r.text  # code invalide
        r = client.post("/api/register", json=payload)
        assert r.status_code == 429, f"attendu 429 après {max_fails} échecs, obtenu {r.status_code}"
    finally:
        throttle.clear("register_fail", "testclient")


def test_llm_throttle_429_apres_limite():
    """Le middleware limite les POST /api/chat* par identité (compte sinon IP)."""
    from fastapi.testclient import TestClient
    import server
    from core import throttle
    client = TestClient(server.app)
    old = os.environ.get("LLM_RATE_LIMIT_PER_MIN")
    os.environ["LLM_RATE_LIMIT_PER_MIN"] = "2"
    throttle.clear("llm", "testclient")
    try:
        codes = [client.post("/api/chat/undo", json={}).status_code for _ in range(3)]
        # Les 2 premières passent le throttle (quel que soit leur code métier), la 3e = 429.
        assert codes[2] == 429, codes
        assert all(c != 429 for c in codes[:2]), codes
    finally:
        if old is None:
            os.environ.pop("LLM_RATE_LIMIT_PER_MIN", None)
        else:
            os.environ["LLM_RATE_LIMIT_PER_MIN"] = old
        throttle.clear("llm", "testclient")


if __name__ == "__main__":
    test_throttle_fenetre_glissante()
    test_throttle_allow_consomme()
    test_register_brute_force_bloque()
    test_llm_throttle_429_apres_limite()
    print("Tous les tests de rate-limiting passent.")

"""Sécurité de l'authentification : révocation de sessions, purge, throttle partagé.

- Un changement/reset de mot de passe doit révoquer les sessions du compte (un token
  volé cesse d'être valide) — la session courante peut être conservée (keep_token).
- Les sessions expirées sont purgeables.
- Le throttle anti-brute-force est partagé (store SQLite) → effectif en multi-worker.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name
# La garde réseau de routers.auth s'exécute à l'import ; en test isolé (sans .env), on
# autorise explicitement pour pouvoir importer le module.
os.environ["ALLOW_INSECURE_NETWORK"] = "true"


def test_revoke_user_keeps_current_session():
    from core.state import ACTIVE_SESSIONS
    exp = time.time() + 1000
    ACTIVE_SESSIONS["tokA"] = {"username": "alice", "role": "user", "exp": exp}
    ACTIVE_SESSIONS["tokB"] = {"username": "alice", "role": "user", "exp": exp}
    ACTIVE_SESSIONS["tokC"] = {"username": "bob", "role": "user", "exp": exp}
    removed = ACTIVE_SESSIONS.revoke_user("alice", keep_token="tokA")
    assert removed == 1
    assert ACTIVE_SESSIONS.get("tokA") is not None, "la session courante doit être conservée"
    assert ACTIVE_SESSIONS.get("tokB") is None, "les autres sessions d'alice doivent être révoquées"
    assert ACTIVE_SESSIONS.get("tokC") is not None, "les sessions des autres comptes ne bougent pas"


def test_purge_expired_sessions():
    from core.state import ACTIVE_SESSIONS
    ACTIVE_SESSIONS["live"] = {"username": "z", "role": "user", "exp": time.time() + 1000}
    ACTIVE_SESSIONS["dead"] = {"username": "z", "role": "user", "exp": time.time() - 10}
    ACTIVE_SESSIONS.purge_expired()
    assert ACTIVE_SESSIONS.get("live") is not None
    assert ACTIVE_SESSIONS.get("dead") is None


def test_login_throttle_is_shared():
    import routers.auth as a
    ip = "203.0.113.7"
    a._clear_login_fails(ip)
    for _ in range(a._LOGIN_MAX_FAILS):
        a._record_login_fail(ip)
    assert len(a._recent_fails(ip)) >= a._LOGIN_MAX_FAILS, "les échecs doivent être comptés (et partagés via le store)"
    a._clear_login_fails(ip)
    assert a._recent_fails(ip) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de sécurité auth passent.")

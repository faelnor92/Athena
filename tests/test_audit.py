"""Journal d'audit : écriture append-only, ordre récent, filtre, redaction des secrets."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["STATE_DB_PATH"] = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name


def test_audit_log_and_recent_order():
    from core import audit
    audit.log("login", actor="alice", role="user", ip="10.0.0.1")
    audit.log("login_failed", actor="bob", ip="10.0.0.2")
    audit.log("password_change", actor="alice", ip="10.0.0.1")
    ev = audit.recent(limit=10)
    assert [e["action"] for e in ev[:3]] == ["password_change", "login_failed", "login"], "ordre anti-chronologique attendu"
    assert ev[0]["actor"] == "alice"


def test_audit_action_filter():
    from core import audit
    audit.log("login_failed", actor="carol", ip="10.0.0.9")  # auto-suffisant (indépendant de l'ordre)
    fails = audit.recent(action="login_failed")
    assert fails and all(e["action"] == "login_failed" for e in fails)


def test_audit_redacts_secrets():
    from core import audit
    audit.log("test_secret", actor="x", detail="token sk-ABCDEF1234567890ABCDEF more")
    ev = audit.recent(action="test_secret")
    assert ev, "événement enregistré"
    assert "sk-ABCDEF1234567890ABCDEF" not in ev[0]["detail"], "le secret doit être masqué"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests d'audit passent.")

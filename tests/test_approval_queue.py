"""Tests : file d'approbations HITL asynchrones.

Exécution : python3 tests/test_approval_queue.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import approval_queue as aq


def test_approve_deny_timeout():
    aid = aq.request("execute_bash_command", {"command": "reboot"}, "Codeur", "telegram:123")
    assert any(p["id"] == aid for p in aq.pending_list())

    def approver():
        time.sleep(0.1)
        assert aq.resolve(aid, True)
    threading.Thread(target=approver).start()
    assert aq.wait(aid, timeout=2) == "approved"
    assert not any(p["id"] == aid for p in aq.pending_list()), "résolu → retiré de la file"

    aid2 = aq.request("x", {}, "A", "telegram:1")
    aq.resolve(aid2, False)
    assert aq.wait(aid2, timeout=1) == "denied"

    aid3 = aq.request("y", {}, "A", "telegram:1")
    assert aq.wait(aid3, timeout=0.2) == "timeout", "sans décision → timeout (refus sûr)"
    print("OK: approve / deny / timeout")


def test_channel_gating():
    os.environ.pop("APPROVAL_ASYNC", None)
    os.environ.pop("APPROVAL_ASYNC_ALL", None)
    assert aq.async_enabled("telegram:5") is True
    assert aq.async_enabled("web") is False, "le web reste in-band (l'utilisateur voit le chat)"
    assert aq.async_enabled("voice:papa") is False, "la voix est in-band (utilisateur présent)"
    os.environ["APPROVAL_ASYNC"] = "false"
    assert aq.async_enabled("telegram:5") is False, "désactivable globalement"
    os.environ.pop("APPROVAL_ASYNC", None)
    print("OK: gating par canal")


def test_resolve_unknown():
    assert aq.resolve("ZZZZZZ", True) is False
    print("OK: id inconnu refusé proprement")


if __name__ == "__main__":
    test_approve_deny_timeout()
    test_channel_gating()
    test_resolve_unknown()
    print("\n✅ test_approval_queue OK")

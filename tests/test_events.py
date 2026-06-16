"""Tests : bus d'événements (Vigie) — filtrage, dedup, worker, config.

Exécution : python3 tests/test_events.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.events as ev


def test_filter_dedup_worker():
    got = []
    ev.start_worker(lambda rec: got.append(rec["message"]))
    ev.set_config({"enabled": True, "min_severity": "warning", "dedup_window": 60})

    assert ev.submit({"type": "x", "severity": "warning", "message": "a"})["status"] == "queued"
    assert ev.submit({"type": "x", "severity": "info", "message": "b"})["status"] == "filtered"
    assert ev.submit({"type": "x", "severity": "warning", "message": "a"})["status"] == "deduped"
    assert ev.submit({"type": "y", "severity": "critical", "message": "c"})["status"] == "queued"
    time.sleep(0.5)
    assert got == ["a", "c"], f"le worker doit traiter a puis c, eu : {got}"
    print("OK: filtre sévérité + dedup + worker")


def test_disabled_and_config():
    ev.set_config({"enabled": False})
    assert ev.submit({"type": "z", "severity": "critical", "message": "d"})["status"] == "disabled"
    c = ev.set_config({"enabled": True, "min_severity": "critical"})
    assert c["enabled"] is True and c["min_severity"] == "critical"
    # un warning est maintenant sous le seuil
    assert ev.submit({"type": "w", "severity": "warning", "message": "e"})["status"] == "filtered"
    ev.set_config({"enabled": False})
    print("OK: activation/désactivation + seuil configurable")


if __name__ == "__main__":
    test_filter_dedup_worker()
    test_disabled_and_config()
    print("\n✅ test_events OK")

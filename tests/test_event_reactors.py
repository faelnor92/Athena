"""Producteurs branchés sur le bus d'événements : Vigie (events.submit → 'vigie.event') et
objectifs (update_goal_status('done') → 'goal.completed'). Les réacteurs (audit, notifications)
sont enregistrés côté serveur ; ici on vérifie l'ÉMISSION."""
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import event_bus  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_bus():
    event_bus.reset()
    yield
    event_bus.reset()
    # events.submit alimente une file MODULE globale (events._q) + un cache de dédup : on les
    # vide pour ne pas polluer test_events (worker Vigie) qui s'exécute ensuite.
    try:
        from core import events
        while not events._q.empty():
            events._q.get_nowait()
        events._dedup.clear()
    except Exception:
        pass


def test_events_submit_publie_vigie_event():
    from core import events
    # Neutralise le callback du worker Vigie : en suite complète, l'import de `server` l'a
    # démarré avec _run_vigie (→ swarm.run/réseau). Ici on teste la PUBLICATION sur le bus,
    # pas l'agent Vigie — on évite donc de déclencher un vrai run (qui bloquerait le worker).
    events.start_worker(lambda rec: None)
    events.set_config({"enabled": True, "min_severity": "info", "dedup_window": 0})
    got = threading.Event()
    cap = {}
    event_bus.subscribe("vigie.event", lambda t, p: (cap.update(p), got.set()))
    r = events.submit({"type": "unit_test", "source": "u", "severity": "critical", "message": "boom"})
    assert r["status"] == "queued"
    assert got.wait(timeout=3), "vigie.event non publié sur le bus"
    assert cap["type"] == "unit_test" and cap["severity"] == "critical"


def test_goal_done_publie_goal_completed():
    from core import goals
    from tools import goal_tools
    g = goals.create("Livrer la v1", detail="MVP")
    cap = []
    event_bus.subscribe("goal.completed", lambda t, p: cap.append(p))
    # Un changement de statut NON terminal ne publie pas.
    goal_tools.update_goal_status(g["id"], "paused")
    assert cap == []
    # « done » → publication avec id + titre.
    out = goal_tools.update_goal_status(g["id"], "done")
    assert "ATTEINT" in out
    assert cap and cap[0]["id"] == g["id"] and cap[0]["title"] == "Livrer la v1"

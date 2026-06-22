"""Bus d'événements pub/sub (#4b) + intégration HITL (approbations async → bus → audit)."""
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


def test_publish_livre_aux_abonnes_du_sujet_et_du_joker():
    got = []
    event_bus.subscribe("topicA", lambda t, p: got.append(("A", p["v"])))
    event_bus.subscribe("*", lambda t, p: got.append(("*", t)))
    n = event_bus.publish("topicA", {"v": 1})
    assert n == 2
    assert ("A", 1) in got and ("*", "topicA") in got
    # Un autre sujet ne touche que le joker.
    event_bus.publish("topicB", {"v": 2})
    assert ("*", "topicB") in got and all(g[0] != "A" or g[1] != 2 for g in got)


def test_unsubscribe():
    seen = []
    tok = event_bus.subscribe("x", lambda t, p: seen.append(p))
    assert event_bus.unsubscribe(tok) is True
    event_bus.publish("x", {"k": 1})
    assert seen == []


def test_erreur_d_un_abonne_n_empeche_pas_les_autres():
    seen = []
    event_bus.subscribe("x", lambda t, p: (_ for _ in ()).throw(RuntimeError("boom")))
    event_bus.subscribe("x", lambda t, p: seen.append("ok"))
    event_bus.publish("x", {})       # ne lève pas
    assert seen == ["ok"]


def test_subscriber_count():
    event_bus.subscribe("x", lambda t, p: None)
    event_bus.subscribe("*", lambda t, p: None)
    assert event_bus.subscriber_count("x") == 2   # x + joker
    assert event_bus.subscriber_count("y") == 1   # joker seul


def test_publish_async():
    done = threading.Event()
    out = {}
    event_bus.subscribe("z", lambda t, p: (out.update(p), done.set()))
    event_bus.publish("z", {"v": 42}, async_=True)
    assert done.wait(timeout=3), "l'abonné async n'a pas été appelé"
    assert out["v"] == 42


# --- Intégration HITL : approval_queue publie son cycle de vie sur le bus -----
def test_approval_queue_publie_sur_le_bus():
    from core import approval_queue as aq
    events = []
    event_bus.subscribe("approval", lambda t, p: events.append(p))

    aid = aq.request("execute_bash_command", {"cmd": "ls"}, agent="Codeur", channel="telegram:1")
    aq.resolve(aid, approved=True)

    phases = [e["phase"] for e in events]
    assert "requested" in phases and "resolved" in phases
    req = next(e for e in events if e["phase"] == "requested")
    assert req["tool"] == "execute_bash_command" and req["agent"] == "Codeur"
    res = next(e for e in events if e["phase"] == "resolved")
    assert res["approved"] is True


def test_approval_timeout_publie_timeout():
    from core import approval_queue as aq
    events = []
    event_bus.subscribe("approval", lambda t, p: events.append(p["phase"]))
    aid = aq.request("execute_bash_command", {}, agent="Codeur", channel="telegram:1")
    assert aq.wait(aid, timeout=0.05) == "timeout"
    assert "timeout" in events

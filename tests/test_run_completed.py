"""Événement run.completed : publication par RunRegistry.finish + gating du réacteur
de notification (routines/API/déconnecté/vocal long = notifiés ; chat direct = jamais)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DB_PATH", tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False).name)


def _collect_events():
    from core import event_bus
    seen = []
    tok = event_bus.subscribe("run.completed", lambda t, p: seen.append(p))
    return seen, tok


def test_finish_publie_run_completed_une_seule_fois():
    from core import event_bus, channels
    from core.run_context import RunRegistry
    reg = RunRegistry()
    seen, tok = _collect_events()
    try:
        reg.start("r1")
        reg.set_result("r1", {"agent": "Athena", "response": "voilà"})
        chan_tok = channels.current_channel.set("routine")
        try:
            reg.finish("r1")
            reg.finish("r1")  # idempotent : pas de double événement
        finally:
            channels.current_channel.reset(chan_tok)
        assert len(seen) == 1, seen
        p = seen[0]
        assert p["run_id"] == "r1" and p["agent"] == "Athena"
        assert p["channel"] == "routine" and p["response"] == "voilà"
        assert p["cancelled"] is False and p["detached"] is False
        assert isinstance(p["duration_s"], float)
    finally:
        event_bus.unsubscribe(tok)


def test_mark_detached_remonte_dans_l_evenement():
    from core import event_bus
    from core.run_context import RunRegistry
    reg = RunRegistry()
    seen, tok = _collect_events()
    try:
        reg.start("r2")
        reg.mark_detached("r2")
        reg.finish("r2")
        assert len(seen) == 1 and seen[0]["detached"] is True
    finally:
        event_bus.unsubscribe(tok)


def test_reacteur_notifie_les_bons_canaux(monkeypatch):
    from core import notifications
    sent = []
    monkeypatch.setattr(notifications, "notify", lambda msg, **kw: sent.append(msg))
    monkeypatch.setenv("RUN_COMPLETED_NOTIFY", "true")

    def fire(**p):
        sent.clear()
        base = {"run_id": "x", "agent": "A", "response": "ok", "error": None,
                "cancelled": False, "detached": False, "duration_s": 3.0,
                "channel": "web", "user": None}
        base.update(p)
        notifications.run_completed_reactor("run.completed", base)
        return bool(sent)

    # Notifiés : routines, API, webhooks/événements, pipelines, client web déconnecté.
    assert fire(channel="routine")
    assert fire(channel="api")
    assert fire(channel="events")
    assert fire(channel="pipeline")
    assert fire(channel="web", detached=True)
    # Vocal : seulement au-delà du seuil de durée.
    assert not fire(channel="voice", duration_s=5.0)
    assert fire(channel="voice", duration_s=500.0)
    # Jamais : chat direct (web/telegram), run annulé.
    assert not fire(channel="web")
    assert not fire(channel="telegram:123")
    assert not fire(channel="routine", cancelled=True)
    # Kill-switch global.
    monkeypatch.setenv("RUN_COMPLETED_NOTIFY", "false")
    assert not fire(channel="routine")


if __name__ == "__main__":
    test_finish_publie_run_completed_une_seule_fois()
    test_mark_detached_remonte_dans_l_evenement()
    print("Tests run.completed OK (lancer via pytest pour le test monkeypatch).")

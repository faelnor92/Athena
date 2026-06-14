"""Non-régression : (1) le MCPManager expose les erreurs de connexion par serveur (UI),
(2) la suppression d'un événement Google utilise l'id COMPLET (external_id), pas le handle
tronqué — sinon l'API Google renvoie 404."""
import os
import sys
import json
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.mcp_manager import MCPManager      # noqa: E402
import tools.agenda_sync as asy               # noqa: E402
import tools.agenda_tools as at               # noqa: E402


def test_mcp_status_surfaces_connection_error():
    # Commande inexistante → échec de connexion, mais l'erreur doit être CAPTURÉE (pas swallowed).
    cfg = {"mcpServers": {"bidon": {"command": "commande_inexistante_xyz_123",
                                    "args": [], "env": {}, "timeout": 6}}}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(cfg, f); f.close()
    try:
        m = MCPManager(f.name)
        m.start()
        st = m.status()
        assert "bidon" in st["configured_servers"]
        assert "bidon" not in st["connected_servers"]
        assert st["errors"].get("bidon"), "l'erreur de connexion doit être exposée pour l'UI"
        m.stop()
    finally:
        os.remove(f.name)


def test_agenda_delete_google_uses_external_id():
    # Agenda local contenant un événement Google avec id tronqué + external_id complet.
    full_id = "abcdef0123456789FULLGOOGLEID9999"
    short_id = full_id[:16]
    os.makedirs("workspace", exist_ok=True)
    path = at.agenda_file()  # workspace/agenda_local.json (mode sans auth)
    backup = None
    if os.path.exists(path):
        backup = open(path, encoding="utf-8").read()
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([{"id": short_id, "external_id": full_id, "title": "RDV",
                        "datetime": "2026-06-20 10:00", "duration_minutes": 30,
                        "description": "", "source": "google"}], fh)
        captured = {}

        def _fake_delete(event_id):
            captured["id"] = event_id
            return True

        with mock.patch.object(asy, "delete_google_calendar_event", _fake_delete), \
             mock.patch.object(at, "sync_all_external_calendars", lambda: 0):
            out = at.delete_calendar_event(short_id)   # l'agent passe le HANDLE court
        # L'appel Google doit recevoir l'id COMPLET, pas le tronqué.
        assert captured.get("id") == full_id, captured
        assert "supprimé" in out.lower()
    finally:
        if backup is not None:
            open(path, "w", encoding="utf-8").write(backup)
        elif os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests mcp/agenda passent.")

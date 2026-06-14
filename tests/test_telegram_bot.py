"""Bot Telegram entrant : routage des messages, pairing, commandes — réseau et essaim mockés."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.telegram_bot as tg          # noqa: E402
import core.telegram_pairing as pair    # noqa: E402


def _msg(chat_id, text):
    return {"chat": {"id": chat_id}, "text": text}


def test_disabled_without_token():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        assert tg.is_enabled() is False
        assert tg.status()["enabled"] is False


def test_unknown_chat_gets_pairing_code():
    sent = []
    with mock.patch.object(tg, "send_message", lambda cid, txt: sent.append((str(cid), txt))), \
         mock.patch.object(pair, "is_allowed", return_value=False), \
         mock.patch.object(pair, "maybe_bootstrap", return_value=False), \
         mock.patch.object(pair, "required", return_value=True), \
         mock.patch.object(pair, "request_pairing", return_value="ABC123"), \
         mock.patch.object(pair, "allowed_chats", return_value=[]), \
         mock.patch.object(tg, "_respond") as resp:
        tg._handle_message(_msg(999, "bonjour"))
        # Un code est envoyé, l'essaim N'est PAS lancé pour un inconnu.
        assert any("ABC123" in t for _, t in sent), sent
        resp.assert_not_called()


def test_allowed_chat_runs_swarm():
    sent = []
    with mock.patch.object(tg, "send_message", lambda cid, txt: sent.append((str(cid), txt))), \
         mock.patch.object(pair, "is_allowed", return_value=True), \
         mock.patch.object(tg, "_respond", return_value="réponse d'Athena") as resp:
        tg._handle_message(_msg(42, "quelle heure est-il ?"))
        resp.assert_called_once()
        assert any("réponse d'Athena" in t for _, t in sent), sent


def test_reset_clears_history():
    sent = []
    tg._HISTORY["7"] = [{"role": "user", "content": "x"}]
    with mock.patch.object(tg, "send_message", lambda cid, txt: sent.append((str(cid), txt))):
        tg._handle_message(_msg(7, "/reset"))
    assert "7" not in tg._HISTORY
    assert any("oublié" in t.lower() for _, t in sent), sent


def test_approve_requires_authorized_chat():
    sent = []
    with mock.patch.object(tg, "send_message", lambda cid, txt: sent.append((str(cid), txt))), \
         mock.patch.object(pair, "is_allowed", return_value=False):
        tg._handle_message(_msg(13, "/approve ABC123"))
    assert any("réservé" in t.lower() or "⛔" in t for _, t in sent), sent


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests telegram_bot passent.")

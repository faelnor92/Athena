"""OAuth Google (Calendar + Gmail) : construction d'URL, state CSRF anti-rejeu, étendues,
routage agenda OAuth-prioritaire, et garde de connexion. AUCUN appel réseau réel."""
import os
import sys
from unittest import mock
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "cid.apps.googleusercontent.com"
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "secret"
os.environ.pop("GOOGLE_OAUTH_REDIRECT_URI", None)

import core.google_oauth as go      # noqa: E402
import tools.agenda_sync as asy     # noqa: E402
import tools.gmail_oauth as gm      # noqa: E402


def test_configured_and_scopes():
    assert go.is_configured()
    # Étendues attendues : Calendar (R/W) + Gmail (lecture seule) + identité.
    joined = " ".join(go.SCOPES)
    assert "calendar.events" in joined
    assert "gmail.readonly" in joined
    assert "openid" in joined


def test_redirect_uri_priority():
    # Dérivée de la requête à défaut d'env.
    assert go.redirect_uri("http://192.168.1.50:8000/") == \
        "http://192.168.1.50:8000/api/oauth/google/callback"
    # L'env prime (cas homelab : URI HTTPS via domaine/tunnel).
    with mock.patch.dict(os.environ, {"GOOGLE_OAUTH_REDIRECT_URI": "https://a.fr/api/oauth/google/callback"}):
        assert go.redirect_uri("http://x/") == "https://a.fr/api/oauth/google/callback"


def test_auth_url_and_state_single_use():
    url = go.build_auth_url("http://localhost:8000/")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"]      # → refresh_token
    assert q["prompt"] == ["consent"]
    assert q["response_type"] == ["code"]
    state = q["state"][0]
    # Le state se consomme UNE seule fois (anti-rejeu / CSRF).
    assert go._pop_state(state) is not None
    assert go._pop_state(state) is None
    # State inconnu/expiré → refusé.
    assert go._pop_state("inexistant") is None


def test_disconnected_paths_are_graceful():
    # Pas de refresh_token stocké → pas de token, pas de calendrier Google actif.
    with mock.patch.object(go.user_config, "get", return_value=None):
        assert go.get_access_token(user="local") is None
        assert go.is_connected(user="local") is False
    # gmail lecture sans connexion → message clair (pas d'exception).
    with mock.patch.object(go, "get_access_token", return_value=None):
        assert "non connecté" in gm.read_gmail().lower()
        assert "non connecté" in gm.read_gmail_message("abc").lower()


def test_agenda_prefers_oauth_token():
    # Si l'OAuth fournit un token, get_google_calendar_client l'utilise (calendrier 'primary'
    # par défaut) SANS exiger de fichier de compte de service ni de partage.
    with mock.patch.object(asy, "_oauth_token", return_value="ya29.fake"):
        os.environ.pop("GOOGLE_CALENDAR_ID", None)
        token, cal = asy.get_google_calendar_client()
        assert token == "ya29.fake"
        assert cal == "primary"
        assert asy.google_calendar_enabled() is True
    # Sans OAuth ni compte de service → désactivé.
    with mock.patch.object(asy, "_oauth_token", return_value=None):
        asy.GOOGLE_KEY_PATH = "/chemin/inexistant_xyz.json"
        os.environ.pop("GOOGLE_CALENDAR_ID", None)
        assert asy.google_calendar_enabled() is False


def test_gmail_readonly_no_write_capability():
    # SÛRETÉ : aucune fonction d'envoi/suppression dans le lecteur Gmail OAuth.
    names = [n for n in dir(gm) if not n.startswith("_")]
    assert not any(x in n.lower() for n in names for x in ("send", "delete", "draft", "trash"))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests google_oauth passent.")

"""Nextcloud (WebDAV/CalDAV/CardDAV) : config, dérivation d'URL, anti-traversal,
gardes (non configuré / lecture seule), et net_guard allowlist côté chemin."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.nextcloud as nc        # noqa: E402
import tools.nextcloud_tools as nt  # noqa: E402


def test_not_configured_is_graceful():
    with mock.patch.object(nc, "is_configured", return_value=False):
        for out in (nt.nextcloud_list_files(), nt.nextcloud_read_file("a.txt"),
                    nt.nextcloud_list_tasks(), nt.nextcloud_search_contacts("x")):
            assert "non configuré" in out.lower(), out


def test_url_derivation():
    with mock.patch.dict(os.environ, {"NEXTCLOUD_URL": "https://cloud.x.fr/",
                                      "NEXTCLOUD_USERNAME": "fael",
                                      "NEXTCLOUD_PASSWORD": "app-pwd"}), \
         mock.patch.object(nc.user_config, "get", return_value=None):
        assert nc.is_configured()
        assert nc.files_base() == "https://cloud.x.fr/remote.php/dav/files/fael/"
        assert nc.calendars_base().endswith("/remote.php/dav/calendars/fael/")
        assert nc.addressbooks_base().endswith("/remote.php/dav/addressbooks/users/fael/")


def test_path_traversal_blocked():
    with mock.patch.dict(os.environ, {"NEXTCLOUD_URL": "https://cloud.x.fr",
                                      "NEXTCLOUD_USERNAME": "fael",
                                      "NEXTCLOUD_PASSWORD": "p"}), \
         mock.patch.object(nc.user_config, "get", return_value=None):
        out = nt.nextcloud_read_file("../../etc/passwd")
        assert "invalide" in out.lower() or "interdite" in out.lower(), out


def test_write_delete_require_can_write():
    with mock.patch.dict(os.environ, {"NEXTCLOUD_URL": "https://cloud.x.fr",
                                      "NEXTCLOUD_USERNAME": "fael",
                                      "NEXTCLOUD_PASSWORD": "p"}), \
         mock.patch.object(nc.user_config, "get", return_value=None), \
         mock.patch.object(nt.projects, "can_write", return_value=False):
        assert "lecture seule" in nt.nextcloud_write_file("a.txt", "x").lower()
        assert "lecture seule" in nt.nextcloud_delete_file("a.txt").lower()


def test_ssrf_guard_blocks_private_without_allowlist():
    # Nextcloud en IP privée + pas d'allowlist → bloqué proprement (message anti-SSRF).
    os.environ.pop("NET_GUARD_ALLOW_HOSTS", None)
    import tools.net_guard as ng
    import importlib
    importlib.reload(ng)
    with mock.patch.dict(os.environ, {"NEXTCLOUD_URL": "http://192.168.1.10:8080",
                                      "NEXTCLOUD_USERNAME": "fael",
                                      "NEXTCLOUD_PASSWORD": "p"}), \
         mock.patch.object(nc.user_config, "get", return_value=None), \
         mock.patch.object(nt, "is_blocked_url", ng.is_blocked_url):
        out = nt.nextcloud_list_files("")
        assert "ssrf" in out.lower() or "interne" in out.lower(), out


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests nextcloud passent.")

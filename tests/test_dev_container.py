"""Conteneur dev persistant : tests SANS Docker (subprocess mocké).

Vérifie le nommage/clé, la logique enabled(off/on/auto), la réutilisation d'un conteneur
déjà actif, et la construction correcte de la commande `docker exec` (UID hôte, HOME
persistant dans le projet, cd dans le sous-dossier)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import dev_container as dc  # noqa: E402


def test_sanitize_key():
    assert dc.sanitize_key("Alice@Corp", "Proj X!") == "alice-corp-proj-x"
    assert dc.sanitize_key("", None) == "local-global"
    assert len(dc.sanitize_key("u" * 200, "p" * 200)) <= 48


def test_container_name_prefix():
    assert dc.container_name("alice-proj").startswith("athena-dev-")


def test_enabled_modes(monkeypatch=None):
    with mock.patch.dict(os.environ, {"DEV_CONTAINER_MODE": "off"}):
        assert dc.enabled() is False
    with mock.patch.dict(os.environ, {"DEV_CONTAINER_MODE": "on"}):
        assert dc.enabled() is True
    with mock.patch.dict(os.environ, {"DEV_CONTAINER_MODE": "auto"}):
        with mock.patch.object(dc, "docker_available", return_value=True):
            assert dc.enabled() is True
        with mock.patch.object(dc, "docker_available", return_value=False):
            assert dc.enabled() is False


def test_ensure_reuses_running_container():
    with mock.patch.object(dc, "docker_available", return_value=True), \
         mock.patch.object(dc, "_is_running", return_value=True), \
         mock.patch("subprocess.run") as run:
        name, err = dc.ensure("alice-proj")
        assert err is None
        assert name == "athena-dev-alice-proj"
        run.assert_not_called()  # conteneur déjà actif → aucun docker run/build


def test_exec_bash_builds_correct_command():
    captured = {}

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return mock.Mock(stdout="out", stderr="", returncode=0)

    with mock.patch.object(dc, "docker_available", return_value=True), \
         mock.patch.object(dc, "_is_running", return_value=True), \
         mock.patch("subprocess.run", side_effect=fake_run):
        out, err, rc = dc.exec_bash("alice-proj", "pip install x", timeout=42, workdir="sub/dir")

    assert (out, rc) == ("out", 0)
    cmd = captured["cmd"]
    assert cmd[0] == "docker" and cmd[1] == "exec"
    assert "athena-dev-alice-proj" in cmd
    wrapper = cmd[-1]
    assert "export HOME=" in wrapper and "/work/.athena-home" in wrapper
    assert "cd sub/dir" in wrapper
    assert wrapper.strip().endswith("pip install x")
    if hasattr(os, "getuid"):
        assert "-u" in cmd and f"{os.getuid()}:{os.getgid()}" in cmd


def test_exec_bash_surfaces_ensure_error():
    with mock.patch.object(dc, "docker_available", return_value=False):
        out, err, rc = dc.exec_bash("k", "ls")
        assert rc == 1 and "Docker" in err


def test_sandbox_runner_routes_to_dev_container_when_active():
    """Quand un conteneur dev est ACTIF (console codeur), sandbox_runner.run_bash y délègue."""
    from tools import sandbox_runner
    with mock.patch.object(dc, "enabled", return_value=True), \
         mock.patch.object(dc, "exec_bash", return_value=("DEV", "", 0)) as ex:
        tok = dc.activate("alice-proj")
        try:
            out, err, rc = sandbox_runner.run_bash("git status", timeout=15, workdir="x")
        finally:
            dc.deactivate(tok)
    assert (out, rc) == ("DEV", 0)
    ex.assert_called_once()
    # le timeout est élargi pour les installs/tests
    assert ex.call_args.kwargs.get("timeout", 0) >= 120


def test_sandbox_runner_no_route_when_inactive():
    """Hors contexte console codeur (pas de conteneur actif) : pas de délégation."""
    from tools import sandbox_runner
    assert dc.active_key() is None
    with mock.patch.object(dc, "exec_bash") as ex, \
         mock.patch("tools.sandbox_runner._execute", return_value=("", "", 0)):
        sandbox_runner.run_bash("ls", timeout=5)
    ex.assert_not_called()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests dev_container passent.")

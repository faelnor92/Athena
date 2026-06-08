"""Plugin Claude Code : opt-in, détection du binaire, appel headless (subprocess mocké)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import claude_code_tool as cc  # noqa: E402


def test_desactive_par_defaut():
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CLAUDE_CODE_ENABLED", None)
        out = cc.claude_code("fais X")
    assert "désactivé" in out.lower(), out
    print("OK test_desactive_par_defaut")


def test_binaire_absent():
    with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENABLED": "true"}), \
         mock.patch.object(cc, "_bin", return_value=""):
        out = cc.claude_code("fais X")
    assert "introuvable" in out.lower(), out
    print("OK test_binaire_absent")


def test_appel_headless_ok():
    class _R:
        stdout = '{"result": "Tâche terminée: 2 fichiers modifiés."}'
        stderr = ""
        returncode = 0
    with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENABLED": "true"}), \
         mock.patch.object(cc, "_bin", return_value="/usr/bin/claude"), \
         mock.patch.object(cc, "_project_dir", return_value="/tmp"), \
         mock.patch("subprocess.run", return_value=_R()) as run:
        out = cc.claude_code("corrige le bug")
    assert "2 fichiers" in out, out
    cmd = run.call_args.args[0]
    assert cmd[:3] == ["/usr/bin/claude", "-p", "corrige le bug"], cmd
    assert "--output-format" in cmd and "--permission-mode" in cmd, cmd
    assert run.call_args.kwargs.get("cwd") == "/tmp", "doit s'exécuter dans le projet actif"
    print("OK test_appel_headless_ok")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nTous les tests claude_code passent.")

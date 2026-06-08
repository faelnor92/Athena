"""Plugin Claude Code : opt-in, détection du binaire, appel headless (subprocess mocké)."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import claude_code_tool as cc  # noqa: E402


def test_desactive_par_defaut():
    # Indépendant de l'état : ni env, ni flag shared_store → enabled() doit être False.
    with mock.patch.dict(os.environ, {}, clear=False), \
         mock.patch("core.shared_store.get", return_value=None):
        os.environ.pop("CLAUDE_CODE_ENABLED", None)
        out = cc.claude_code("fais X")
    assert "désactivé" in out.lower(), out
    print("OK test_desactive_par_defaut")


def test_binaire_absent():
    with mock.patch.object(cc, "enabled", return_value=True), \
         mock.patch.object(cc, "_bin", return_value=""):
        out = cc.claude_code("fais X")
    assert "introuvable" in out.lower(), out
    print("OK test_binaire_absent")


def test_appel_headless_ok():
    class _R:
        stdout = '{"result": "Tâche terminée: 2 fichiers modifiés."}'
        stderr = ""
        returncode = 0
    with mock.patch.object(cc, "enabled", return_value=True), \
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


def test_injecte_dans_le_codeur_si_active():
    """Plugin activé → l'outil claude_code est donné AUTOMATIQUEMENT à l'agent codeur."""
    import core.swarm as swarm_mod
    from core.swarm import Swarm
    from core.agent import Agent
    from core import shared_store

    captured = {}
    class _Msg:
        content = "ok"; tool_calls = None
        def model_dump(self, exclude_none=True): return {"role": "assistant", "content": "ok"}
    class _Usage:
        prompt_tokens = 1; completion_tokens = 1
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]; usage = _Usage()
    def fake(**kw):
        captured["tools"] = kw.get("tools")
        return _Resp()

    def edit_file(path="x"):
        """Outil d'édition de code (rend l'agent 'codeur')."""
        return "ok"

    os.environ["TOOL_FILTER_ENABLED"] = "false"  # isole de l'exposition filtrée
    swarm_mod.completion = fake
    shared_store.set("plugins", "claude_code_enabled", True)
    try:
        s = Swarm.__new__(Swarm)
        ag = Agent(name="Codeur", system_prompt="code", model="gpt-4o")
        ag.tools = [edit_file]
        s.agents = {"Codeur": ag}
        s.run(ag, [{"role": "user", "content": "corrige le bug"}], max_turns=1)
        names = {(t.get("function") or {}).get("name") for t in (captured.get("tools") or [])}
        assert "claude_code" in names, f"claude_code non injecté dans le codeur : {names}"
        print("OK test_injecte_dans_le_codeur_si_active")
    finally:
        shared_store.delete("plugins", "claude_code_enabled")
        os.environ.pop("TOOL_FILTER_ENABLED", None)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nTous les tests claude_code passent.")

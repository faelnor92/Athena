"""Tests des permissions par canal (core.channels) + filtrage des outils swarm."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import channels


def test_politiques_par_defaut():
    assert channels.auto_approve_for("voice") is True
    assert channels.auto_approve_for("cli") is True
    assert channels.auto_approve_for("web") is False
    # Telegram interdit le shell/ssh même via un sous-canal "telegram:123".
    assert channels.tool_allowed("telegram:12345", "execute_bash_command") is False
    assert channels.tool_allowed("telegram:12345", "web_search") is True
    # Canal inconnu → politique 'default'.
    assert channels.tool_allowed("inconnu", "web_search") is True
    print("OK: politiques par canal par défaut")


def test_swarm_filtre_les_outils_par_canal():
    os.environ["SELF_IMPROVE"] = "false"
    import core.swarm as swarm_mod
    from core.agent import Agent
    from core.swarm import Swarm

    captured = {"tools": None}

    def fake_complete(self, model, messages, tools_schema=None, allow_continuation=True, on_delta=None):
        captured["tools"] = [t["function"]["name"] for t in (tools_schema or [])]
        class _M:
            content = "ok"
            tool_calls = None
            def model_dump(self, exclude_none=True):
                return {"role": "assistant", "content": "ok"}
        class _U:
            prompt_tokens = 1
            completion_tokens = 1
        class _C:
            message = _M()
        class _R:
            choices = [_C()]
            usage = _U()
        return _R()

    def interdit():
        """outil interdit."""
        return "x"

    def permis():
        """outil permis."""
        return "y"

    swarm_mod.Swarm._complete = fake_complete
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Jarvis", system_prompt="t", model="gpt-4o")
    agent.tools = [interdit, permis]
    s.agents = {"Jarvis": agent}

    token = channels.current_channel.set("salon")
    # Politique runtime : interdire 'interdit' sur le canal 'salon'.
    channels._cache = dict(channels._DEFAULTS)
    channels._cache["salon"] = {"auto_approve": True, "allow": "*", "deny": ["interdit"]}
    try:
        s.run(agent, [{"role": "user", "content": "go"}], max_turns=1)
    finally:
        channels.current_channel.reset(token)
        channels._cache = None

    assert "permis" in captured["tools"], captured["tools"]
    assert "interdit" not in captured["tools"], f"outil interdit exposé: {captured['tools']}"
    print("OK: le swarm filtre les outils selon le canal")


if __name__ == "__main__":
    test_politiques_par_defaut()
    test_swarm_filtre_les_outils_par_canal()

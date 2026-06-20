import os
import sys
from unittest import mock
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Désactivation des hooks d'apprentissage en arrière-plan pour éviter les effets de bord entre tests
os.environ["ASYNC_POST_HOOKS"] = "false"
os.environ["SELF_IMPROVE"] = "false"
os.environ["GRAPH_AUTO_EXTRACT"] = "false"
os.environ["USER_MODELING"] = "false"
os.environ["SELF_IMPROVE_SKILLS"] = "false"

from core import channels
import core.swarm as swarm_mod
from core.swarm import Swarm
from core.agent import Agent

def test_cli_channel_auto_approve_disabled():
    assert not channels.auto_approve_for("cli")

def test_engine_interactive_approval_approved():
    tool_called = False
    
    def sensitive_tool():
        """Outil sensible."""
        nonlocal tool_called
        tool_called = True
        return "success_val"
    
    class _F:
        name = "sensitive_tool"
        arguments = "{}"
    class _TC:
        id = "call_sensitive"
        type = "function"
        function = _F()
    class _Msg1:
        content = ""
        tool_calls = [_TC()]
        def model_dump(self, exclude_none=True):
            return {
                "role": "assistant",
                "tool_calls": [{"id": "call_sensitive", "type": "function", "function": {"name": "sensitive_tool", "arguments": "{}"}}]
            }
    class _Msg2:
        content = "done"
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "done"}
            
    class _Choice1:
        message = _Msg1()
        finish_reason = "tool_calls"
    class _Choice2:
        message = _Msg2()
        finish_reason = "stop"
        
    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1
        
    class _Resp1:
        choices = [_Choice1()]
        usage = _Usage()
    class _Resp2:
        choices = [_Choice2()]
        usage = _Usage()
        
    call_count = 0
    def fake_complete(**kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _Resp1()
        return _Resp2()
        
    original_completion = swarm_mod.completion
    swarm_mod.completion = fake_complete
    chan_token = channels.current_channel.set("cli")
    
    try:
        s = Swarm()
        ag = Agent(name="Codeur", system_prompt="code", model="gpt-4o")
        ag.tools = [sensitive_tool]
        s.agents = {"Codeur": ag}
        
        with mock.patch("builtins.input", return_value="y"), \
             mock.patch.dict(os.environ, {"SENSITIVE_TOOLS": "sensitive_tool"}):
            s.run(ag, [{"role": "user", "content": "run sensitive action"}], max_turns=2)
            
        assert tool_called, "L'outil sensible aurait dû être exécuté car approuvé"
    finally:
        swarm_mod.completion = original_completion
        channels.current_channel.reset(chan_token)

def test_engine_interactive_approval_denied():
    tool_called = False
    
    def sensitive_tool():
        """Outil sensible."""
        nonlocal tool_called
        tool_called = True
        return "success_val"
    
    class _F:
        name = "sensitive_tool"
        arguments = "{}"
    class _TC:
        id = "call_sensitive"
        type = "function"
        function = _F()
    class _Msg1:
        content = ""
        tool_calls = [_TC()]
        def model_dump(self, exclude_none=True):
            return {
                "role": "assistant",
                "tool_calls": [{"id": "call_sensitive", "type": "function", "function": {"name": "sensitive_tool", "arguments": "{}"}}]
            }
    class _Msg2:
        content = "done"
        tool_calls = None
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "done"}
            
    class _Choice1:
        message = _Msg1()
        finish_reason = "tool_calls"
    class _Choice2:
        message = _Msg2()
        finish_reason = "stop"
        
    class _Usage:
        prompt_tokens = 1
        completion_tokens = 1
        
    class _Resp1:
        choices = [_Choice1()]
        usage = _Usage()
    class _Resp2:
        choices = [_Choice2()]
        usage = _Usage()
        
    call_count = 0
    def fake_complete(**kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _Resp1()
        return _Resp2()
        
    original_completion = swarm_mod.completion
    swarm_mod.completion = fake_complete
    chan_token = channels.current_channel.set("cli")
    
    try:
        s = Swarm()
        ag = Agent(name="Codeur", system_prompt="code", model="gpt-4o")
        ag.tools = [sensitive_tool]
        s.agents = {"Codeur": ag}
        
        with mock.patch("builtins.input", return_value="n"), \
             mock.patch.dict(os.environ, {"SENSITIVE_TOOLS": "sensitive_tool"}):
            from core import approvals
            print("SENSITIVE_TOOLS env:", os.environ.get("SENSITIVE_TOOLS"))
            print("sensitive_tool_names():", approvals.sensitive_tool_names())
            print("is_sensitive(sensitive_tool):", approvals.is_sensitive(sensitive_tool))
            _, messages, _ = s.run(ag, [{"role": "user", "content": "run sensitive action"}], max_turns=2)
            print("MESSAGES DANS ECHEC :", messages)
            
        assert not tool_called, "L'outil sensible ne doit pas s'exécuter car refusé"
        tool_outputs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_outputs) > 0
        assert "REFUSÉE" in tool_outputs[0].get("content", "")
    finally:
        swarm_mod.completion = original_completion
        channels.current_channel.reset(chan_token)

def test_cascade_rules_loader(tmp_path):
    rules_file = tmp_path / ".athena-rules.md"
    rules_file.write_text("RULE_SPEC_1234", encoding="utf-8")
    
    captured_kw = {}
    class _Msg:
        content = "done"
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": "done"}
    class _Choice:
        message = _Msg()
    class _Resp:
        choices = [_Choice()]
        class _Usage:
            prompt_tokens = 1; completion_tokens = 1
        usage = _Usage()
        
    def fake_complete(**kw):
        captured_kw.update(kw)
        return _Resp()
        
    original_completion = swarm_mod.completion
    swarm_mod.completion = fake_complete
    
    try:
        from core.state import get_workspace_dir
        with mock.patch("core.state.get_workspace_dir", return_value=str(tmp_path)):
            s = Swarm()
            ag = Agent(name="Codeur", system_prompt="code", model="gpt-4o")
            s.agents = {"Codeur": ag}
            s.run(ag, [{"role": "user", "content": "hello"}], max_turns=1)
            
        messages = captured_kw.get("messages", [])
        system_msgs = [m for m in messages if m.get("role") == "system"]
        assert len(system_msgs) > 0
        sys_content = system_msgs[0].get("content", "")
        assert "RULE_SPEC_1234" in sys_content
    finally:
        swarm_mod.completion = original_completion

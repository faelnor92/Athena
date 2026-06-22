"""Phase 3 : mode plan (lecture seule), outil glob, préambule modèle, chargement
des instructions de projet (cache/cascade/AGENTS.md/SYSTEM.md)."""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.swarm as swarm_mod  # noqa: E402
from core import plan_mode  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.swarm import Swarm, engine  # noqa: E402
from core.swarm.llm import model_style_preamble  # noqa: E402
from tools import code_nav, code_edit  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="athena_p3_")


@pytest.fixture(autouse=True)
def _ws(monkeypatch):
    monkeypatch.setenv("ACTIVE_WORKSPACE_DIR", _tmp)
    monkeypatch.setenv("TOOL_FILTER_ENABLED", "false")  # isole du filtre sémantique


# --- Mode plan -------------------------------------------------------------
def test_plan_mode_defaut_inactif_puis_toggle():
    assert plan_mode.is_active() is False
    assert plan_mode.toggle() is True
    assert plan_mode.is_active() is True
    assert plan_mode.toggle() is False


def test_plan_mode_bloque_les_outils_mutants():
    assert plan_mode.is_blocked("edit_file") and plan_mode.is_blocked("execute_bash_command")
    assert not plan_mode.is_blocked("read_file") and not plan_mode.is_blocked("search_code")


def test_swarm_retire_les_outils_mutants_en_mode_plan(monkeypatch):
    captured = {"tools": None}

    def fake_complete(self, model, messages, tools_schema=None, allow_continuation=True, on_delta=None):
        captured["tools"] = [t["function"]["name"] for t in (tools_schema or [])]
        class _M:
            content = "plan"; tool_calls = None
            def model_dump(self, exclude_none=True): return {"role": "assistant", "content": "plan"}
        class _U: prompt_tokens = 1; completion_tokens = 1
        class _C: message = _M()
        class _R: choices = [_C()]; usage = _U()
        return _R()

    monkeypatch.setattr(swarm_mod.Swarm, "_complete", fake_complete)
    plan_mode.set_active(True)
    s = Swarm.__new__(Swarm)
    agent = Agent(name="Codeur", system_prompt="t", model="gpt-4o")
    agent.tools = [engine.AVAILABLE_TOOLS["read_file"], engine.AVAILABLE_TOOLS["edit_file"],
                   engine.AVAILABLE_TOOLS["search_code"]]
    s.agents = {"Codeur": agent}
    s.orchestrator_name = "Codeur"
    s.run(agent, [{"role": "user", "content": "go"}], max_turns=1)
    assert "read_file" in captured["tools"], captured["tools"]
    assert "edit_file" not in captured["tools"], "outil mutant exposé en mode plan"


# --- Outil glob ------------------------------------------------------------
def test_glob_files_motif_et_tri():
    os.makedirs(os.path.join(_tmp, "src"), exist_ok=True)
    code_edit.write_file("src/a.py", "x=1\n")
    code_edit.write_file("src/b.py", "y=2\n")
    code_edit.write_file("notes.txt", "hello\n")
    out = code_nav.glob_files("**/*.py")
    assert "src/a.py" in out and "src/b.py" in out and "notes.txt" not in out
    # motif sans slash → cherche partout
    assert "notes.txt" in code_nav.glob_files("*.txt")


def test_glob_files_aucun_resultat():
    assert "aucun fichier" in code_nav.glob_files("**/*.rs").lower()


# --- Préambule par famille de modèle --------------------------------------
def test_model_style_preamble():
    assert model_style_preamble("coder-qwen")     # qwen → ajout
    assert model_style_preamble("chat-gemma")     # gemma → famille gemini
    assert model_style_preamble("ministral")
    assert model_style_preamble("claude-opus-4-8") == ""  # déjà bon → rien
    assert model_style_preamble("gpt-4o") == ""


# --- Instructions de projet (cascade / cache / AGENTS.md / SYSTEM.md) ------
def test_load_local_instructions_cascade_et_override():
    root = tempfile.mkdtemp()
    os.mkdir(os.path.join(root, ".git"))
    sub = os.path.join(root, "src"); os.mkdir(sub)
    open(os.path.join(root, "AGENTS.md"), "w").write("REGLE RACINE")
    open(os.path.join(sub, "CLAUDE.md"), "w").write("REGLE SRC")
    ov, instr = engine._load_local_instructions(sub)
    assert ov is None
    assert instr.index("REGLE RACINE") < instr.index("REGLE SRC")  # racine avant le plus spécifique
    # SYSTEM.md = override total + ne remonte pas au-dessus du .git
    open(os.path.join(sub, "SYSTEM.md"), "w").write("PROMPT TOTAL")
    ov2, _ = engine._load_local_instructions(sub)
    assert ov2 == "PROMPT TOTAL"
    assert engine._project_boundary(sub) == os.path.realpath(root)


def test_load_local_instructions_cap_taille(monkeypatch):
    monkeypatch.setattr(engine, "_LOCAL_INSTR_MAX", 100)
    d = tempfile.mkdtemp(); os.mkdir(os.path.join(d, ".git"))
    open(os.path.join(d, "CLAUDE.md"), "w").write("A" * 5000)
    _, instr = engine._load_local_instructions(d)
    assert "tronqué" in instr and len(instr) < 400

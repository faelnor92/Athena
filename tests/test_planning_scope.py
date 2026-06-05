"""Scope du plan : la console codeur isole son plan de celui du chat (canal 'web').

Vérifie que set_scope() prime sur le canal courant dans planning_tools._cid(), et que
make_plan/get_plan d'un scope console n'écrasent pas le plan d'un autre scope."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_fd, _plans = tempfile.mkstemp(prefix="plans_", suffix=".json")
os.close(_fd)
os.environ["PLANS_PATH"] = _plans

from core import channels  # noqa: E402
from core import plan_store  # noqa: E402
import tools.planning_tools as planning  # noqa: E402


def test_scope_overrides_channel():
    tok_ch = channels.current_channel.set("web")
    try:
        assert planning._cid() == "web"
        tok = planning.set_scope("coder:alice:proj1")
        try:
            assert planning._cid() == "coder:alice:proj1"
        finally:
            planning.reset_scope(tok)
        assert planning._cid() == "web"  # rétabli
    finally:
        channels.current_channel.reset(tok_ch)


def test_console_plan_isolated_from_chat():
    # Plan du CHAT (canal web, pas de scope)
    tok_ch = channels.current_channel.set("web")
    try:
        planning.make_plan("étape chat A\nétape chat B")
        # Plan de la CONSOLE (scope dédié)
        tok = planning.set_scope("coder:alice:proj1")
        try:
            planning.make_plan("étape code 1\nétape code 2\nétape code 3")
            assert len(plan_store.get_plan("coder:alice:proj1")) == 3
        finally:
            planning.reset_scope(tok)
        # Le plan du chat est intact (non écrasé par celui de la console)
        chat = plan_store.get_plan("web")
        assert len(chat) == 2 and chat[0]["text"] == "étape chat A"
    finally:
        channels.current_channel.reset(tok_ch)


def test_update_step_in_scope():
    tok = planning.set_scope("coder:bob:p")
    try:
        planning.make_plan("a\nb")
        planning.update_plan_step(step=1, status="done")
        items = plan_store.get_plan("coder:bob:p")
        assert items[0]["status"] == "done" and items[1]["status"] == "pending"
    finally:
        planning.reset_scope(tok)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("\nTous les tests de scope de plan passent.")

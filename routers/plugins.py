"""Réglages > Plugins : état et activation des extensions d'Athena.

Athena étend ses capacités via : MCP (serveurs externes), compétences dynamiques (skills/),
et des intégrations first-class (ex. Claude Code). Ce routeur expose leur état + un toggle.
"""
from fastapi import APIRouter, Body
from core import shared_store
from tools import claude_code_tool

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])


def _mcp_tool_count() -> int:
    try:
        from tools import mcp_manager
        return len(mcp_manager.mcp_manager.tool_functions())
    except Exception:
        return 0


def _skills_count() -> int:
    try:
        from core.swarm import load_dynamic_skills
        return len(load_dynamic_skills())
    except Exception:
        return 0


@router.get("")
async def list_plugins():
    return {
        "claude_code": {
            "name": "Claude Code",
            "description": "Délègue les tâches de code à l'agent Claude Code (CLI), dans le projet actif.",
            "available": claude_code_tool.available(),
            "enabled": claude_code_tool.enabled(),
            "tool": "claude_code",
        },
        "mcp": {"name": "Serveurs MCP", "description": "Outils externes (protocole MCP).", "tools": _mcp_tool_count()},
        "skills": {"name": "Compétences dynamiques", "description": "Outils Python auto-chargés (skills/).", "count": _skills_count()},
    }


@router.post("/claude-code")
async def toggle_claude_code(payload: dict = Body(...)):
    enabled = bool(payload.get("enabled"))
    shared_store.set("plugins", "claude_code_enabled", enabled)
    return {"enabled": claude_code_tool.enabled(), "available": claude_code_tool.available()}

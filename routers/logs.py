"""Routeur : panneau de logs live (/api/logs) + niveau de log à chaud (/api/logs/level).
Réservé à l'admin (cf. _ADMIN_EXACT). Les secrets sont déjà masqués dans le tampon."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Logs"])

_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


@router.get("/api/logs")
async def get_logs(level: str = "", limit: int = 200):
    """Derniers logs en mémoire (filtrés par niveau minimal si fourni)."""
    from core.logging_config import get_recent_logs, current_level
    return {"level": current_level(), "levels": _LEVELS, "logs": get_recent_logs(level, limit)}


class LogLevelRequest(BaseModel):
    level: str


@router.post("/api/logs/level")
async def set_logs_level(req: LogLevelRequest):
    """Change le niveau de log à chaud (sans redémarrage)."""
    from core.logging_config import set_log_level
    return {"status": "success", "level": set_log_level(req.level)}

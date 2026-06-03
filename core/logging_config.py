"""Configuration de logging structuré avec rotation de fichier.

Remplace progressivement les print() bruts par un logging à niveaux. Les sorties
console colorées du swarm (affichage live des étapes) restent volontairement en
print() car elles servent d'UX temps réel.
"""
import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler

_CONFIGURED = False

# Tampon circulaire en mémoire des derniers logs (pour le panneau de logs de l'UI).
_RING = deque(maxlen=int(os.getenv("LOG_BUFFER_SIZE", "800") or 800))


class _RedactionFilter(logging.Filter):
    """Masque les secrets dans le message formaté de chaque enregistrement de log."""
    def filter(self, record):
        try:
            from core.redaction import redact_secrets
            if record.args:
                record.msg = redact_secrets(record.getMessage())
                record.args = ()
            else:
                record.msg = redact_secrets(record.msg)
        except Exception:
            pass
        return True


class RingBufferHandler(logging.Handler):
    """Conserve les derniers enregistrements en mémoire (exposés via /api/logs)."""
    def emit(self, record):
        try:
            _RING.append({
                "t": record.created,
                "level": record.levelname,
                "name": record.name,
                "msg": record.getMessage(),
            })
        except Exception:
            pass


def get_recent_logs(level: str = "", limit: int = 200):
    """Renvoie les logs récents (filtrés par niveau minimal si fourni)."""
    items = list(_RING)
    lvl = (level or "").upper().strip()
    if lvl and lvl in logging._nameToLevel:
        threshold = logging._nameToLevel[lvl]
        items = [r for r in items if logging._nameToLevel.get(r["level"], 0) >= threshold]
    limit = max(1, min(int(limit or 200), _RING.maxlen or 800))
    return items[-limit:]


def set_log_level(level: str) -> str:
    """Change le niveau de log À CHAUD (root) et le mémorise dans l'env du process."""
    lvl = (level or "").upper().strip()
    if lvl not in logging._nameToLevel:
        lvl = "INFO"
    logging.getLogger().setLevel(lvl)
    os.environ["LOG_LEVEL"] = lvl
    return lvl


def current_level() -> str:
    return logging.getLevelName(logging.getLogger().level)


def setup_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return logging.getLogger()

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "athena.log"),
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(_RedactionFilter())

    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)

    # Tampon mémoire pour le panneau de logs de l'UI (mêmes secrets masqués).
    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        ring = RingBufferHandler()
        ring.setFormatter(fmt)
        ring.addFilter(_RedactionFilter())
        root.addHandler(ring)

    # Réduit le bruit des bibliothèques tierces très bavardes.
    for noisy in ("httpx", "httpcore", "LiteLLM", "litellm", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

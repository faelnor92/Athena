"""Configuration de logging structuré avec rotation de fichier.

Remplace progressivement les print() bruts par un logging à niveaux. Les sorties
console colorées du swarm (affichage live des étapes) restent volontairement en
print() car elles servent d'UX temps réel.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

_CONFIGURED = False


def setup_logging():
    global _CONFIGURED
    if _CONFIGURED:
        return logging.getLogger()

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "jarvis.log"),
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(file_handler)

    # Réduit le bruit des bibliothèques tierces très bavardes.
    for noisy in ("httpx", "httpcore", "LiteLLM", "litellm", "chromadb", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

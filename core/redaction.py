"""Rédaction (masquage) de secrets dans tout texte destiné aux logs, aux traces
(runs.sqlite3) ou renvoyé par un outil.

Deux niveaux, sans faux positifs sur du contenu légitime :
1. les VALEURS réelles des variables d'environnement sensibles (clés API, mots de
   passe, tokens) — on ne veut JAMAIS voir ces chaînes en clair quelque part ;
2. quelques motifs à très haute confiance (sk-…, ghp_…, Bearer <token>, etc.).
"""
import os
import re

_MASK = "***REDACTED***"

# Indices de nom indiquant une variable d'env sensible.
_SECRET_HINTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PWD", "API")

# Motifs génériques à haute confiance (peu de risque de faux positif).
_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),                 # OpenAI & co
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                  # GitHub PAT
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),          # Slack
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                      # AWS access key id
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}"),       # en-tête Authorization
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),           # token bot Telegram
]


def _secret_env_values():
    vals = set()
    for name, val in os.environ.items():
        if not val or len(val) < 6:
            continue
        if any(h in name.upper() for h in _SECRET_HINTS):
            vals.add(val)
    # Les plus longues d'abord (évite de masquer une sous-chaîne avant le tout).
    return sorted(vals, key=len, reverse=True)


def redact_secrets(text):
    """Renvoie `text` avec les secrets masqués. Tolérant aux types non-str."""
    if text is None:
        return text
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:
            return text
    if not text:
        return text
    for val in _secret_env_values():
        if val in text:
            text = text.replace(val, _MASK)
    for pat in _PATTERNS:
        text = pat.sub(_MASK, text)
    return text

"""Mémoire de PROJET persistante — fait qu'Athena « connaît ton code » d'une session à l'autre
(contrairement à un agent de code sans mémoire). Stockée dans le workspace du projet actif
(.athena/PROJECT_MEMORY.md) → persiste, versionnable avec le code, éditable à la main.

Contenu typique : conventions de code, décisions d'architecture, commande de test/build, pièges
récurrents, structure du projet. JAMAIS de secret (le fichier peut être commité).
"""
import os

_DIRNAME = ".athena"
_FILENAME = "PROJECT_MEMORY.md"
_MAX_INJECT = 2000
_MAX_FILE = 16000


def _base(base=None):
    if base:
        return base
    try:
        from core.state import get_workspace_dir
        return get_workspace_dir()
    except Exception:
        return os.getcwd()


def _path(base=None):
    return os.path.join(_base(base), _DIRNAME, _FILENAME)


def load(base=None) -> str:
    try:
        with open(_path(base), encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""


def summary(max_chars: int = _MAX_INJECT, base=None) -> str:
    """Contenu borné, pour injection dans le contexte du Codeur (on garde le plus récent)."""
    c = load(base)
    if not c:
        return ""
    return c if len(c) <= max_chars else ("…(début tronqué)…\n" + c[-max_chars:])


def remember(note: str, base=None) -> str:
    note = (note or "").strip()
    if not note:
        return "Note vide ignorée."
    existing = load(base)
    if note.lower() in existing.lower():
        return "Déjà présent dans la mémoire du projet (ignoré)."
    p = _path(base)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        line = "- " + " ".join(note.split())  # une ligne, espaces normalisés
        with open(p, "a", encoding="utf-8") as f:
            if not existing:
                f.write("# Mémoire du projet — notes persistantes d'Athena\n"
                        "<!-- Faits durables réutilisés à chaque session. Pas de secret. -->\n\n")
            f.write(line + "\n")
        # garde-fou taille : tronque le plus ancien si ça gonfle trop
        full = load(base)
        if len(full) > _MAX_FILE:
            with open(p, "w", encoding="utf-8") as f:
                f.write(full[-_MAX_FILE:])
        return f"Mémorisé dans le projet : {line[2:90]}"
    except Exception as e:  # noqa: BLE001
        return f"Échec d'écriture de la mémoire projet : {e}"

"""Revue de code AUTO (relecture sécurité + qualité) — pour rattraper les angles morts d'une
passe unique (faille subtile, sel statique, régression, oubli de vérif).

Par défaut = AUTO-RELECTURE : le modèle relit son propre diff/fichiers via un prompt de relecteur
senior. L'agent peut AUSSI déléguer à un agent d'audit/sécurité s'il en existe un (mécanisme
delegate_to_ standard) — mais aucun agent dédié n'est requis.
"""
import os

_PROMPT = (
    "Tu es un RELECTEUR SENIOR (sécurité + qualité). Relis le code ci-dessous (modifications "
    "récentes) et liste UNIQUEMENT les VRAIS problèmes, par ordre d'importance :\n"
    "- Sécurité : injection (SQL/commande/path), secret en dur, CRYPTO FAIBLE (MD5/SHA1, ou sel "
    "STATIQUE/partagé au lieu d'aléatoire par mot de passe), désérialisation non sûre, eval.\n"
    "- Bugs / régressions / cas limites introduits.\n"
    "Sois CONCRET et ACTIONNABLE : « fichier:ligne — problème — correction ». Ignore le style.\n"
    "Si rien de sérieux, réponds EXACTEMENT « RAS ».\n\n"
)


def enabled() -> bool:
    return os.getenv("CODE_REVIEW", "true").lower() in ("true", "1", "yes")


def review_text(content: str, model: str = "") -> str:
    content = (content or "").strip()
    if not content:
        return "RAS"
    try:
        from core.state import swarm as _sw, _orch_agent
        mdl = (model or "").strip() or getattr(_orch_agent(), "model", None) or "qwen3"
        msgs = [{"role": "system", "content": _PROMPT + content[:24000]}]
        resp = _sw._complete(mdl, msgs, tools_schema=None, allow_continuation=True, allow_fallback=True)
        return (resp.choices[0].message.content or "RAS").strip() or "RAS"
    except Exception as e:  # noqa: BLE001
        return f"(revue indisponible : {e})"


def review_files(paths, model: str = "") -> str:
    """Relit le CONTENU des fichiers donnés (revue auto post-édition, sans dépendre de git)."""
    try:
        from core.state import get_workspace_dir
        base = get_workspace_dir()
    except Exception:
        base = os.getcwd()
    parts = []
    for p in list(dict.fromkeys(paths or []))[:20]:
        try:
            with open(os.path.join(base, p), encoding="utf-8", errors="ignore") as f:
                parts.append(f"=== {p} ===\n" + f.read()[:8000])
        except Exception:
            pass
    return review_text("\n\n".join(parts), model) if parts else "RAS"


def review_current(model: str = "") -> str:
    """Relit le DIFF git du projet actif (pour l'appel explicite via l'outil request_code_review)."""
    diff = ""
    try:
        from tools.git_tools import git_diff
        diff = git_diff() or ""
    except Exception:
        diff = ""
    low = diff.lower()
    if not diff.strip() or "pas un dépôt" in low or "not a git" in low or "aucune" in low:
        return ("Aucun diff git à relire (projet non versionné ou aucun changement). "
                "Astuce : la revue automatique post-édition de la console couvre ce cas.")
    return review_text("DIFF:\n" + diff, model)

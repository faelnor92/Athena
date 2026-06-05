"""Réglages PROPRES à l'utilisateur courant (chacun gère les siens — pas admin).

Aujourd'hui : configuration LLM par-utilisateur (modèle préféré + clés API perso) avec
repli sur la config de base si non renseigné. Demain : autres préférences perso.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from core import user_config

router = APIRouter(tags=["User Settings"])

# Champs LLM gérables par utilisateur (mêmes noms que les variables d'env globales).
_LLM_KEYS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
             "CUSTOM_LLM_API_BASE", "CUSTOM_LLM_API_KEY"]


def _mask(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return ""
    return f"{v[:4]}...{v[-4:]}" if len(v) > 8 else "***"


@router.get("/api/me/llm")
async def get_my_llm():
    """Config LLM de l'utilisateur courant (clés masquées). Champs vides = repli sur la base."""
    cfg = user_config.get_all()
    out = {"model": cfg.get("LLM_MODEL", "") or "", "using_base": not any(cfg.get(k) for k in _LLM_KEYS + ["LLM_MODEL"])}
    for k in _LLM_KEYS:
        out[k] = _mask(cfg.get(k, ""))
    return out


class MyLlmRequest(BaseModel):
    model: str | None = None
    keys: dict = None  # {OPENAI_API_KEY: "...", ...} ; valeur masquée/vide = inchangée


@router.post("/api/me/llm")
async def set_my_llm(req: MyLlmRequest):
    """Met à jour la config LLM de l'utilisateur courant. Une valeur masquée ('...') ou
    absente laisse la clé inchangée ; une chaîne vide explicite efface (repli sur la base)."""
    updates = {}
    if req.model is not None:
        updates["LLM_MODEL"] = req.model.strip()
    for k, v in (req.keys or {}).items():
        if k not in _LLM_KEYS:
            continue
        if v is None or "..." in str(v) or v == "***":
            continue  # masqué → inchangé
        updates[k] = str(v).strip()
    if updates:
        user_config.set_many(updates)
    return {"status": "success"}


@router.get("/api/me/usage")
async def my_usage():
    """Usage (requêtes, tokens, coût) du compte courant : aujourd'hui, 30 j, total."""
    import time
    from core.tracing import run_store
    from core.user_config import current_user_key
    u = current_user_key()
    day = time.time() - 86400
    month = time.time() - 30 * 86400
    return {
        "user": u,
        "today": run_store.usage_for(u, day),
        "month": run_store.usage_for(u, month),
        "total": run_store.usage_for(u),
    }


@router.get("/api/usage")
async def all_usage():
    """Usage agrégé PAR UTILISATEUR (admin) : 30 j et total."""
    import time
    from core.tracing import run_store
    return {"month": run_store.usage_by_user(time.time() - 30 * 86400),
            "total": run_store.usage_by_user()}

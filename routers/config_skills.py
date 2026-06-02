from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["Config Skills"])

@router.get("/api/config/skills")
async def get_config_skills() -> List[Dict[str, str]]:
    try:
        from core.swarm import load_dynamic_skills
        skills_dict = load_dynamic_skills()
        skills_list = []
        for name, func in skills_dict.items():
            doc = func.__doc__ or "Aucune description fournie."
            skills_list.append({
                "name": name,
                "description": doc.strip()
            })
        return skills_list
    except Exception as e:
        import logging
        logging.exception("Erreur de lecture des compétences")
        raise HTTPException(status_code=500, detail=f"Erreur de lecture des compétences : {str(e)}")

@router.delete("/api/config/skills/{skill_name}")
async def delete_config_skill(skill_name: str) -> Dict[str, str]:
    """Supprime une compétence permanente (fichier skills/<name>.py)."""
    try:
        from tools.skills_manager import delete_skill
        result = delete_skill(skill_name)
        if result.startswith("Erreur"):
            raise HTTPException(status_code=400, detail=result)
        return {"status": "success", "message": result}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.exception(f"Erreur lors de la suppression de la compétence {skill_name}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/config/tools")
async def get_config_tools() -> Dict[str, List[Dict[str, str]]]:
    """Tous les outils réellement disponibles (statiques + compétences + MCP) pour la
    checklist par agent — dynamique : tout outil enregistré apparaît automatiquement."""
    from core.swarm import AVAILABLE_TOOLS, load_dynamic_skills
    out = {}

    def add(name: str, fn: Any, category: str):
        doc = " ".join((getattr(fn, "__doc__", "") or "").strip().split())
        out[name] = {"key": name, "desc": doc[:140], "category": category}

    try:
        for n, fn in AVAILABLE_TOOLS.items():
            add(n, fn, "standard")
    except Exception as e:
        import logging
        logging.warning(f"Impossible de charger AVAILABLE_TOOLS : {e}")

    try:
        for n, fn in load_dynamic_skills().items():
            add(n, fn, "competence")
    except Exception as e:
        import logging
        logging.warning(f"Impossible de charger load_dynamic_skills : {e}")

    try:
        from tools.mcp_manager import mcp_manager
        for n, fn in mcp_manager.tool_functions().items():
            add(n, fn, "mcp")
    except Exception as e:
        import logging
        logging.warning(f"Impossible de charger mcp_manager : {e}")

    return {"tools": sorted(out.values(), key=lambda t: t["key"])}

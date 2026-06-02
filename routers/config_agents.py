import yaml
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.state import swarm, _orch_name, _orch_agent, session

router = APIRouter(tags=["Config Agents"])

@router.get("/api/config/agents")
async def get_config_agents() -> List[Dict[str, Any]]:
    try:
        with open("agents.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("agents", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de lecture de agents.yaml : {str(e)}")

class SaveAgentsRequest(BaseModel):
    agents: List[Dict[str, Any]]

@router.post("/api/config/agents")
async def save_config_agents(req: SaveAgentsRequest) -> Dict[str, str]:
    try:
        agents = req.agents or []
        if not agents:
            raise HTTPException(status_code=400, detail="Au moins un agent (l'orchestrateur) est requis.")
            
        orch = _orch_name()
        names = {a.get("name") for a in agents}
        has_orch = any(a.get("orchestrator") is True for a in agents) or (orch in names)
        
        if not has_orch:
            raise HTTPException(status_code=400, detail=(
                f"Impossible de supprimer l'orchestrateur « {orch} ». "
                "Pour le renommer, change son nom en gardant « orchestrator: true »."))
                
        with open("agents.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump({"agents": req.agents}, f, allow_unicode=True, sort_keys=False)
            
        swarm.load_agents("agents.yaml")
        
        if session.active_agent.name not in swarm.agents:
            session.active_agent = _orch_agent() or list(swarm.agents.values())[0]
            
        return {"status": "success", "message": "Configuration des agents sauvegardée et rechargée avec succès !"}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.exception("Erreur lors de la sauvegarde des agents")
        raise HTTPException(status_code=500, detail=f"Erreur de sauvegarde de agents.yaml : {str(e)}")

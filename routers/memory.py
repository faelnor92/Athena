"""Routeur : mémoire clé-valeur (/api/memory) et base de connaissances RAG
(/api/knowledge). Autonome — ne dépend que de tools.memory_tools."""
import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tools.memory_tools import core_mem

router = APIRouter()


@router.get("/api/memory")
async def get_memory():
    core_mem.load()
    return core_mem.data


@router.delete("/api/memory/{key}")
async def delete_memory_key(key: str):
    if core_mem.delete(key):
        return {"status": "success", "message": f"Clé {key} supprimée de la mémoire."}
    raise HTTPException(status_code=404, detail=f"Clé {key} introuvable dans la mémoire.")


@router.get("/api/knowledge")
async def list_knowledge(limit: int = 200):
    import tools.memory_tools as mt
    return {"count": mt.semantic_mem.count(), "documents": mt.semantic_mem.list_documents(limit)}


@router.delete("/api/knowledge/{doc_id}")
async def delete_knowledge(doc_id: str):
    import tools.memory_tools as mt
    if mt.semantic_mem.delete(doc_id):
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Document introuvable.")


class IngestRequest(BaseModel):
    url: str | None = None
    text: str | None = None
    source: str = "manuel"


@router.post("/api/knowledge/ingest")
async def ingest_knowledge(req: IngestRequest):
    import tools.memory_tools as mt
    if req.url:
        from tools.web_tools import web_scrape
        content = await asyncio.to_thread(web_scrape, req.url)
        if not content or content.startswith("Erreur"):
            raise HTTPException(status_code=400, detail=f"Impossible de récupérer la page : {content}")
        doc_id = mt.semantic_mem.store(content, source=req.url)
        return {"status": "success", "id": doc_id, "chars": len(content), "source": req.url}
    if req.text and req.text.strip():
        doc_id = mt.semantic_mem.store(req.text.strip(), source=req.source or "manuel")
        return {"status": "success", "id": doc_id, "chars": len(req.text), "source": req.source}
    raise HTTPException(status_code=400, detail="Fournis 'url' ou 'text'.")

"""Routeur : listes universelles (courses, tâches, idées) — /api/lists.
Autonome — tools.list_tools."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ListAddItemRequest(BaseModel):
    list_name: str
    text: str


@router.get("/api/lists/names")
async def get_list_names_api():
    """Tous les noms de listes existants (+ nb d'éléments) pour peupler dynamiquement
    le sélecteur de l'UI — sinon une liste créée par un agent (ex. « todo ») reste invisible."""
    from tools.list_tools import read_lists
    data = read_lists()
    return {"names": sorted(data.keys()), "counts": {k: len(v or []) for k, v in data.items()}}


@router.get("/api/lists")
async def get_lists_api(list_name: str = "taches"):
    from tools.list_tools import get_list_items
    return get_list_items(list_name)


@router.post("/api/lists")
async def add_list_item_api(req: ListAddItemRequest):
    from tools.list_tools import add_list_item
    item = add_list_item(req.list_name, req.text)
    return {"status": "success", "item": item}


@router.put("/api/lists/{list_name}/{item_id}/toggle")
async def toggle_list_item_api(list_name: str, item_id: str):
    from tools.list_tools import toggle_list_item
    if not toggle_list_item(list_name, item_id):
        raise HTTPException(status_code=404, detail="Élément introuvable.")
    return {"status": "success"}


@router.delete("/api/lists/{list_name}/{item_id}")
async def delete_list_item_api(list_name: str, item_id: str):
    from tools.list_tools import delete_list_item
    if not delete_list_item(list_name, item_id):
        raise HTTPException(status_code=404, detail="Élément introuvable.")
    return {"status": "success"}

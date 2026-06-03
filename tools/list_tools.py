import os
import json
import uuid
from typing import List, Dict, Any

from core import shared_store
from core.user_config import current_user_key, user_slug

# Listes PAR UTILISATEUR, désormais dans le store SQLite partagé (multi-worker-safe :
# lectures cohérentes + mutations atomiques). Migration douce des anciens fichiers
# workspace/lists_<user>.json au premier accès.
_NS = "lists"


def _legacy_file() -> str:
    return os.path.join("workspace", f"lists_{user_slug()}.json")


def read_lists() -> Dict[str, List[Dict[str, Any]]]:
    """Lit les listes de l'utilisateur courant (migre l'ancien fichier JSON si présent)."""
    user = current_user_key()
    data = shared_store.get(_NS, user)
    if data is None:
        data = {}
        p = _legacy_file()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
            shared_store.set(_NS, user, data)  # persiste la migration (une seule fois)
    return data if isinstance(data, dict) else {}


def write_lists(data: Dict[str, List[Dict[str, Any]]]):
    """Remplace les listes de l'utilisateur courant."""
    shared_store.set(_NS, current_user_key(), data or {})


def _mutate(fn):
    """Lecture-modification-écriture ATOMIQUE des listes de l'utilisateur courant."""
    read_lists()  # garantit la migration éventuelle avant l'update atomique
    return shared_store.update(_NS, current_user_key(), lambda d: fn(d or {}))


def add_list_item(list_name: str, item_text: str) -> Dict[str, Any]:
    """Ajoute un élément à une liste spécifique (ex: courses, taches, idees)."""
    list_name = list_name.lower().strip()
    item = {"id": uuid.uuid4().hex[:12], "text": item_text.strip(), "completed": False}

    def _add(data):
        data.setdefault(list_name, []).append(item)
        return data
    _mutate(_add)
    return item


def get_list_items(list_name: str) -> List[Dict[str, Any]]:
    """Récupère tous les éléments d'une liste spécifique."""
    return read_lists().get(list_name.lower().strip(), [])


def toggle_list_item(list_name: str, item_id: str) -> bool:
    """Coche ou décoche un élément d'une liste."""
    list_name = list_name.lower().strip()
    outcome = {"ok": False}

    def _toggle(data):
        for item in data.get(list_name, []):
            if item["id"] == item_id:
                item["completed"] = not item["completed"]
                outcome["ok"] = True
                break
        return data
    _mutate(_toggle)
    return outcome["ok"]


def delete_list_item(list_name: str, item_id: str) -> bool:
    """Supprime un élément d'une liste."""
    list_name = list_name.lower().strip()
    outcome = {"ok": False}

    def _del(data):
        if list_name in data:
            before = len(data[list_name])
            data[list_name] = [i for i in data[list_name] if i["id"] != item_id]
            outcome["ok"] = len(data[list_name]) < before
        return data
    _mutate(_del)
    return outcome["ok"]

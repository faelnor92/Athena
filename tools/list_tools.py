import os
import json
import uuid
import threading
from typing import List, Dict, Any

lists_lock = threading.Lock()

def _lists_file() -> str:
    """Fichier de listes de l'utilisateur courant (listes PAR UTILISATEUR)."""
    from core.user_config import user_slug
    return os.path.join("workspace", f"lists_{user_slug()}.json")

def ensure_lists_file():
    """ Assure que le répertoire et le fichier JSON de listes existent. """
    os.makedirs("workspace", exist_ok=True)
    with lists_lock:
        path = _lists_file()
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4, ensure_ascii=False)

def read_lists() -> Dict[str, List[Dict[str, Any]]]:
    """ Lit le contenu du fichier de listes. """
    ensure_lists_file()
    with lists_lock:
        try:
            with open(_lists_file(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

def write_lists(data: Dict[str, List[Dict[str, Any]]]):
    """ Écrit le contenu dans le fichier de listes. """
    ensure_lists_file()
    with lists_lock:
        with open(_lists_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

def add_list_item(list_name: str, item_text: str) -> Dict[str, Any]:
    """ Ajoute un élément à une liste spécifique (ex: courses, taches, idees). """
    list_name = list_name.lower().strip()
    data = read_lists()
    
    if list_name not in data:
        data[list_name] = []
        
    item = {
        "id": uuid.uuid4().hex[:12],
        "text": item_text.strip(),
        "completed": False
    }
    
    data[list_name].append(item)
    write_lists(data)
    return item

def get_list_items(list_name: str) -> List[Dict[str, Any]]:
    """ Récupère tous les éléments d'une liste spécifique. """
    list_name = list_name.lower().strip()
    data = read_lists()
    return data.get(list_name, [])

def toggle_list_item(list_name: str, item_id: str) -> bool:
    """ Coche ou décoche un élément d'une liste. """
    list_name = list_name.lower().strip()
    data = read_lists()
    
    if list_name not in data:
        return False
        
    for item in data[list_name]:
        if item["id"] == item_id:
            item["completed"] = not item["completed"]
            write_lists(data)
            return True
            
    return False

def delete_list_item(list_name: str, item_id: str) -> bool:
    """ Supprime un élément d'une liste. """
    list_name = list_name.lower().strip()
    data = read_lists()
    
    if list_name not in data:
        return False
        
    initial_len = len(data[list_name])
    data[list_name] = [item for item in data[list_name] if item["id"] != item_id]
    
    if len(data[list_name]) < initial_len:
        write_lists(data)
        return True
        
    return False

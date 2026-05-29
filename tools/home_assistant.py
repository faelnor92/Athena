import os
import requests
import json

def get_ha_headers():
    token = os.getenv("HA_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

def get_ha_state(entity_id: str) -> str:
    """
    Récupère l'état actuel d'une entité Home Assistant.
    
    Args:
        entity_id (str): L'ID de l'entité (ex: light.salon, sensor.temperature_exterieure)
        
    Returns:
        str: L'état de l'entité (ou un message d'erreur).
    """
    url = os.getenv("HA_URL")
    if not url or not os.getenv("HA_TOKEN"):
        return json.dumps({"error": "Home Assistant n'est pas configuré dans le .env."})
    
    endpoint = f"{url.rstrip('/')}/api/states/{entity_id}"
    try:
        response = requests.get(endpoint, headers=get_ha_headers())
        response.raise_for_status()
        return json.dumps(response.json())
    except Exception as e:
        return json.dumps({"error": str(e)})

def call_ha_service(domain: str, service: str, entity_id: str = None) -> str:
    """
    Appelle un service sur Home Assistant (ex: light.turn_on).
    
    Args:
        domain (str): Le domaine (ex: light, switch, script)
        service (str): Le service (ex: turn_on, turn_off, toggle)
        entity_id (str): L'ID de l'entité concernée (optionnel)
        
    Returns:
        str: Le résultat de l'opération.
    """
    url = os.getenv("HA_URL")
    if not url or not os.getenv("HA_TOKEN"):
        return json.dumps({"error": "Home Assistant n'est pas configuré dans le .env."})
    
    endpoint = f"{url.rstrip('/')}/api/services/{domain}/{service}"
    data = {}
    if entity_id:
        data["entity_id"] = entity_id
        
    try:
        response = requests.post(endpoint, headers=get_ha_headers(), json=data)
        response.raise_for_status()
        return json.dumps([r for r in response.json()]) if response.json() else "Succès"
    except Exception as e:
        return json.dumps({"error": str(e)})

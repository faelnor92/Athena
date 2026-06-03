import os
import json
import requests
import urllib.parse
from datetime import datetime
from tools.agenda_tools import load_agenda
from tools.list_tools import get_list_items

def get_daily_briefing(city: str = "Paris") -> str:
    """
    Génère un superbe bulletin quotidien de l'assistant (météo, agenda du jour, tâches).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    readable_today = datetime.now().strftime("%A %d %B %Y")
    
    briefing = f"☀️ **BRIEFING DU JOUR - {readable_today}** ☀️\n\n"
    
    # 1. METEO
    print(f"☀️ [Briefing] Récupération de la météo pour : {city}")
    try:
        # Requête wttr.in formatée
        encoded_city = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded_city}?format=%C:+%t+(ressenti+%f),+Humidité+%h,+Vent+%w"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            weather_text = r.text.strip()
            briefing += f"🌡️ **Météo à {city.capitalize()}** :\n> {weather_text}\n\n"
        else:
            briefing += f"🌡️ **Météo à {city.capitalize()}** : Indisponible temporairement.\n\n"
    except Exception as e:
        briefing += f"🌡️ **Météo à {city.capitalize()}** : Échec de la récupération ({str(e)}).\n\n"
        
    # 2. AGENDA DU JOUR (agenda de l'utilisateur courant)
    today_events = []
    try:
        events = load_agenda()
        today_events = [e for e in events if e.get("datetime", "").startswith(today_str)]
    except Exception as err:
        print(f"📅 [Briefing Erreur Agenda] {err}")
            
    briefing += "📅 **Vos Rendez-vous d'aujourd'hui** :\n"
    if today_events:
        for e in sorted(today_events, key=lambda x: x["datetime"]):
            time_part = e["datetime"].split(" ")[1]
            desc = f" - *{e['description']}*" if e.get("description") else ""
            briefing += f"- **{time_part}** : {e['title']} ({e['duration_minutes']} min){desc}\n"
    else:
        briefing += "- *Aucun événement planifié pour aujourd'hui. Profitez de votre journée libre !* 🎉\n"
        
    briefing += "\n"
    
    # 3. LISTE DE TACHES & COURSES PENDANTES
    todos = [t for t in get_list_items("taches") if not t.get("completed", False)]
    shopping = [s for s in get_list_items("courses") if not s.get("completed", False)]
    
    briefing += "📝 **Tâches prioritaires à faire** :\n"
    if todos:
        for t in todos[:5]: # Top 5 tâches
            briefing += f"- [ ] {t['text']}\n"
    else:
        briefing += "- *Aucune tâche en attente.* ✅\n"
        
    briefing += "\n"
    
    briefing += "🛒 **Liste de courses (Rappel)** :\n"
    if shopping:
        items_str = ", ".join([s['text'] for s in shopping[:8]])
        briefing += f"- *À acheter aujourd'hui :* {items_str}\n"
    else:
        briefing += "- *Rien à acheter de prévu.* 🛒\n"
        
    try:
        from core.state import _app_name
        app_name = _app_name()
    except Exception:
        app_name = os.getenv("APP_NAME", "").strip() or "Jarvis"
    briefing += f"\n*Passez une excellente journée ! {app_name} reste à votre entière disposition.* 🚀"

    return briefing

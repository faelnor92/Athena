import urllib.parse
import requests
from datetime import datetime

def get_time(timezone: str = "Europe/Paris") -> str:
    """
    Retourne l'heure et la date courante (utile pour savoir quel jour on est).
    """
    # zoneinfo = stdlib (Python ≥3.9) → pas de dépendance pytz (doctrine native>dépendance).
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return (f"Erreur : fuseau horaire inconnu '{timezone}'. "
                "Utilise un identifiant IANA, ex. 'Europe/Paris'.")
    now = datetime.now(tz)
    # Format: Lundi 03 Juin 2026, 14:15
    day_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    month_names = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    
    day_str = day_names[now.weekday()]
    month_str = month_names[now.month]
    
    readable_date = f"{day_str} {now.day:02d} {month_str} {now.year}, {now.hour:02d}:{now.minute:02d}"
    return f"Il est actuellement {readable_date} (fuseau horaire : {timezone})."

def get_weather(city: str) -> str:
    """
    Récupère la météo EXTÉRIEURE actuelle pour une ville donnée via wttr.in.
    IMPORTANT : 
    - Si l'utilisateur ne précise pas la ville, déduis-la de ses informations mémorisées (utilise search_memory si besoin).
    - Pour la température intérieure d'une pièce de la maison (ex: salon, chambre), 
      utilise plutôt l'outil `get_ha_state` avec le bon capteur domotique (ex: sensor.temperature_salon).
    """
    if not city or city.strip() == "":
        return "Erreur : Tu dois préciser une ville. Cherche dans ta mémoire la ville de l'utilisateur ou demande-lui."
    try:
        encoded_city = urllib.parse.quote(city)
        url = f"https://wttr.in/{encoded_city}?format=j1&lang=fr"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            curr = data['current_condition'][0]
            desc = curr.get('lang_fr', [{'value': curr['weatherDesc'][0]['value']}])[0]['value']
            temp = curr['temp_C']
            feels = curr['FeelsLikeC']
            hum = curr['humidity']
            wind = curr['windspeedKmph']
            
            res = f"Météo actuelle à {city.capitalize()} : {desc}, {temp}°C (ressenti {feels}°C), Humidité {hum}%, Vent {wind} km/h.\n\n"
            res += "Prévisions pour les prochains jours :\n"
            for day in data.get('weather', []):
                d = day.get('date', '')
                tmin = day.get('mintempC', '?')
                tmax = day.get('maxtempC', '?')
                try:
                    # Prendre la prévision de 12h00 (index 4 si par tranches de 3h)
                    mid_desc = day['hourly'][4].get('lang_fr', [{'value': day['hourly'][4]['weatherDesc'][0]['value']}])[0]['value']
                except Exception:
                    mid_desc = "Indisponible"
                res += f"- {d} : {mid_desc}, min {tmin}°C / max {tmax}°C\n"
                
            return res.strip()
        else:
            return f"Météo indisponible pour {city} (erreur {r.status_code})."
    except Exception as e:
        return f"Erreur lors de la récupération de la météo pour {city} : {str(e)}"

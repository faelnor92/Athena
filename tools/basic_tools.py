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

# Codes météo WMO (Open-Meteo) → description FR (concise).
_WMO = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine faible", 53: "bruine", 55: "bruine dense",
    56: "bruine verglaçante", 57: "bruine verglaçante dense",
    61: "pluie faible", 63: "pluie", 65: "pluie forte",
    66: "pluie verglaçante", 67: "pluie verglaçante forte",
    71: "neige faible", 73: "neige", 75: "neige forte", 77: "grains de neige",
    80: "averses faibles", 81: "averses", 82: "averses violentes",
    85: "averses de neige", 86: "fortes averses de neige",
    95: "orage", 96: "orage avec grêle", 99: "orage avec forte grêle",
}


def _geocode(city: str):
    """Ville → (lat, lon, libellé) via le géocodage Open-Meteo (gratuit, sans clé). None sinon."""
    try:
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1, "language": "fr", "format": "json"},
                         timeout=8)
        res = (r.json() or {}).get("results") if r.status_code == 200 else None
        if res:
            g = res[0]
            label = g.get("name", city)
            if g.get("admin1"):
                label += f" ({g['admin1']})"
            return float(g["latitude"]), float(g["longitude"]), label
    except Exception:
        pass
    return None


def _resolve_coords(city: str):
    """Coordonnées hyperlocales : ville passée → géocodage ; sinon WEATHER_LAT/LON de la config
    (position précise du compte) ; sinon géocodage de la ville configurée. Renvoie (lat,lon,label)."""
    if (city or "").strip():
        g = _geocode(city.strip())
        return g or (None, None, city)
    # Pas de ville → position précise du compte (hyperlocal), sinon ville configurée.
    cfg = {}
    try:
        from core import user_config
        cfg = user_config.get_all() or {}
    except Exception:
        cfg = {}
    import os as _os
    lat = (str(cfg.get("WEATHER_LAT") or "").strip() or _os.getenv("WEATHER_LAT", "").strip())
    lon = (str(cfg.get("WEATHER_LON") or "").strip() or _os.getenv("WEATHER_LON", "").strip())
    if lat and lon:
        try:
            return float(lat), float(lon), (str(cfg.get("WEATHER_CITY") or "").strip() or "ma position")
        except ValueError:
            pass
    try:
        from tools.briefing_tools import _resolve_city
        c = _resolve_city()
        if c:
            g = _geocode(c)
            if g:
                return g
    except Exception:
        pass
    return (None, None, "")


def get_weather(city: str = "") -> str:
    """
    Météo EXTÉRIEURE actuelle + prévisions, HYPERLOCALE (par coordonnées, via Open-Meteo).
    - Ville passée → géocodée précisément. Vide → position du compte (WEATHER_LAT/LON) ou ville
      configurée. Pour la position exacte (quartier), renseigne WEATHER_LAT/WEATHER_LON.
    - Température INTÉRIEURE d'une pièce → utilise `get_ha_state` (capteur domotique), pas cet outil.
    """
    lat, lon, label = _resolve_coords(city)
    if lat is None:
        return ("Erreur : aucune localisation. Précise une ville, ou configure WEATHER_LAT/WEATHER_LON "
                "(position précise) ou WEATHER_CITY dans le compte.")
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 4,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        }, timeout=8)
        if r.status_code != 200:
            return f"Météo indisponible pour {label} (erreur {r.status_code})."
        data = r.json()
        cur = data.get("current", {})
        desc = _WMO.get(int(cur.get("weather_code", -1)), "conditions inconnues")
        res = (f"Météo actuelle à {label} : {desc}, {cur.get('temperature_2m','?')}°C "
               f"(ressenti {cur.get('apparent_temperature','?')}°C), humidité {cur.get('relative_humidity_2m','?')}%, "
               f"vent {cur.get('wind_speed_10m','?')} km/h.\n\nPrévisions :\n")
        daily = data.get("daily", {})
        days = daily.get("time", []) or []
        for i, d in enumerate(days):
            dd = _WMO.get(int((daily.get("weather_code") or [None])[i] or -1), "?")
            tmin = (daily.get("temperature_2m_min") or [None])[i]
            tmax = (daily.get("temperature_2m_max") or [None])[i]
            pp = (daily.get("precipitation_probability_max") or [None])[i]
            rain = f", pluie {pp}%" if pp is not None else ""
            res += f"- {d} : {dd}, min {tmin}°C / max {tmax}°C{rain}\n"
        return res.strip()
    except Exception as e:  # noqa: BLE001
        return f"Erreur lors de la récupération de la météo pour {label} : {e}"

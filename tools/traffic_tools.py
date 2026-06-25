"""Trafic ROUTIER (voiture) en temps réel : temps de trajet avec embouteillages + incidents.

Utilise **TomTom** (routing traffic-aware + incidents), clé gratuite : https://developer.tomtom.com/
→ `TOMTOM_API_KEY`. Lecture seule ; réponse = donnée non fiable ; dégradation propre sans clé.
"""
import os
import urllib.parse
import requests

_TIMEOUT = 8


def _key() -> str:
    try:
        from core import user_config
        cfg = user_config.get_all() or {}
        v = (cfg.get("TOMTOM_API_KEY") or "").strip()
        if v:
            return v
    except Exception:
        pass
    return os.getenv("TOMTOM_API_KEY", "").strip()


def _geocode(query: str, key: str):
    """Adresse/lieu → (lat, lon, libellé) via TomTom Search. None sinon."""
    try:
        url = f"https://api.tomtom.com/search/2/geocode/{urllib.parse.quote(query)}.json"
        r = requests.get(url, params={"key": key, "limit": 1}, timeout=_TIMEOUT)
        res = (r.json() or {}).get("results") if r.status_code == 200 else None
        if res:
            p = res[0]
            pos = p.get("position") or {}
            label = (p.get("address") or {}).get("freeformAddress", query)
            return float(pos["lat"]), float(pos["lon"]), label
    except Exception:
        pass
    return None


def _fmt_min(seconds) -> str:
    try:
        m = int(round(int(seconds) / 60))
        if m >= 60:
            return f"{m // 60} h {m % 60:02d}"
        return f"{m} min"
    except Exception:
        return "?"


def get_driving_route(origin: str, destination: str) -> str:
    """Durée et distance d'un trajet EN VOITURE entre deux lieux — « combien de temps / quelle distance pour aller de A à B en voiture » — avec trafic temps réel et retards dus aux embouteillages.

    origin / destination : adresses ou lieux (ex. « Strasbourg » → « Aéroport d'Entzheim »).
    Renvoie distance, durée actuelle (trafic inclus), retard vs circulation fluide et arrivée estimée.
    """
    if not (origin or "").strip() or not (destination or "").strip():
        return "🚗 Indique un point de départ ET une destination."
    key = _key()
    if not key:
        return ("🚗 Aucune clé TomTom configurée. Crée-en une (gratuite) sur "
                "https://developer.tomtom.com/ puis renseigne `TOMTOM_API_KEY`.")
    o = _geocode(origin, key)
    d = _geocode(destination, key)
    if not o:
        return f"🚗 Départ introuvable : « {origin} »."
    if not d:
        return f"🚗 Destination introuvable : « {destination} »."
    try:
        loc = f"{o[0]},{o[1]}:{d[0]},{d[1]}"
        url = f"https://api.tomtom.com/routing/1/calculateRoute/{loc}/json"
        r = requests.get(url, params={"key": key, "traffic": "true", "travelMode": "car"},
                         timeout=_TIMEOUT)
        if r.status_code == 403:
            return "🚗 Clé TomTom refusée (403) — vérifie `TOMTOM_API_KEY`."
        if r.status_code != 200:
            return f"🚗 Trafic indisponible (HTTP {r.status_code})."
        routes = (r.json() or {}).get("routes") or []
        if not routes:
            return f"🚗 Aucun itinéraire routier de « {o[2]} » à « {d[2]} »."
        s = routes[0].get("summary") or {}
        km = (s.get("lengthInMeters", 0) or 0) / 1000.0
        delay = int(s.get("trafficDelayInSeconds", 0) or 0)
        out = [f"🚗 **Trajet voiture — {o[2]} → {d[2]}**",
               f"- Distance : {km:.1f} km",
               f"- Durée actuelle (trafic) : {_fmt_min(s.get('travelTimeInSeconds'))}"]
        if delay > 60:
            out.append(f"- ⚠️ Embouteillages : +{_fmt_min(delay)} vs fluide")
        elif s.get("noTrafficTravelTimeInSeconds"):
            out.append("- ✅ Circulation fluide")
        arr = s.get("arrivalTime")
        if arr:
            out.append(f"- Arrivée estimée : {arr[11:16]}")
        return "\n".join(out)
    except requests.Timeout:
        return "🚗 Trafic : délai dépassé."
    except Exception as e:  # noqa: BLE001
        return f"🚗 Trafic : échec ({e})."


def get_traffic_incidents(area: str) -> str:
    """Incidents/bouchons routiers EN COURS autour d'un lieu (accidents, travaux, ralentissements).

    area : ville/lieu (ex. « Strasbourg »). On scrute une zone d'environ 15 km autour.
    """
    if not (area or "").strip():
        return "🚧 Précise un lieu (ex. « incidents routiers à Strasbourg »)."
    key = _key()
    if not key:
        return ("🚧 Aucune clé TomTom configurée (https://developer.tomtom.com/ → `TOMTOM_API_KEY`).")
    g = _geocode(area, key)
    if not g:
        return f"🚧 Lieu introuvable : « {area} »."
    lat, lon, label = g
    # Boîte ~0.15° (~15 km) autour du point. bbox = minLon,minLat,maxLon,maxLat
    bbox = f"{lon-0.15},{lat-0.15},{lon+0.15},{lat+0.15}"
    try:
        url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
        params = {"key": key, "bbox": bbox, "language": "fr-FR",
                  "fields": "{incidents{type,properties{iconCategory,events{description}}}}"}
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code != 200:
            return f"🚧 Incidents indisponibles (HTTP {r.status_code})."
        inc = (r.json() or {}).get("incidents") or []
        if not inc:
            return f"🚧 Aucun incident routier signalé autour de « {label} »."
        out = [f"🚧 **Incidents routiers — {label}** :"]
        for it in inc[:10]:
            evts = ((it.get("properties") or {}).get("events") or [])
            desc = (evts[0].get("description") if evts else "") or "incident"
            out.append(f"• {desc}")
        return "\n".join(out)
    except requests.Timeout:
        return "🚧 Incidents : délai dépassé."
    except Exception as e:  # noqa: BLE001
        return f"🚧 Incidents : échec ({e})."


def driving_minutes(origin: str, destination: str):
    """Durée d'un trajet voiture (trafic inclus) en MINUTES, exploitable programmatiquement.
    Renvoie (minutes:int, retard_min:int) ou None si indisponible (pas de clé, lieu introuvable,
    erreur réseau). Usage interne : alertes de départ du briefing."""
    key = _key()
    if not key or not (origin or "").strip() or not (destination or "").strip():
        return None
    o = _geocode(origin, key)
    d = _geocode(destination, key)
    if not o or not d:
        return None
    try:
        loc = f"{o[0]},{o[1]}:{d[0]},{d[1]}"
        url = f"https://api.tomtom.com/routing/1/calculateRoute/{loc}/json"
        r = requests.get(url, params={"key": key, "traffic": "true", "travelMode": "car"},
                         timeout=_TIMEOUT)
        if r.status_code != 200:
            return None
        routes = (r.json() or {}).get("routes") or []
        if not routes:
            return None
        s = routes[0].get("summary") or {}
        sec = int(s.get("travelTimeInSeconds", 0) or 0)
        if sec <= 0:
            return None
        return (round(sec / 60), round(int(s.get("trafficDelayInSeconds", 0) or 0) / 60))
    except Exception:  # noqa: BLE001
        return None

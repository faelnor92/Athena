"""Transports en commun en TEMPS RÉEL (départs, retards, perturbations, itinéraires) — PLUGGABLE.

Fournisseurs (`TRANSPORT_PROVIDER`) :
- **navitia** : excellent pour la FRANCE (SNCF + réseaux urbains type CTS Strasbourg), itinéraires
  point-à-point. Clé `NAVITIA_API_KEY` (navitia.io). Endpoint surchargeable via `NAVITIA_API_BASE`
  (ex. l'API SNCF, même format, ou un Navitia auto-hébergé).
- **transitland** : couverture MONDIALE (agrège les GTFS de nombreux pays), clé gratuite instantanée.
  Clé `TRANSITLAND_API_KEY` (transit.land). Départs + retards ; pas de planificateur d'itinéraire.
- **auto** (défaut) : transitland si sa clé est posée, sinon navitia.

Doctrine : lecture seule ; réponse = donnée non fiable ; dégradation propre sans clé.
"""
import os
import requests

_TIMEOUT = 8


def _cfg(name: str) -> str:
    """Valeur de config : compte courant d'abord, puis environnement."""
    try:
        from core import user_config
        v = (user_config.get_all() or {}).get(name)
        if v and str(v).strip():
            return str(v).strip()
    except Exception:
        pass
    return os.getenv(name, "").strip()


def _provider() -> str:
    """Fournisseur actif : explicite (navitia/transitland) sinon auto (transitland si clé, sinon navitia)."""
    p = (_cfg("TRANSPORT_PROVIDER") or "auto").lower()
    if p in ("navitia", "transitland"):
        return p
    if _cfg("TRANSITLAND_API_KEY"):
        return "transitland"
    return "navitia"


# ───────────────────────────── Backend NAVITIA (France) ─────────────────────────────
def _nav_get(path: str, params: dict = None):
    key = _cfg("NAVITIA_API_KEY") or _cfg("NAVITIA_KEY")
    if not key:
        return None, ("Aucune clé Navitia configurée. Clé gratuite sur https://navitia.io/ puis "
                      "renseigne `NAVITIA_API_KEY` (Réglages → Intégrations externes).")
    base = (_cfg("NAVITIA_API_BASE") or "https://api.navitia.io/v1").rstrip("/")
    try:
        r = requests.get(f"{base}/{path.lstrip('/')}", params=params or {}, auth=(key, ""), timeout=_TIMEOUT)
        if r.status_code == 401:
            return None, "Clé Navitia refusée (401) — vérifie `NAVITIA_API_KEY`."
        if r.status_code == 404:
            return None, "Aucun résultat (404) — lieu/ligne introuvable ou hors couverture."
        if r.status_code != 200:
            return None, f"API transport indisponible (HTTP {r.status_code})."
        return r.json(), None
    except requests.Timeout:
        return None, "API transport : délai dépassé."
    except Exception as e:  # noqa: BLE001
        return None, f"API transport : échec ({e})."


def _nav_resolve_place(query: str, stop_area_only: bool = False):
    """Résout un lieu (arrêt, adresse, ville, POI) → {id, label, region, coord}. None si introuvable."""
    params = {"q": query, "count": 1}
    if stop_area_only:
        params["type[]"] = "stop_area"
    data, err = _nav_get("places", params)
    if err or not data:
        return None, err
    places = data.get("places") or []
    if not places:
        return None, f"Lieu « {query} » introuvable."
    p = places[0]
    emb = p.get("embedded_type") or ""
    coord = ((p.get(emb) or {}).get("coord")) or {}
    region = None
    try:
        lon, lat = coord.get("lon"), coord.get("lat")
        if lon and lat:
            rdata, _ = _nav_get(f"coord/{lon};{lat}")
            regs = (rdata or {}).get("regions") or []
            if regs:
                region = regs[0]
    except Exception:
        pass
    return {"id": p.get("id"), "label": p.get("name") or query, "region": region, "coord": coord}, None


def _hms_to_min(base: str, real: str) -> int:
    """Retard en minutes (format Navitia YYYYMMDDTHHMMSS)."""
    try:
        from datetime import datetime
        fmt = "%Y%m%dT%H%M%S"
        return int((datetime.strptime(real, fmt) - datetime.strptime(base, fmt)).total_seconds() // 60)
    except Exception:
        return 0


def _nav_departures(stop: str, limit: int = 8) -> str:
    info, err = _nav_resolve_place(stop, stop_area_only=True)
    if err:
        return f"🚏 {err}"
    region = info.get("region")
    if not region:
        return (f"🚏 Arrêt « {info['label']} » trouvé mais sa région Navitia n'a pu être résolue "
                "(temps réel indisponible ici).")
    data, err = _nav_get(f"coverage/{region}/stop_areas/{info['id']}/departures",
                         {"data_freshness": "realtime", "count": max(1, min(int(limit or 8), 20))})
    if err:
        return f"🚏 {err}"
    deps = (data or {}).get("departures") or []
    if not deps:
        return f"🚏 Aucun départ prévu prochainement à « {info['label']} »."
    lines = [f"🚏 **Prochains départs — {info['label']}** (temps réel) :"]
    for d in deps:
        st = d.get("stop_date_time") or {}
        di = d.get("display_informations") or {}
        line = (di.get("code") or di.get("label") or di.get("commercial_mode") or "?").strip()
        direction = (di.get("direction") or "").strip()
        base = st.get("base_departure_date_time") or ""
        real = st.get("departure_date_time") or ""
        hhmm = (real[9:11] + ":" + real[11:13]) if len(real) >= 13 else "?"
        status = ""
        if (st.get("data_freshness") == "realtime") and base and real:
            dm = _hms_to_min(base, real)
            status = f" ⚠️ +{dm} min" if dm > 0 else (" ✅ à l'heure" if dm == 0 else "")
        lines.append(f"• {hhmm} — {line} → {direction}{status}")
    return "\n".join(lines)


def _nav_disruptions(area: str = "") -> str:
    q = (area or "").strip()
    if not q:
        try:
            from tools.briefing_tools import _resolve_city
            q = _resolve_city()
        except Exception:
            q = ""
    if not q:
        return "🚧 Précise un réseau/une ville (ex. « perturbations à Strasbourg »)."
    info, err = _nav_resolve_place(q)
    region = info.get("region") if info and not err else None
    data, err = _nav_get(f"coverage/{region}/disruptions" if region else "disruptions", {"count": 15})
    if err:
        return f"🚧 {err}"
    active = [d for d in ((data or {}).get("disruptions") or []) if d.get("status") == "active"]
    if not active:
        return f"🚧 Aucune perturbation active signalée pour « {q} »."
    import re as _re
    lines = [f"🚧 **Perturbations en cours — {q}** :"]
    for d in active[:10]:
        sev = ((d.get("severity") or {}).get("name") or "").strip()
        msgs = d.get("messages") or []
        txt = _re.sub(r"<[^>]+>", " ", (msgs[0].get("text") if msgs else "") or "").strip()
        lines.append(f"• {('[' + sev + '] ') if sev else ''}{txt[:240] or '(détail non fourni)'}")
    return "\n".join(lines)


def _nav_journey(origin: str, destination: str) -> str:
    o, e1 = _nav_resolve_place(origin)
    d, e2 = _nav_resolve_place(destination)
    if e1 or not o:
        return f"🧭 Départ : {e1 or 'introuvable'}"
    if e2 or not d:
        return f"🧭 Destination : {e2 or 'introuvable'}"
    data, err = _nav_get("journeys", {"from": o["id"], "to": d["id"], "data_freshness": "realtime", "count": 2})
    if err:
        return f"🧭 {err}"
    journeys = (data or {}).get("journeys") or []
    if not journeys:
        return f"🧭 Aucun itinéraire trouvé de « {o['label']} » à « {d['label']} »."
    out = [f"🧭 **Itinéraire — {o['label']} → {d['label']}** :"]
    for j in journeys[:2]:
        dep = (j.get("departure_date_time") or "")[9:13]
        arr = (j.get("arrival_date_time") or "")[9:13]
        dur = int((j.get("duration") or 0) // 60)
        nb = j.get("nb_transfers", 0)
        dep_s = f"{dep[:2]}:{dep[2:]}" if len(dep) == 4 else "?"
        arr_s = f"{arr[:2]}:{arr[2:]}" if len(arr) == 4 else "?"
        modes = [c for c in ((s.get("display_informations") or {}).get("code", "")
                             for s in (j.get("sections") or [])) if c]
        status = " ⚠️ perturbé" if j.get("status") in ("SIGNIFICANT_DELAYS", "NO_SERVICE", "REDUCED_SERVICE") else ""
        out.append(f"• {dep_s} → {arr_s} ({dur} min, {nb} corresp.){(' via ' + ' / '.join(modes)) if modes else ''}{status}")
    return "\n".join(out)


# ─────────────────────────── Backend TRANSITLAND (mondial) ───────────────────────────
def _tl_timeout() -> int:
    # Transitland (free tier) est SENSIBLEMENT plus lent que Navitia, surtout /departures
    # (interroge le temps réel sur les flux GTFS-RT) → timeout plus large, configurable.
    try:
        return int(os.getenv("TRANSITLAND_TIMEOUT", "20") or 20)
    except ValueError:
        return 20


def _tl_get(path: str, params: dict = None):
    key = _cfg("TRANSITLAND_API_KEY")
    if not key:
        return None, ("Aucune clé Transitland configurée. Clé gratuite instantanée sur "
                      "https://www.transit.land/ puis renseigne `TRANSITLAND_API_KEY`.")
    base = (_cfg("TRANSITLAND_API_BASE") or "https://transit.land/api/v2/rest").rstrip("/")
    p = dict(params or {})
    p["apikey"] = key
    try:
        r = requests.get(f"{base}/{path.lstrip('/')}", params=p, timeout=_tl_timeout())
        if r.status_code in (401, 403):
            return None, "Clé Transitland refusée (401/403) — vérifie `TRANSITLAND_API_KEY`."
        if r.status_code != 200:
            return None, f"API Transitland indisponible (HTTP {r.status_code})."
        return r.json(), None
    except requests.Timeout:
        return None, "API Transitland : délai dépassé."
    except Exception as e:  # noqa: BLE001
        return None, f"API Transitland : échec ({e})."


def _tl_find_stop(query: str):
    data, err = _tl_get("stops", {"search": query, "limit": 1})
    if err:
        return None, err
    stops = (data or {}).get("stops") or []
    if not stops:
        return None, f"Arrêt « {query} » introuvable."
    s = stops[0]
    return {"id": s.get("onestop_id"), "label": s.get("stop_name") or query}, None


def _hms_diff_min(a: str, b: str) -> int:
    def _s(t):
        parts = (t or "").split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)
    try:
        return (_s(b) - _s(a)) // 60
    except Exception:
        return 0


def _tl_departures(stop: str, limit: int = 8) -> str:
    info, err = _tl_find_stop(stop)
    if err:
        return f"🚏 {err}"
    data, err = _tl_get(f"stops/{info['id']}/departures", {"limit": max(1, min(int(limit or 8), 20))})
    if err:
        return f"🚏 {err}"
    stops = (data or {}).get("stops") or []
    deps = (stops[0].get("departures") if stops else []) or []
    if not deps:
        return f"🚏 Aucun départ prochain à « {info['label']} »."
    lines = [f"🚏 **Prochains départs — {info['label']}** (temps réel) :"]
    for d in deps:
        dep = d.get("departure") or {}
        trip = d.get("trip") or {}
        route = trip.get("route") or {}
        line = (route.get("route_short_name") or route.get("route_long_name") or "?")
        head = (trip.get("trip_headsign") or "").strip()
        sched = dep.get("scheduled") or ""
        est = dep.get("estimated") or ""
        hhmm = (est or sched)[:5] or "?"
        delay = dep.get("delay")
        if delay is None and sched and est:
            delay = _hms_diff_min(sched, est) * 60
        status = ""
        if isinstance(delay, (int, float)):
            dm = int(delay // 60)
            status = f" ⚠️ +{dm} min" if dm > 0 else (" ✅ à l'heure" if est else "")
        lines.append(f"• {hhmm} — {line} → {head}{status}")
    return "\n".join(lines)


def _tl_disruptions(area: str = "") -> str:
    return ("🚧 Les perturbations détaillées ne sont pas exposées par Transitland — mais les RETARDS "
            "apparaissent directement dans les prochains départs (heure réelle vs théorique). Pour une "
            "liste de perturbations, utilise TRANSPORT_PROVIDER=navitia (France).")


# ───────────────────────────── Outils publics (dispatch) ─────────────────────────────
def get_next_departures(stop: str, limit: int = 8) -> str:
    """Prochains départs en TEMPS RÉEL à un arrêt/gare, avec retards et suppressions.

    stop : nom de l'arrêt/gare (ex. « Strasbourg Homme de Fer », « Gare de Strasbourg »).
    limit : nombre de départs (défaut 8). Fonctionne en France (Navitia) et à l'étranger (Transitland).
    """
    return _tl_departures(stop, limit) if _provider() == "transitland" else _nav_departures(stop, limit)


def get_disruptions(area: str = "") -> str:
    """Perturbations/retards EN COURS sur un réseau ou une zone (travaux, incidents, suppressions).

    area : ville/réseau/ligne (ex. « Strasbourg »). Vide = zone de l'utilisateur.
    """
    return _tl_disruptions(area) if _provider() == "transitland" else _nav_disruptions(area)


def get_journey(origin: str, destination: str) -> str:
    """Itinéraire en transports en commun entre deux lieux, avec horaires et perturbations temps réel.

    origin / destination : adresses ou arrêts. NB : nécessite Navitia (la planification point-à-point
    n'est pas fournie par Transitland).
    """
    if not (origin or "").strip() or not (destination or "").strip():
        return "🧭 Indique un point de départ ET une destination."
    if _provider() == "transitland":
        return ("🧭 La planification d'itinéraire point-à-point n'est pas disponible via Transitland "
                "(données d'arrêts/passages seulement). Utilise get_next_departures, ou configure "
                "TRANSPORT_PROVIDER=navitia pour les itinéraires complets.")
    return _nav_journey(origin, destination)

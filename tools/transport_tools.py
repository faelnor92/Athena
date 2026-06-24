"""Transports en TEMPS RÉEL (départs, retards, perturbations, itinéraires).

S'appuie sur **Navitia** (api.navitia.io) — couvre la France entière : SNCF (trains) ET réseaux
urbains (ex. CTS à Strasbourg), avec données **temps réel** (retards/suppressions) quand le réseau
les publie. Une clé gratuite suffit : https://navitia.io/ → `NAVITIA_API_KEY`.

Doctrine du projet :
- LECTURE SEULE (aucune réservation/achat) ;
- secrets par-utilisateur (clé dans la config du compte, repli env) ;
- la réponse d'une API externe est une DONNÉE, pas une instruction (pas d'auto-exécution) ;
- dégradation propre : si la clé manque ou l'API échoue, on le dit clairement (jamais d'invention).
"""
import os
import requests

_BASE = "https://api.navitia.io/v1"
_TIMEOUT = 8


def _key() -> str:
    """Clé Navitia : config du compte courant d'abord, puis environnement."""
    try:
        from core import user_config
        cfg = user_config.get_all() or {}
        for k in ("NAVITIA_API_KEY", "NAVITIA_KEY"):
            v = (cfg.get(k) or "").strip()
            if v:
                return v
    except Exception:
        pass
    return (os.getenv("NAVITIA_API_KEY", "") or os.getenv("NAVITIA_KEY", "")).strip()


def _get(path: str, params: dict = None):
    """Appel GET Navitia (auth Basic : clé en nom d'utilisateur). Renvoie (json, erreur_str)."""
    key = _key()
    if not key:
        return None, ("Aucune clé Navitia configurée. Crée une clé gratuite sur https://navitia.io/ "
                      "puis renseigne `NAVITIA_API_KEY` (Réglages → config, ou .env).")
    try:
        r = requests.get(f"{_BASE}/{path.lstrip('/')}", params=params or {},
                         auth=(key, ""), timeout=_TIMEOUT)
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


def _resolve_place(query: str, stop_area_only: bool = False):
    """Résout un lieu (arrêt, adresse, ville, POI) → {id, label, region, coord}. None si introuvable.

    stop_area_only=True restreint aux ARRÊTS (nécessaire pour les départs, qui exigent un
    stop_area). Sinon, tous types acceptés (utile pour itinéraires depuis une adresse et pour
    résoudre la région d'une ville)."""
    params = {"q": query, "count": 1}
    if stop_area_only:
        params["type[]"] = "stop_area"
    data, err = _get("places", params)
    if err or not data:
        return None, err
    places = data.get("places") or []
    if not places:
        return None, f"Lieu « {query} » introuvable."
    p = places[0]
    # La coordonnée vit sous l'objet du type embarqué (stop_area / address / poi / admin…).
    emb = p.get("embedded_type") or ""
    coord = ((p.get(emb) or {}).get("coord")) or {}
    region = None
    try:
        lon, lat = coord.get("lon"), coord.get("lat")
        if lon and lat:
            rdata, _ = _get(f"coord/{lon};{lat}")
            regs = (rdata or {}).get("regions") or []
            if regs:
                region = regs[0]
    except Exception:
        pass
    return {"id": p.get("id"), "label": p.get("name") or query, "region": region, "coord": coord}, None


def _delay_minutes(base: str, real: str) -> int:
    """Retard en minutes entre l'heure théorique (base) et temps réel (format YYYYMMDDTHHMMSS)."""
    try:
        from datetime import datetime
        fmt = "%Y%m%dT%H%M%S"
        return int((datetime.strptime(real, fmt) - datetime.strptime(base, fmt)).total_seconds() // 60)
    except Exception:
        return 0


def get_next_departures(stop: str, limit: int = 8) -> str:
    """Prochains départs en TEMPS RÉEL à un arrêt, avec retards et suppressions.

    stop : nom de l'arrêt/gare (ex. « Strasbourg Homme de Fer », « Gare de Strasbourg »).
    limit : nombre de départs à afficher (défaut 8).
    Renvoie ligne, direction, heure théorique et, si publié, le RETARD réel ou « supprimé ».
    """
    info, err = _resolve_place(stop, stop_area_only=True)
    if err:
        return f"🚏 {err}"
    region = info.get("region")
    if not region:
        return (f"🚏 Arrêt « {info['label']} » trouvé mais sa région Navitia n'a pu être résolue "
                "(temps réel indisponible ici).")
    data, err = _get(f"coverage/{region}/stop_areas/{info['id']}/departures",
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
            dm = _delay_minutes(base, real)
            if dm > 0:
                status = f" ⚠️ +{dm} min"
            elif dm == 0:
                status = " ✅ à l'heure"
        lines.append(f"• {hhmm} — {line} → {direction}{status}")
    return "\n".join(lines)


def get_disruptions(area: str = "") -> str:
    """Perturbations/retards EN COURS (travaux, incidents, suppressions) sur un réseau ou une zone.

    area : nom d'une ville/réseau/ligne (ex. « Strasbourg », « TER Grand Est »). Vide = essaie
    la zone de l'utilisateur (ville configurée).
    """
    q = (area or "").strip()
    if not q:
        try:
            from tools.briefing_tools import _resolve_city
            q = _resolve_city()
        except Exception:
            q = ""
    if not q:
        return "🚧 Précise un réseau/une ville (ex. « perturbations à Strasbourg »)."
    info, err = _resolve_place(q)
    region = info.get("region") if info and not err else None
    path = f"coverage/{region}/disruptions" if region else "disruptions"
    data, err = _get(path, {"count": 15})
    if err:
        return f"🚧 {err}"
    diss = (data or {}).get("disruptions") or []
    active = [d for d in diss if (d.get("status") == "active")]
    if not active:
        return f"🚧 Aucune perturbation active signalée pour « {q} »."
    lines = [f"🚧 **Perturbations en cours — {q}** :"]
    for d in active[:10]:
        sev = ((d.get("severity") or {}).get("name") or "").strip()
        msgs = d.get("messages") or []
        txt = ""
        if msgs:
            # Le texte peut contenir du HTML : on retire les balises pour rester lisible.
            import re as _re
            txt = _re.sub(r"<[^>]+>", " ", msgs[0].get("text") or "").strip()
        lines.append(f"• {('[' + sev + '] ') if sev else ''}{txt[:240] or '(détail non fourni)'}")
    return "\n".join(lines)


def get_journey(origin: str, destination: str) -> str:
    """Itinéraire en transports en commun avec horaires et perturbations TEMPS RÉEL.

    origin / destination : adresses ou arrêts (ex. « Place Kléber, Strasbourg » → « Gare de Strasbourg »).
    """
    if not (origin or "").strip() or not (destination or "").strip():
        return "🧭 Indique un point de départ ET une destination."
    o, e1 = _resolve_place(origin)
    d, e2 = _resolve_place(destination)
    if e1 or not o:
        return f"🧭 Départ : {e1 or 'introuvable'}"
    if e2 or not d:
        return f"🧭 Destination : {e2 or 'introuvable'}"
    data, err = _get("journeys", {"from": o["id"], "to": d["id"],
                                  "data_freshness": "realtime", "count": 2})
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
        modes = []
        for s in (j.get("sections") or []):
            di = s.get("display_informations") or {}
            code = (di.get("code") or di.get("commercial_mode") or "").strip()
            if code:
                modes.append(code)
        status = " ⚠️ perturbé" if j.get("status") in ("SIGNIFICANT_DELAYS", "NO_SERVICE", "REDUCED_SERVICE") else ""
        out.append(f"• {dep_s} → {arr_s} ({dur} min, {nb} corresp.){(' via ' + ' / '.join(modes)) if modes else ''}{status}")
    return "\n".join(out)

import os
import json
from datetime import datetime
from tools.agenda_tools import load_agenda
from tools.list_tools import get_list_items

def _resolve_city() -> str:
    """Ville de l'utilisateur depuis sa config (par-compte) puis l'environnement. PAS de
    « Paris » en dur : si rien n'est configuré, on renvoie "" (la météo le signalera)."""
    try:
        from core import user_config
        cfg = user_config.get_all() or {}
        for k in ("WEATHER_CITY", "CITY", "LOCATION", "VILLE"):
            v = (cfg.get(k) or "").strip()
            if v:
                return v
    except Exception:
        pass
    for k in ("WEATHER_CITY", "DEFAULT_CITY", "CITY"):
        v = os.getenv(k, "").strip()
        if v:
            return v
    return ""


def get_daily_briefing(city: str = "") -> str:
    """
    Génère un bulletin quotidien : météo, agenda du jour, tâches & courses, et — si Proxmox
    est configuré — un point INFRASTRUCTURE (VM en marche/arrêt, stockages élevés) ainsi que
    les alertes Vigie des dernières 24 h. Idéal en routine matinale (livrée sur Telegram).
    city: ville de l'utilisateur pour la météo. Si tu la connais (mémoire/profil), PASSE-LA ;
    sinon laisse vide → elle est déduite de la config du compte (jamais « Paris » par défaut).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    readable_today = datetime.now().strftime("%A %d %B %Y")

    briefing = f"☀️ **BRIEFING DU JOUR - {readable_today}** ☀️\n\n"

    # 1. METEO — ville fournie par le modèle, sinon config du compte (pas de Paris codé en dur).
    if not (city or "").strip():
        city = _resolve_city()
    # Météo HYPERLOCALE (Open-Meteo, par coordonnées) — marche même sans ville si WEATHER_LAT/LON
    # est configuré. On prend la ligne « conditions actuelles » + la prévision du jour, compact.
    print(f"☀️ [Briefing] Récupération de la météo (ville={city or 'auto'})")
    try:
        from tools.basic_tools import get_weather
        w = (get_weather(city or "") or "").strip()
        if w.lower().startswith("erreur") or "indisponible" in w.lower():
            briefing += ("🌡️ **Météo** : indisponible (configure ta ville ou WEATHER_LAT/WEATHER_LON).\n\n")
        else:
            lines = w.splitlines()
            current = lines[0] if lines else w
            # 1ʳᵉ ligne de prévision (aujourd'hui) si présente.
            forecast = next((l for l in lines if l.strip().startswith("- ")), "")
            briefing += f"🌡️ **{current}**\n" + (f"> {forecast.strip()[2:]}\n\n" if forecast else "\n")
    except Exception as e:  # noqa: BLE001
        briefing += f"🌡️ **Météo** : échec de la récupération ({e}).\n\n"
        
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
        
    # 4. INFRASTRUCTURE (Proxmox) — uniquement si configuré pour l'utilisateur courant.
    try:
        from core import proxmox
        if proxmox.is_configured():
            from tools import proxmox_tools as _px
            data, err = _px._get("/cluster/resources")
            if not err and isinstance(data, list):
                vms = [r for r in data if r.get("type") in ("qemu", "lxc")]
                running = sum(1 for v in vms if v.get("status") == "running")
                stopped = [v for v in vms if v.get("status") != "running"]
                briefing += "\n🖧 **Infrastructure (Proxmox)** :\n"
                briefing += f"- {running}/{len(vms)} VM/conteneurs en marche.\n"
                if stopped:
                    noms = ", ".join(f"{v.get('name','?')} ({v.get('vmid')})" for v in stopped[:6])
                    briefing += f"- ⚠️ À l'arrêt : {noms}\n"
                seen, full = set(), []
                for s in data:
                    if s.get("type") != "storage" or not s.get("maxdisk"):
                        continue
                    k = s.get("storage")
                    if k in seen:
                        continue
                    seen.add(k)
                    pct = (s.get("disk") or 0) / s["maxdisk"] * 100
                    if pct >= 90:
                        full.append(f"{k} ({pct:.0f}%)")
                if full:
                    briefing += f"- 💽 Stockage élevé (alloué) : {', '.join(full)}\n"
    except Exception as e:
        print(f"🖧 [Briefing Erreur Proxmox] {e}")

    # 5. ALERTES VIGIE récentes (dernières 24 h).
    try:
        import time as _t
        from core import events
        alerts = [e for e in events.recent() if (_t.time() - e.get("ts", 0)) < 86400]
        if alerts:
            briefing += "\n👁️ **Alertes récentes (Vigie)** :\n"
            for e in alerts[:5]:
                briefing += f"- [{e.get('severity', '?')}] {(e.get('message') or '')[:120]}\n"
    except Exception:
        pass

    try:
        from core.state import _app_name
        app_name = _app_name()
    except Exception:
        app_name = os.getenv("APP_NAME", "").strip() or "Athena"
    briefing += f"\n*Passez une excellente journée ! {app_name} reste à votre entière disposition.* 🚀"

    return briefing

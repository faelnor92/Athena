import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any
import tools.agenda_sync as agenda_sync

AGENDA_FILE = "workspace/agenda.json"

def ensure_agenda_file():
    """Garantit un agenda.json VALIDE : crée le fichier s'il manque, et le répare
    s'il est vide ou corrompu (cas fréquent quand aucun agenda n'est encore utilisé)."""
    os.makedirs("workspace", exist_ok=True)
    needs_init = True
    if os.path.exists(AGENDA_FILE):
        try:
            with open(AGENDA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                json.loads(content)  # vérifie la validité
                needs_init = False
        except Exception:
            needs_init = True  # vide ou JSON invalide → on réinitialise
    if needs_init:
        with open(AGENDA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def load_agenda() -> list:
    """Charge la liste d'événements de façon robuste (jamais d'exception sur vide/corrompu)."""
    ensure_agenda_file()
    try:
        with open(AGENDA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def sync_all_external_calendars() -> int:
    """
    Synchronise toutes les sources externes configurées vers le cache local agenda.json.
    
    Returns:
        int: Nombre d'événements externes importés avec succès.
    """
    # 1. Charger les événements existants (robuste : vide/corrompu → [])
    events = load_agenda()

    # S'il n'y a AUCUNE source externe configurée, rien à synchroniser (no-op silencieux).
    has_external = bool(os.getenv("EXTERNAL_ICAL_URL")) or \
        (os.path.exists(agenda_sync.GOOGLE_KEY_PATH) and os.getenv("GOOGLE_CALENDAR_ID")) or \
        (os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"))
    if not has_external:
        return 0

    # Filtrer pour ne garder QUE les événements créés localement (source = 'local' ou absente)
    local_events = [e for e in events if e.get("source", "local") == "local"]
    
    external_events = []
    
    # 2. Synchronisation iCal
    ical_url = os.getenv("EXTERNAL_ICAL_URL")
    if ical_url:
        print(f"📅 [Sync] Démarrage de la synchro iCal sur {ical_url[:30]}...")
        ical_events = agenda_sync.sync_ical_feed(ical_url)
        for e in ical_events:
            e["source"] = "ical"
        external_events.extend(ical_events)
        
    # 3. Synchronisation Google Calendar
    if os.path.exists(agenda_sync.GOOGLE_KEY_PATH) and os.getenv("GOOGLE_CALENDAR_ID"):
        print("📅 [Sync] Démarrage de la synchro Google Calendar...")
        google_events = agenda_sync.sync_google_calendar()
        for e in google_events:
            e["source"] = "google"
        external_events.extend(google_events)
        
    # 4. Synchronisation CalDAV / Nextcloud
    if os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"):
        print("📅 [Sync] Démarrage de la synchro CalDAV...")
        caldav_events = agenda_sync.sync_caldav_calendar()
        for e in caldav_events:
            e["source"] = "caldav"
        external_events.extend(caldav_events)
        
    # 5. Fusionner et enregistrer
    merged = local_events + external_events
    # Trier par date chronologique (robuste si une clé manque)
    merged.sort(key=lambda x: x.get("datetime", ""))
    
    with open(AGENDA_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4, ensure_ascii=False)
        
    print(f"📅 [Sync] Synchronisation terminée avec succès ! {len(external_events)} événements externes importés.")
    return len(external_events)

def add_calendar_event(title: str, datetime_str: str, duration_minutes: int = 60, description: str = "") -> str:
    """
    Ajoute un événement ou rendez-vous dans l'agenda de l'utilisateur (local et externe).
    
    Args:
        title (str): Le titre du rendez-vous.
        datetime_str (str): La date et heure au format AAAA-MM-JJ HH:MM.
        duration_minutes (int): Durée estimée en minutes (défaut: 60).
        description (str): Détails ou notes complémentaires.
        
    Returns:
        str: Message de confirmation de l'ajout.
    """
    ensure_agenda_file()
    
    try:
        try:
            parsed_dt = datetime.strptime(datetime_str.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            parsed_dt = datetime.fromisoformat(datetime_str.strip().replace("Z", ""))
        iso_str = parsed_dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return f"Erreur : Format de date invalide '{datetime_str}'. Utilisez le format 'AAAA-MM-JJ HH:MM'."
        
    # Déterminer la source cible de l'écriture
    # Si Google est configuré, on l'écrit prioritairement sur Google
    written_externally = False
    source = "local"
    event_id = uuid.uuid4().hex[:8]
    
    if os.path.exists(agenda_sync.GOOGLE_KEY_PATH) and os.getenv("GOOGLE_CALENDAR_ID"):
        print("📅 [Agenda] Écriture en cours sur Google Calendar...")
        success = agenda_sync.add_google_calendar_event(title, iso_str, int(duration_minutes), description)
        if success:
            written_externally = True
            source = "google"
            
    # Sinon si CalDAV est configuré
    elif os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"):
        print("📅 [Agenda] Écriture en cours sur CalDAV...")
        success = agenda_sync.add_caldav_calendar_event(title, iso_str, int(duration_minutes), description)
        if success:
            written_externally = True
            source = "caldav"
            
    # Toujours écrire dans le cache local agenda.json pour un affichage immédiat
    event = {
        "id": event_id,
        "title": title,
        "datetime": iso_str,
        "duration_minutes": int(duration_minutes),
        "description": description,
        "reminded_15m": False,
        "reminded_now": False,
        "source": source
    }
    
    with open(AGENDA_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)
        
    events.append(event)
    events.sort(key=lambda x: x["datetime"])
    
    with open(AGENDA_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=4, ensure_ascii=False)
        
    # Si on a écrit sur un compte externe, on force un rafraîchissement rapide
    if written_externally:
        sync_all_external_calendars()
        return f"📅 Événement synchronisé avec succès sur votre calendrier externe ('{title}' le {iso_str})."
        
    return f"📅 Événement ajouté localement avec succès : '{title}' le {iso_str}."

def list_calendar_events() -> str:
    """
    Force la synchronisation et liste tous les rendez-vous de l'agenda.
    """
    ensure_agenda_file()
    # Déclencher une synchronisation silencieuse rapide à la lecture
    try:
        sync_all_external_calendars()
    except Exception as e:
        print(f"📅 [Sync Avertissement] Échec de la synchronisation à chaud : {e}")
        
    with open(AGENDA_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)
        
    if not events:
        return "📅 Votre agenda est actuellement vide."
        
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    upcoming = [e for e in events if e["datetime"] >= now_str]
    past = [e for e in events if e["datetime"] < now_str]
    
    output = "📅 --- ÉVÉNEMENTS PLANIFIÉS ---\n"
    if upcoming:
        for e in upcoming:
            source_lbl = f"({e.get('source', 'local')})" if e.get('source') else "(local)"
            output += f"- [{e['id']}] {e['datetime']} : {e['title']} {source_lbl} ({e['duration_minutes']} min)"
            if e.get("description"):
                output += f" - {e['description']}"
            output += "\n"
    else:
        output += "Aucun événement à venir.\n"
        
    if past:
        output += "\n⌛ --- ÉVÉNEMENTS PASSÉS (Historique) ---\n"
        for e in past[-5:]:
            source_lbl = f"({e.get('source', 'local')})" if e.get('source') else "(local)"
            output += f"- [{e['id']}] {e['datetime']} : {e['title']} {source_lbl}\n"
            
    return output

def delete_calendar_event(event_id: str) -> str:
    """
    Supprime un rendez-vous (local ou externe) de l'agenda par son ID.
    """
    ensure_agenda_file()
    with open(AGENDA_FILE, "r", encoding="utf-8") as f:
        events = json.load(f)
        
    target_event = next((e for e in events if e["id"] == event_id), None)
    if not target_event:
        return f"Erreur : Aucun événement trouvé avec l'identifiant '{event_id}'."
        
    source = target_event.get("source", "local")
    deleted_externally = False
    
    # Si c'est un événement Google
    if source == "google":
        print(f"📅 [Agenda] Suppression en cours sur Google Calendar pour l'event {event_id}...")
        deleted_externally = agenda_sync.delete_google_calendar_event(event_id)
        
    # Si c'est un événement CalDAV
    elif source == "caldav":
        print(f"📅 [Agenda] Suppression en cours sur CalDAV pour l'event {event_id}...")
        deleted_externally = agenda_sync.delete_caldav_calendar_event(event_id)
        
    # Nettoyer du cache local
    filtered_events = [e for e in events if e["id"] != event_id]
    with open(AGENDA_FILE, "w", encoding="utf-8") as f:
        json.dump(filtered_events, f, indent=4, ensure_ascii=False)
        
    if deleted_externally or source in ["google", "caldav"]:
        # Rafraîchir
        sync_all_external_calendars()
        return f"📅 L'événement [{event_id}] a été supprimé de votre agenda externe avec succès."
        
    return f"📅 L'événement local [{event_id}] a été supprimé de votre agenda."

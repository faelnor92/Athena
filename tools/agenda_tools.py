import os
import re
import json
import uuid
import functools
import contextlib
import threading
from datetime import datetime
from typing import List, Dict, Any
import tools.agenda_sync as agenda_sync

# --- Multi-tenant : agenda PAR UTILISATEUR --------------------------------
# Données et identifiants (iCal/CalDAV/Google) sont propres à chaque utilisateur
# (bucket "local" en mode sans auth). Pour ne pas réécrire agenda_sync (qui lit des
# os.getenv en interne), un context manager injecte temporairement, SOUS VERROU, la
# config de l'utilisateur courant dans l'environnement le temps de l'opération.
_AGENDA_LOCK = threading.RLock()
_ENV_KEYS = ["EXTERNAL_ICAL_URL", "GOOGLE_CALENDAR_ID", "CALDAV_URL", "CALDAV_USERNAME",
             "CALDAV_PASSWORD", "AGENDA_WRITE_TARGET", "AGENDA_TIMEZONE"]


def _user_slug() -> str:
    from core import user_config
    return re.sub(r"[^A-Za-z0-9_.-]", "_", user_config.current_user_key()) or "local"


def agenda_file() -> str:
    """Fichier d'événements de l'utilisateur courant."""
    return os.path.join("workspace", f"agenda_{_user_slug()}.json")


def google_creds_path() -> str:
    """Clé de service Google de l'utilisateur courant."""
    return os.path.join("workspace", f"google_credentials_{_user_slug()}.json")


@contextlib.contextmanager
def user_agenda_context():
    """Applique la config agenda de l'utilisateur courant (env + chemin clé Google)
    le temps de l'opération, puis restaure. Sérialisé (RLock) car mute os.environ."""
    from core import user_config
    with _AGENDA_LOCK:
        saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}
        saved_gkey = agenda_sync.GOOGLE_KEY_PATH
        try:
            for k in _ENV_KEYS:
                v = user_config.get(k)
                if v:
                    os.environ[k] = str(v)
                else:
                    os.environ.pop(k, None)
            agenda_sync.GOOGLE_KEY_PATH = google_creds_path()
            yield
        finally:
            for k, old in saved_env.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old
            agenda_sync.GOOGLE_KEY_PATH = saved_gkey


def _per_user(fn):
    """Décorateur : exécute la fonction dans le contexte agenda de l'utilisateur courant."""
    @functools.wraps(fn)
    def wrap(*a, **k):
        with user_agenda_context():
            return fn(*a, **k)
    return wrap


def _atomic_write(path: str, data) -> None:
    """Écriture atomique (temp + os.replace) : pas de fichier partiel/corrompu si deux
    workers écrivent l'agenda du même utilisateur (multi-worker-safe ; last-writer-wins)."""
    import tempfile
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".agenda-", suffix=".tmp",
                               dir=os.path.dirname(os.path.abspath(path)) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise


def ensure_agenda_file():
    """Garantit un agenda_<user>.json VALIDE (crée/répare)."""
    os.makedirs("workspace", exist_ok=True)
    path = agenda_file()
    needs_init = True
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                json.loads(content)
                needs_init = False
        except Exception:
            needs_init = True
    if needs_init:
        _atomic_write(path, [])


def load_agenda() -> list:
    """Charge la liste d'événements de l'utilisateur courant (robuste)."""
    ensure_agenda_file()
    try:
        with open(agenda_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


@_per_user
def sync_all_external_calendars() -> int:
    """Synchronise les sources externes de l'utilisateur courant vers son cache local."""
    events = load_agenda()

    has_external = bool(os.getenv("EXTERNAL_ICAL_URL")) or \
        agenda_sync.google_calendar_enabled() or \
        (os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"))
    if not has_external:
        return 0

    local_events = [e for e in events if e.get("source", "local") == "local"]
    external_events = []

    ical_url = os.getenv("EXTERNAL_ICAL_URL")
    if ical_url:
        print(f"📅 [Sync] Démarrage de la synchro iCal sur {ical_url[:30]}...")
        ical_events = agenda_sync.sync_ical_feed(ical_url)
        for e in ical_events:
            e["source"] = "ical"
        external_events.extend(ical_events)

    if agenda_sync.google_calendar_enabled():
        print("📅 [Sync] Démarrage de la synchro Google Calendar...")
        google_events = agenda_sync.sync_google_calendar()
        for e in google_events:
            e["source"] = "google"
        external_events.extend(google_events)

    if os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"):
        print("📅 [Sync] Démarrage de la synchro CalDAV...")
        caldav_events = agenda_sync.sync_caldav_calendar()
        for e in caldav_events:
            e["source"] = "caldav"
        external_events.extend(caldav_events)

    merged = local_events + external_events
    merged.sort(key=lambda x: x.get("datetime", ""))

    _atomic_write(agenda_file(), merged)

    print(f"📅 [Sync] Synchronisation terminée ! {len(external_events)} événements externes importés.")
    return len(external_events)


@_per_user
def add_calendar_event(title: str, datetime_str: str, duration_minutes: int = 60, description: str = "",
                       location: str = "") -> str:
    """
    Ajoute un événement ou rendez-vous dans l'agenda de l'utilisateur (local et externe).

    Args:
        title (str): Le titre du rendez-vous.
        datetime_str (str): La date et heure au format AAAA-MM-JJ HH:MM.
        duration_minutes (int): Durée estimée en minutes (défaut: 60).
        description (str): Détails ou notes complémentaires.
        location (str): LIEU du rendez-vous (adresse ou ville). Renseigne-le dès que tu le connais :
            il permet l'ALERTE DE DÉPART du briefing (« pars à 14h15, trajet 35 min + trafic »).

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

    written_externally = False
    source = "local"
    event_id = uuid.uuid4().hex[:8]

    # Calendrier d'écriture : préférence utilisateur (AGENDA_WRITE_TARGET) parmi
    # auto / local / google / caldav. "auto" (défaut) = ancien comportement (Google puis CalDAV).
    # Une cible explicite mais indisponible retombe sur "auto" plutôt que d'échouer en silence.
    _target = (os.getenv("AGENDA_WRITE_TARGET") or "auto").strip().lower()
    _google_ok = agenda_sync.google_calendar_enabled()
    _caldav_ok = bool(os.getenv("CALDAV_URL") and os.getenv("CALDAV_USERNAME") and os.getenv("CALDAV_PASSWORD"))

    def _write_google():
        if agenda_sync.add_google_calendar_event(title, iso_str, int(duration_minutes), description):
            return "google"
        return None

    def _write_caldav():
        if agenda_sync.add_caldav_calendar_event(title, iso_str, int(duration_minutes), description):
            return "caldav"
        return None

    if _target == "local":
        pass  # local uniquement, on n'écrit sur aucun externe
    elif _target == "google" and _google_ok:
        print("📅 [Agenda] Écriture sur Google Calendar (cible choisie)...")
        source = _write_google() or "local"
    elif _target == "caldav" and _caldav_ok:
        print("📅 [Agenda] Écriture sur CalDAV (cible choisie)...")
        source = _write_caldav() or "local"
    else:
        # auto (ou cible choisie indisponible) : Google d'abord, sinon CalDAV.
        if _google_ok:
            print("📅 [Agenda] Écriture sur Google Calendar (auto)...")
            source = _write_google() or "local"
        elif _caldav_ok:
            print("📅 [Agenda] Écriture sur CalDAV (auto)...")
            source = _write_caldav() or "local"
    written_externally = source != "local"

    event = {
        "id": event_id,
        "title": title,
        "datetime": iso_str,
        "duration_minutes": int(duration_minutes),
        "description": description,
        "location": (location or "").strip(),
        "reminded_15m": False,
        "reminded_now": False,
        "source": source,
    }

    with open(agenda_file(), "r", encoding="utf-8") as f:
        events = json.load(f)

    events.append(event)
    events.sort(key=lambda x: x["datetime"])

    _atomic_write(agenda_file(), events)

    if written_externally:
        sync_all_external_calendars()
        return f"📅 Événement synchronisé avec succès sur votre calendrier externe ('{title}' le {iso_str})."

    return f"📅 Événement ajouté localement avec succès : '{title}' le {iso_str}."


@_per_user
def list_calendar_events() -> str:
    """
    Force la synchronisation et liste tous les rendez-vous de l'agenda.
    """
    ensure_agenda_file()
    try:
        sync_all_external_calendars()
    except Exception as e:
        print(f"📅 [Sync Avertissement] Échec de la synchronisation à chaud : {e}")

    with open(agenda_file(), "r", encoding="utf-8") as f:
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


@_per_user
def delete_calendar_event(event_id: str) -> str:
    """
    Supprime un rendez-vous (local ou externe) de l'agenda par son ID.
    """
    ensure_agenda_file()
    with open(agenda_file(), "r", encoding="utf-8") as f:
        events = json.load(f)

    target_event = next((e for e in events if e["id"] == event_id), None)
    if not target_event:
        return f"Erreur : Aucun événement trouvé avec l'identifiant '{event_id}'."

    source = target_event.get("source", "local")
    deleted_externally = False
    # Pour Google, l'API exige l'id COMPLET (le champ `id` local est tronqué à 16 car. pour
    # l'affichage) → on utilise `external_id` quand il est présent.
    ext_id = target_event.get("external_id") or event_id

    if source == "google":
        print(f"📅 [Agenda] Suppression en cours sur Google Calendar pour l'event {event_id}...")
        deleted_externally = agenda_sync.delete_google_calendar_event(ext_id)
    elif source == "caldav":
        print(f"📅 [Agenda] Suppression en cours sur CalDAV pour l'event {event_id}...")
        deleted_externally = agenda_sync.delete_caldav_calendar_event(event_id)

    filtered_events = [e for e in events if e["id"] != event_id]
    _atomic_write(agenda_file(), filtered_events)

    if deleted_externally or source in ["google", "caldav"]:
        sync_all_external_calendars()
        return f"📅 L'événement [{event_id}] a été supprimé de votre agenda externe avec succès."

    return f"📅 L'événement local [{event_id}] a été supprimé de votre agenda."

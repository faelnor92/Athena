import os
import re
import json
import time
import base64
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# Chemin des credentials Google
GOOGLE_KEY_PATH = "workspace/google_credentials.json"

# =========================================================================
# 1. PARSEUR ICS UNIVERSEL (LIGHTWEIGHT & EXTRA ROBUSTE)
# =========================================================================
def parse_ics_data(ics_content: str) -> List[Dict[str, Any]]:
    """
    Parse un contenu brut de fichier .ics et en extrait une liste d'événements.
    """
    events = []
    # Nettoyer les sauts de lignes pour supporter le "line folding" (RFC 5545)
    ics_content = ics_content.replace("\r\n ", "").replace("\n ", "").replace("\r ", "")
    
    vevents = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", ics_content, re.DOTALL)
    
    for vevent in vevents:
        event = {}
        
        # 1. Titre (SUMMARY)
        summary_match = re.search(r"SUMMARY:(.*)", vevent)
        event["title"] = summary_match.group(1).strip() if summary_match else "Événement sans titre"
        
        # 2. Description
        desc_match = re.search(r"DESCRIPTION:(.*)", vevent)
        event["description"] = desc_match.group(1).strip().replace("\\n", "\n").replace("\\", "") if desc_match else ""
        
        # 3. Date de début (DTSTART)
        dtstart_match = re.search(r"DTSTART(?:;VALUE=DATE)?:([0-9T]+Z?)", vevent)
        if dtstart_match:
            raw_start = dtstart_match.group(1).strip()
            event["datetime"] = format_ics_datetime(raw_start)
        else:
            continue # Ignorer les événements sans date de début
            
        # 4. Durée (DURATION ou DTEND)
        duration_match = re.search(r"DURATION:P(?:.*?T)?([0-9]+)M", vevent)
        dtend_match = re.search(r"DTEND(?:;VALUE=DATE)?:([0-9T]+Z?)", vevent)
        
        if duration_match:
            event["duration_minutes"] = int(duration_match.group(1))
        elif dtend_match:
            try:
                start_dt = datetime.strptime(event["datetime"], "%Y-%m-%d %H:%M")
                end_str = format_ics_datetime(dtend_match.group(1).strip())
                end_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M")
                diff = int((end_dt - start_dt).total_seconds() / 60)
                event["duration_minutes"] = diff if diff > 0 else 60
            except Exception:
                event["duration_minutes"] = 60
        else:
            event["duration_minutes"] = 60
            
        # Générer un ID stable ou le lire (UID)
        uid_match = re.search(r"UID:(.*)", vevent)
        event["id"] = uid_match.group(1).strip()[:16] if uid_match else "ext_" + base64.b64encode(event["title"].encode()).decode()[:12]
        
        # Initialiser les champs de rappel d'arrière-plan
        event["reminded_15m"] = False
        event["reminded_now"] = False
        
        events.append(event)
        
    return events

def format_ics_datetime(raw_dt: str) -> str:
    """ Convertit un timestamp ICS (ex: 20260530T143000Z ou 20260530) en format YYYY-MM-DD HH:MM """
    raw_dt = raw_dt.replace("Z", "")
    if "T" in raw_dt:
        # Format complet YYYYMMDDTHHMMSS
        try:
            dt = datetime.strptime(raw_dt[:13], "%Y%m%dT%H%M")
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    # Format simple YYYYMMDD
    try:
        dt = datetime.strptime(raw_dt[:8], "%Y%m%d")
        return dt.strftime("%Y-%m-%d 00:00")
    except Exception:
        # Fallback date courante
        return datetime.now().strftime("%Y-%m-%d 12:00")

# =========================================================================
# 2. CONNECTEUR ICAL / ICS (LECTURE SEULE FLUX EXTERNES)
# =========================================================================
def sync_ical_feed(url: str) -> List[Dict[str, Any]]:
    """ Récupère et parse un flux ICS externe """
    # Anti-SSRF : refuser les URL pointant vers le réseau interne / métadonnées cloud
    # (l'URL iCal vient de la config utilisateur → fetch côté serveur).
    from tools.net_guard import is_blocked_url
    if is_blocked_url(url):
        print(f"📅 [Sync iCal] URL refusée (réseau interne/SSRF) : {url}")
        return []
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return parse_ics_data(r.text)
        else:
            print(f"📅 [Sync iCal] Erreur HTTP {r.status_code} sur {url}")
    except Exception as e:
        print(f"📅 [Sync iCal Exception] {e}")
    return []

# =========================================================================
# 3. CONNECTEUR GOOGLE CALENDAR (LECTURE/ÉCRITURE VIA SERVICE ACCOUNT REST)
# =========================================================================
def get_google_access_token(sa_info: Dict[str, Any]) -> str:
    """ Génère un jeton d'accès OAuth2 en pure signature JWT RS256 """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes
    
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {
        "iss": sa_info["client_email"],
        "sub": sa_info["client_email"],
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
        "scope": "https://www.googleapis.com/auth/calendar"
    }
    
    def b64_encode(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
        
    assertion_input = f"{b64_encode(header)}.{b64_encode(payload)}"
    
    private_key = serialization.load_pem_private_key(
        sa_info["private_key"].encode(),
        password=None
    )
    signature = private_key.sign(
        assertion_input.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    sig_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    assertion = f"{assertion_input}.{sig_b64}"
    
    r = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion
        },
        timeout=10
    )
    return r.json()["access_token"]

def _oauth_token() -> str:
    """access_token OAuth de l'utilisateur courant (None s'il n'a pas connecté Google)."""
    try:
        from core import google_oauth
        return google_oauth.get_access_token()
    except Exception:
        return None


def google_calendar_enabled() -> bool:
    """Vrai si l'utilisateur courant a une source Google active : OAuth connecté, OU
    compte de service (fichier de clé) + GOOGLE_CALENDAR_ID. Sert de garde aux opérations."""
    if _oauth_token():
        return True
    return bool(os.path.exists(GOOGLE_KEY_PATH) and os.getenv("GOOGLE_CALENDAR_ID"))


def get_google_calendar_client() -> Tuple[str, str]:
    """Récupère un (access_token, calendar_id) Google.

    Priorité à l'OAuth utilisateur (son propre compte → calendrier `primary` par défaut,
    AUCUN partage requis). Repli sur le compte de service (JWT) si configuré."""
    # 1) OAuth utilisateur (recommandé).
    token = _oauth_token()
    if token:
        # En OAuth on agit sur le compte de l'utilisateur : 'primary' sauf override explicite.
        calendar_id = os.getenv("GOOGLE_CALENDAR_ID") or "primary"
        return token, calendar_id

    # 2) Compte de service (legacy) : nécessite le partage du calendrier avec le SA.
    if not os.path.exists(GOOGLE_KEY_PATH):
        return None, None
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        return None, None
    try:
        with open(GOOGLE_KEY_PATH, "r") as f:
            sa_info = json.load(f)
        token = get_google_access_token(sa_info)
        return token, calendar_id
    except Exception as e:
        print(f"📅 [Google Auth Erreur] {e}")
        return None, None

def sync_google_calendar() -> List[Dict[str, Any]]:
    """ Récupère tous les événements Google Calendar à venir """
    token, calendar_id = get_google_calendar_client()
    if not token:
        return []
        
    events = []
    try:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {token}"}
        # Ne récupérer que les événements non annulés
        params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": 100}
        
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            google_events = r.json().get("items", [])
            for item in google_events:
                if item.get("status") == "cancelled":
                    continue
                    
                start = item.get("start", {})
                start_time = start.get("dateTime") or start.get("date")
                if not start_time:
                    continue
                    
                # Conversion YYYY-MM-DDTHH:MM:SS... en YYYY-MM-DD HH:MM
                dt_str = start_time[:16].replace("T", " ")
                
                # Calcul de durée
                end = item.get("end", {})
                end_time = end.get("dateTime") or end.get("date")
                duration = 60
                if end_time:
                    try:
                        st = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        et = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        duration = int((et - st).total_seconds() / 60)
                    except Exception:
                        pass
                
                events.append({
                    "id": item["id"][:16],          # handle court affiché à l'utilisateur/agent
                    "external_id": item["id"],       # id Google COMPLET (requis pour modifier/supprimer)
                    "title": item.get("summary", "Événement sans titre"),
                    "datetime": dt_str,
                    "duration_minutes": duration,
                    "description": item.get("description", ""),
                    "reminded_15m": False,
                    "reminded_now": False,
                    "source": "google"
                })
        else:
            print(f"📅 [Sync Google] Erreur API {r.status_code} : {r.text}")
    except Exception as e:
        print(f"📅 [Sync Google Exception] {e}")
        
    return events

def add_google_calendar_event(title: str, datetime_str: str, duration_minutes: int, description: str) -> bool:
    """ Ajoute un événement sur Google Calendar """
    token, calendar_id = get_google_calendar_client()
    if not token:
        return False
        
    try:
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        dt_end = dt + timedelta(minutes=duration_minutes)
        
        # Format ISO pour Google Calendar
        start_iso = dt.isoformat()
        end_iso = dt_end.isoformat()
        
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        body = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_iso, "timeZone": "Europe/Paris"},
            "end": {"dateTime": end_iso, "timeZone": "Europe/Paris"}
        }
        
        r = requests.post(url, headers=headers, json=body, timeout=10)
        return r.status_code in [200, 201]
    except Exception as e:
        print(f"📅 [Google Add Event Exception] {e}")
        return False

def delete_google_calendar_event(event_id: str) -> bool:
    """ Supprime un événement sur Google Calendar """
    token, calendar_id = get_google_calendar_client()
    if not token:
        return False
        
    try:
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {token}"}
        
        r = requests.delete(url, headers=headers, timeout=10)
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"📅 [Google Delete Event Exception] {e}")
        return False

# =========================================================================
# 4. CONNECTEUR CALDAV / WEB DAV (LECTURE/ÉCRITURE NEXTCLOUD ET SYNOLOGY)
# =========================================================================
def sync_caldav_calendar() -> List[Dict[str, Any]]:
    """ Récupère tous les événements depuis un serveur CalDAV """
    url = os.getenv("CALDAV_URL")
    user = os.getenv("CALDAV_USERNAME")
    password = os.getenv("CALDAV_PASSWORD")
    
    if not url or not user or not password:
        return []

    # Anti-SSRF : l'URL CalDAV vient de la config utilisateur → bloquer le réseau interne.
    from tools.net_guard import is_blocked_url
    if is_blocked_url(url):
        print("📅 [Sync CalDAV] URL refusée (réseau interne/SSRF).")
        return []

    events = []
    try:
        # Requête REPORT pour récupérer tous les VEVENT du calendrier
        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Depth": "1"
        }
        xml_payload = """<?xml version="1.0" encoding="utf-8" ?>
        <c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
            <d:prop>
                <d:getetag />
                <c:calendar-data />
            </d:prop>
            <c:filter>
                <c:comp-filter name="VCALENDAR">
                    <c:comp-filter name="VEVENT" />
                </c:comp-filter>
            </c:filter>
        </c:calendar-query>"""
        
        r = requests.request("REPORT", url, auth=(user, password), headers=headers, data=xml_payload, timeout=10)
        if r.status_code in [200, 207]:
            # Extraire les blocs iCal des réponses XML. ATTENTION : le serveur choisit SON
            # préfixe de namespace dans la réponse (SabreDAV/Nextcloud renvoie souvent
            # <cal:calendar-data>, voire <C:...>), pas forcément le `c:` de notre requête.
            # → on matche n'importe quel préfixe (ou aucun), sinon 0 événement lu.
            calendar_datas = re.findall(
                r"<(?:[A-Za-z0-9_.-]+:)?calendar-data[^>]*>(.*?)</(?:[A-Za-z0-9_.-]+:)?calendar-data>",
                r.text, re.DOTALL | re.IGNORECASE)
            for ics in calendar_datas:
                # Décoder les entités XML de base
                decoded_ics = ics.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                parsed = parse_ics_data(decoded_ics)
                for e in parsed:
                    e["source"] = "caldav"
                    events.append(e)
        else:
            print(f"📅 [Sync CalDAV] Erreur API {r.status_code}")
    except Exception as e:
        print(f"📅 [Sync CalDAV Exception] {e}")
        
    return events

def add_caldav_calendar_event(title: str, datetime_str: str, duration_minutes: int, description: str) -> bool:
    """ Crée un nouvel événement sur le calendrier CalDAV via HTTP PUT """
    url = os.getenv("CALDAV_URL")
    user = os.getenv("CALDAV_USERNAME")
    password = os.getenv("CALDAV_PASSWORD")
    
    if not url or not user or not password:
        return False
        
    try:
        import uuid
        event_uid = uuid.uuid4().hex[:16]
        
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        dt_end = dt + timedelta(minutes=duration_minutes)
        
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        start_str = dt.strftime("%Y%m%dT%H%M00")
        end_str = dt_end.strftime("%Y%m%dT%H%M00")
        
        # Construire un fichier ICS valide minimaliste
        ics_data = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Athena Swarm//Calendar Client//FR
BEGIN:VEVENT
UID:{event_uid}
DTSTAMP:{stamp}
DTSTART;TZID=Europe/Paris:{start_str}
DTEND;TZID=Europe/Paris:{end_str}
SUMMARY:{title}
DESCRIPTION:{description}
END:VEVENT
END:VCALENDAR"""

        # CalDAV cible l'événement par un fichier .ics unique dans la ressource URL
        put_url = url.rstrip("/") + f"/{event_uid}.ics"
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        
        r = requests.put(put_url, auth=(user, password), headers=headers, data=ics_data.encode("utf-8"), timeout=10)
        return r.status_code in [200, 201, 204]
    except Exception as e:
        print(f"📅 [CalDAV Add Event Exception] {e}")
        return False

def delete_caldav_calendar_event(event_id: str) -> bool:
    """ Supprime un événement sur le calendrier CalDAV """
    url = os.getenv("CALDAV_URL")
    user = os.getenv("CALDAV_USERNAME")
    password = os.getenv("CALDAV_PASSWORD")
    
    if not url or not user or not password:
        return False
        
    try:
        # Essayer de cibler l'événement par son ID
        # Sur CalDAV, l'URL de l'événement est typiquement {calendar_url}/{id}.ics
        delete_url = url.rstrip("/") + f"/{event_id}.ics"
        r = requests.delete(delete_url, auth=(user, password), timeout=10)
        return r.status_code in [200, 204]
    except Exception as e:
        print(f"📅 [CalDAV Delete Event Exception] {e}")
        return False

#!/usr/bin/env python3
"""Diagnostic Agenda (CalDAV / Google / iCal) pour Athena.

Lancement (depuis le dossier d'Athena, ex. /root/athena) :
    .venv/bin/python scripts/diag_agenda.py

Lecture seule. Pour CHAQUE utilisateur ayant une config agenda, il affiche la config
(mot de passe masqué), vérifie l'anti-SSRF sur l'URL CalDAV, puis tente une VRAIE synchro
(CalDAV + Google) et indique combien d'événements remontent — ou l'erreur exacte.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

print("=" * 70)
print("DIAGNOSTIC AGENDA — Athena")
print("=" * 70)

from core import shared_store               # noqa: E402
import tools.agenda_sync as asy             # noqa: E402

_KEYS = ["EXTERNAL_ICAL_URL", "GOOGLE_CALENDAR_ID", "CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD"]


def _slug(user):
    import re
    return re.sub(r"[^A-Za-z0-9_.-]", "_", user) or "local"


# Tous les utilisateurs ayant une config (user_config) + le bucket 'local'.
buckets = shared_store.items("user_config") or {}
if "local" not in buckets:
    buckets["local"] = shared_store.get("user_config", "local") or {}

found_any = False
for user, cfg in buckets.items():
    cfg = cfg or {}
    has_agenda = any(cfg.get(k) for k in _KEYS) or os.path.exists(
        os.path.join("workspace", f"google_credentials_{_slug(user)}.json"))
    if not has_agenda:
        continue
    found_any = True
    print(f"\n#### Utilisateur : {user}")
    for k in _KEYS:
        v = cfg.get(k, "")
        if "PASSWORD" in k and v:
            v = f"{str(v)[:2]}…(défini, {len(str(v))} car.)"
        print(f"    {k:18} = {v!r}")
    gkey = os.path.join("workspace", f"google_credentials_{_slug(user)}.json")
    print(f"    clé Google (compte service) : {'présente' if os.path.exists(gkey) else 'absente'} ({gkey})")
    # OAuth ?
    try:
        from core import google_oauth, user_config as uc
        print(f"    OAuth Google connecté : {bool(uc.get(google_oauth._K_REFRESH, user=user))}")
    except Exception as e:
        print(f"    OAuth Google : (check impossible : {e})")

    # --- Test CalDAV en direct, avec la config de CET utilisateur ---
    caldav_url = cfg.get("CALDAV_URL", "")
    if caldav_url:
        from tools.net_guard import is_blocked_url
        blocked = is_blocked_url(caldav_url)
        print(f"    [CalDAV] anti-SSRF bloque l'URL ? {blocked}"
              + ("  ⚠️ → ajoute l'hôte/plage à NET_GUARD_ALLOW_HOSTS" if blocked else ""))
        if not blocked:
            saved = {k: os.environ.get(k) for k in _KEYS}
            try:
                for k in _KEYS:
                    if cfg.get(k):
                        os.environ[k] = str(cfg[k])
                    else:
                        os.environ.pop(k, None)
                evs = asy.sync_caldav_calendar()
                print(f"    [CalDAV] synchro OK → {len(evs)} événement(s) lus depuis Nextcloud.")
                for e in evs[:3]:
                    print(f"             • {e.get('datetime')} {e.get('title')}")
            except Exception as e:
                print(f"    [CalDAV] ERREUR : {type(e).__name__}: {str(e)[:300]}")
            finally:
                for k, old in saved.items():
                    if old is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = old
    else:
        print("    [CalDAV] non configuré (CALDAV_URL vide).")

    # --- Test Google en direct ---
    if cfg.get("GOOGLE_CALENDAR_ID") or os.path.exists(gkey):
        saved_env = os.environ.get("GOOGLE_CALENDAR_ID")
        saved_path = asy.GOOGLE_KEY_PATH
        try:
            if cfg.get("GOOGLE_CALENDAR_ID"):
                os.environ["GOOGLE_CALENDAR_ID"] = str(cfg["GOOGLE_CALENDAR_ID"])
            asy.GOOGLE_KEY_PATH = gkey
            evs = asy.sync_google_calendar()
            print(f"    [Google] synchro → {len(evs)} événement(s).")
            if not evs and os.path.exists(gkey):
                print("             (0 → le calendrier n'est probablement PAS partagé avec "
                      "l'email du compte de service, ou mauvais GOOGLE_CALENDAR_ID.)")
        except Exception as e:
            print(f"    [Google] ERREUR : {type(e).__name__}: {str(e)[:300]}")
        finally:
            if saved_env is None:
                os.environ.pop("GOOGLE_CALENDAR_ID", None)
            else:
                os.environ["GOOGLE_CALENDAR_ID"] = saved_env
            asy.GOOGLE_KEY_PATH = saved_path
    else:
        print("    [Google] non configuré.")

if not found_any:
    print("\n⚠️  AUCUN utilisateur n'a de config agenda enregistrée (CalDAV/Google/iCal).")
    print("    → La config saisie dans Réglages → Agenda n'a peut-être pas été enregistrée,")
    print("      ou elle est sous un autre compte. Vérifie que tu es bien connecté en l'enregistrant.")

print("\n" + "=" * 70)
print("RAPPELS")
print("  - CalDAV Nextcloud : URL = http://IP/remote.php/dav/calendars/USER/CALENDRIER/")
print("  - Anti-SSRF : NET_GUARD_ALLOW_HOSTS doit couvrir l'IP (CIDR ok, ex. 192.168.1.0/24).")
print("  - Compte de service Google : PARTAGER le calendrier avec le client_email du JSON.")
print("=" * 70)

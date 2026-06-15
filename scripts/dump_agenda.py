#!/usr/bin/env python3
"""Dump complet de l'agenda Athena : fichiers locaux + synchro CalDAV/Google en direct.

Lancement (depuis le dossier d'Athena, ex. /root/athena) :
    .venv/bin/python scripts/dump_agenda.py

Montre, pour chaque utilisateur :
  - le contenu du fichier agenda local (source, date, titre) ;
  - ce que Nextcloud (CalDAV) et Google renvoient VRAIMENT en live ;
  - comment le filtre « à venir / passé » de list_calendar_events classe chaque événement
    (pour repérer un souci de fuseau horaire qui ferait disparaître les events « du jour »).
Lecture seule, aucun secret affiché.
"""
import os
import sys
import re
import json
import glob
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import shared_store          # noqa: E402
import tools.agenda_sync as asy        # noqa: E402

_KEYS = ["EXTERNAL_ICAL_URL", "GOOGLE_CALENDAR_ID", "CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD"]
now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

print("=" * 70)
print(f"DUMP AGENDA — Athena   (maintenant = {now_str})")
print("=" * 70)

# 1) Fichiers d'agenda locaux (tous utilisateurs).
print("\n[1] Fichiers d'agenda locaux (workspace/agenda_*.json)")
files = sorted(glob.glob("workspace/agenda_*.json"))
if not files:
    print("    (aucun)")
for f in files:
    print(f"\n  === {f}")
    try:
        evs = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print(f"     (illisible : {e})"); continue
    if not evs:
        print("     (vide)")
    for e in evs:
        when = e.get("datetime", "?")
        tag = "À VENIR" if when >= now_str else "passé "
        print(f"     [{tag}] {e.get('source','?'):7} | {when} | {e.get('title','')}")

# 2) Synchro live par utilisateur configuré.
print("\n[2] Synchro EN DIRECT depuis les serveurs (CalDAV / Google)")
buckets = shared_store.items("user_config") or {}
if "local" not in buckets:
    buckets["local"] = shared_store.get("user_config", "local") or {}

for user, cfg in buckets.items():
    cfg = cfg or {}
    if not any(cfg.get(k) for k in _KEYS):
        continue
    print(f"\n  #### Utilisateur : {user}")
    saved = {k: os.environ.get(k) for k in _KEYS}
    saved_path = asy.GOOGLE_KEY_PATH
    try:
        for k in _KEYS:
            if cfg.get(k):
                os.environ[k] = str(cfg[k])
            else:
                os.environ.pop(k, None)
        # CalDAV
        if cfg.get("CALDAV_URL"):
            try:
                evs = asy.sync_caldav_calendar()
                print(f"    [CalDAV] {len(evs)} événement(s) lus :")
                for e in evs:
                    print(f"       • {e.get('datetime')} | {e.get('title')}")
            except Exception as e:
                print(f"    [CalDAV] ERREUR : {type(e).__name__}: {str(e)[:200]}")
        # Google
        gkey = os.path.join("workspace", f"google_credentials_{re.sub(r'[^A-Za-z0-9_.-]','_',user)}.json")
        if cfg.get("GOOGLE_CALENDAR_ID") or os.path.exists(gkey):
            try:
                asy.GOOGLE_KEY_PATH = gkey
                evs = asy.sync_google_calendar()
                print(f"    [Google] {len(evs)} événement(s) lus :")
                for e in evs:
                    print(f"       • {e.get('datetime')} | {e.get('title')}")
            except Exception as e:
                print(f"    [Google] ERREUR : {type(e).__name__}: {str(e)[:200]}")
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
        asy.GOOGLE_KEY_PATH = saved_path

print("\n" + "=" * 70)
print("LECTURE :")
print("  - [1] = ce qu'Athena a en mémoire. 'source: local' = jamais écrit sur un externe.")
print("  - [2] = ce que les serveurs renvoient VRAIMENT maintenant.")
print("  - Un événement 'du jour' marqué [passé] (heure déjà dépassée) n'apparaît PAS dans")
print("    les « à venir » de list_calendar_events → c'est normal (ou un décalage de fuseau).")
print("  - Si un event est dans Nextcloud (app) mais absent de [2] → souci de lecture/calendrier.")
print("=" * 70)

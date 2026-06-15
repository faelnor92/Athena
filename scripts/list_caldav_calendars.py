#!/usr/bin/env python3
"""Liste les calendriers CalDAV (Nextcloud) et donne l'URL EXACTE à coller dans Athena.

Lancement (depuis le dossier d'Athena, ex. /root/athena) :
    .venv/bin/python scripts/list_caldav_calendars.py

Il reconstruit le BON endpoint (/remote.php/dav/calendars/<user>/) à partir de l'hôte + du
nom d'utilisateur enregistrés (peu importe que l'URL stockée pointe par erreur sur /principals/),
puis affiche chaque calendrier : nom, écriture possible ou non, et l'URL complète à recopier.
Lecture seule, aucun secret affiché.
"""
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests                       # noqa: E402
from core import shared_store         # noqa: E402

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

print("=" * 70)
print("CALENDRIERS CalDAV DISPONIBLES — Athena")
print("=" * 70)

buckets = shared_store.items("user_config") or {}
if "local" not in buckets:
    buckets["local"] = shared_store.get("user_config", "local") or {}

did = False
for user, cfg in buckets.items():
    cfg = cfg or {}
    url = (cfg.get("CALDAV_URL") or "").strip()
    usr = (cfg.get("CALDAV_USERNAME") or "").strip()
    pwd = (cfg.get("CALDAV_PASSWORD") or "")
    if not url or not usr or not pwd:
        continue
    did = True

    # Reconstruit l'origine (scheme://host:port) depuis l'URL stockée, puis l'endpoint
    # CALENDARS correct (et non /principals/ qui ne contient pas de calendriers).
    p = urllib.parse.urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    home = f"{origin}/remote.php/dav/calendars/{usr}/"

    print(f"\n#### Utilisateur Athena : {user}")
    print(f"    Hôte Nextcloud : {origin}")
    print(f"    Endpoint calendriers : {home}")

    body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" '
            'xmlns:c="urn:ietf:params:xml:ns:caldav">'
            '<d:prop><d:displayname/><d:resourcetype/>'
            '<d:current-user-privilege-set/></d:prop></d:propfind>')
    try:
        r = requests.request("PROPFIND", home, auth=(usr, pwd),
                             headers={"Depth": "1", "Content-Type": "application/xml", **_UA},
                             data=body, timeout=15)
    except Exception as e:
        print(f"    ❌ Connexion impossible : {type(e).__name__}: {str(e)[:200]}")
        continue
    if r.status_code not in (200, 207):
        print(f"    ❌ HTTP {r.status_code} — impossible de lister. Corps : {r.text[:200]}")
        if r.status_code == 401:
            print("       => 401 : utilise un MOT DE PASSE D'APPLICATION Nextcloud.")
        continue

    try:
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"    ❌ Réponse non-XML ({e}) — un proxy (Cloudflare ?) intercepte peut-être.")
        continue

    ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
    found = 0
    print("    ----------------------------------------------------------------")
    for resp in root.findall("d:response", ns):
        if resp.find(".//c:calendar", ns) is None:
            continue  # pas un calendrier (collection racine, etc.)
        found += 1
        href = resp.findtext("d:href", "", ns)
        name = resp.findtext(".//d:displayname", "", ns) or "(sans nom)"
        privs = resp.find(".//d:current-user-privilege-set", ns)
        can_write = privs is not None and privs.find(".//d:write", ns) is not None
        full = origin + href if href.startswith("/") else href
        flag = "✅ ÉCRITURE" if can_write else "🔒 lecture seule"
        print(f"    {flag}  «{name}»")
        print(f"        URL à coller dans Athena : {full}")
    print("    ----------------------------------------------------------------")
    if not found:
        print("    ⚠️ Aucun calendrier trouvé sous cet utilisateur.")
    else:
        print("    => Dans Réglages → Agenda → CalDAV → URL : copie une URL marquée ✅ ÉCRITURE.")

if not did:
    print("\n⚠️ Aucune config CalDAV complète (URL + user + mot de passe) trouvée.")

print("\n" + "=" * 70)

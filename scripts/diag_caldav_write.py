#!/usr/bin/env python3
"""Diagnostic d'ÉCRITURE CalDAV pour Athena.

Lancement (depuis le dossier d'Athena, ex. /root/athena) :
    .venv/bin/python scripts/diag_caldav_write.py

Pour chaque utilisateur ayant une config CalDAV, il :
  1. vérifie l'anti-SSRF sur l'URL ;
  2. fait un PROPFIND (le calendrier répond-il ?) ;
  3. PUT un événement de TEST et montre le CODE HTTP + la réponse brute ;
  4. relit (GET) puis SUPPRIME (DELETE) l'événement de test.

Montre les vraies réponses du serveur (la fonction d'Athena, elle, n'expose qu'un bool).
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests                          # noqa: E402
from core import shared_store            # noqa: E402
from tools.net_guard import is_blocked_url  # noqa: E402

# User-Agent "navigateur" : certaines protections (Cloudflare Bot Fight Mode) bloquent
# le UA par défaut de python-requests → 403. On teste avec un UA réaliste.
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _who_blocked(resp):
    """Indique si un 4xx vient probablement de Cloudflare (vs Nextcloud)."""
    server = (resp.headers.get("Server") or "").lower()
    cf_ray = resp.headers.get("CF-RAY") or resp.headers.get("cf-ray")
    body = (resp.text or "")[:200].lower()
    cf = "cloudflare" in server or bool(cf_ray) or "cloudflare" in body or "attention required" in body
    return (f"Server={resp.headers.get('Server')!r} CF-RAY={cf_ray!r}"
            + ("  ⚠️ => BLOCAGE CLOUDFLARE (pas Nextcloud)" if cf else "  (origine Nextcloud probable)"))

print("=" * 70)
print("DIAGNOSTIC ÉCRITURE CalDAV — Athena")
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
    if not url:
        continue
    did = True
    print(f"\n#### Utilisateur : {user}")
    print(f"    URL  : {url}")
    print(f"    USER : {usr!r}")
    print(f"    PWD  : {'(défini, %d car.)' % len(pwd) if pwd else '(VIDE !)'}")
    print(f"    write_target : {cfg.get('AGENDA_WRITE_TARGET', 'auto')!r}")

    if is_blocked_url(url):
        print("    ❌ Anti-SSRF BLOQUE cette URL → ajoute l'hôte/plage à NET_GUARD_ALLOW_HOSTS.")
        continue
    if not usr or not pwd:
        print("    ❌ user ou mot de passe manquant → écriture impossible.")
        continue

    auth = (usr, pwd)
    base = url.rstrip("/")

    # 0) Liste des calendriers de l'utilisateur + lesquels sont EN ÉCRITURE.
    #    On remonte au "calendar-home" (le parent de l'URL) et on PROPFIND Depth:1.
    home = base.rsplit("/", 1)[0] + "/" if "/" in base else base
    print(f"\n    [Calendriers disponibles] PROPFIND {home}")
    try:
        req = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" '
               'xmlns:c="urn:ietf:params:xml:ns:caldav">'
               '<d:prop><d:displayname/><d:resourcetype/>'
               '<d:current-user-privilege-set/></d:prop></d:propfind>')
        r0 = requests.request("PROPFIND", home, auth=auth,
                              headers={"Depth": "1", "Content-Type": "application/xml", **_UA},
                              data=req, timeout=12)
        if r0.status_code in (200, 207):
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r0.content)
            ns = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}
            for resp in root.findall("d:response", ns):
                href = resp.findtext("d:href", "", ns)
                is_cal = resp.find(".//c:calendar", ns) is not None
                if not is_cal:
                    continue
                name = resp.findtext(".//d:displayname", "", ns) or "(sans nom)"
                privs = resp.find(".//d:current-user-privilege-set", ns)
                can_write = privs is not None and privs.find(".//d:write", ns) is not None
                flag = "✅ ÉCRITURE" if can_write else "🔒 lecture seule"
                print(f"      {flag}  «{name}»  -> URL : {href}")
            print("      => Pour Athena, copie l'URL d'un calendrier marqué ✅ ÉCRITURE (URL complète :"
                  f" {base.split('/remote.php')[0]}<href>).")
        else:
            print(f"      HTTP {r0.status_code} (impossible de lister) — {_who_blocked(r0)}")
    except Exception as e:
        print(f"      (listing impossible : {type(e).__name__}: {str(e)[:150]})")

    # 1) PROPFIND : le calendrier répond-il ?
    print("\n    [PROPFIND] le calendrier existe/répond ?")
    try:
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        r = requests.request("PROPFIND", base + "/", auth=auth,
                             headers={"Depth": "0", "Content-Type": "application/xml", **_UA},
                             data=body, timeout=12, allow_redirects=False)
        print(f"      HTTP {r.status_code}"
              + (f"  (redirection → {r.headers.get('Location')})" if r.status_code in (301, 302, 307, 308) else ""))
        if r.status_code in (403, 405, 503):
            print(f"      {_who_blocked(r)}")
        if r.status_code == 401:
            print("      => 401 : identifiants refusés (utilise un MOT DE PASSE D'APPLICATION Nextcloud).")
        elif r.status_code in (301, 302, 307, 308):
            print("      => redirection : mauvais schéma/URL. Utilise l'URL FINALE (souvent https://...).")
        elif r.status_code not in (207, 200):
            print(f"      => inattendu. Corps : {r.text[:200]}")
    except Exception as e:
        print(f"      ❌ Connexion impossible : {type(e).__name__}: {str(e)[:200]}")
        print("         => mauvais hôte/port, ou Nextcloud injoignable depuis cette machine.")
        continue

    # 2) PUT d'un événement de test
    uid = "athena-diag-" + uuid.uuid4().hex[:10]
    dt = datetime.now() + timedelta(days=1)
    dt = dt.replace(minute=0, second=0, microsecond=0)
    end = dt + timedelta(minutes=30)
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Athena//diag//FR\r\nBEGIN:VEVENT\r\n"
           f"UID:{uid}\r\nDTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\n"
           f"DTSTART;TZID=Europe/Paris:{dt.strftime('%Y%m%dT%H%M00')}\r\n"
           f"DTEND;TZID=Europe/Paris:{end.strftime('%Y%m%dT%H%M00')}\r\n"
           "SUMMARY:TEST Athena (diag - à supprimer)\r\nEND:VEVENT\r\nEND:VCALENDAR")
    put_url = base + f"/{uid}.ics"
    print(f"\n    [PUT] création d'un événement de test → {put_url}")
    try:
        r = requests.put(put_url, auth=auth,
                         headers={"Content-Type": "text/calendar; charset=utf-8", **_UA},
                         data=ics.encode("utf-8"), timeout=12, allow_redirects=False)
        print(f"      HTTP {r.status_code}  (attendu : 201 ou 204)")
        if r.status_code in (200, 201, 204):
            print("      ✅ ÉCRITURE OK — l'événement de test a été créé sur le serveur.")
        else:
            print(f"      ❌ ÉCRITURE REFUSÉE. {_who_blocked(r)}")
            print(f"      Allow={r.headers.get('Allow')!r} DAV={r.headers.get('DAV')!r}")
            print(f"      Corps : {r.text[:400]}")
            if r.status_code == 403:
                print("      => 403 : le compte n'a pas le droit d'ÉCRIRE sur ce calendrier "
                      "(droits Nextcloud), ou l'URL pointe sur un calendrier en lecture seule/partagé.")
            if r.status_code == 404:
                print("      => 404 : l'URL ne pointe pas sur un calendrier valide. Format attendu : "
                      "https://host/remote.php/dav/calendars/UTILISATEUR/NOMCALENDRIER/")
            if r.status_code == 405:
                print("      => 405 : méthode non autorisée ici → l'URL n'est pas une collection "
                      "calendrier (PUT impossible). Vérifie le chemin .../calendars/USER/personal/")
    except Exception as e:
        print(f"      ❌ Exception PUT : {type(e).__name__}: {str(e)[:200]}")
        continue

    # 3) GET de relecture + 4) DELETE de nettoyage
    try:
        g = requests.get(put_url, auth=auth, headers=_UA, timeout=10)
        print(f"    [GET] relecture de l'événement : HTTP {g.status_code} ({'trouvé' if g.status_code == 200 else 'absent'})")
    except Exception as e:
        print(f"    [GET] {type(e).__name__}: {str(e)[:120]}")
    try:
        d = requests.delete(put_url, auth=auth, headers=_UA, timeout=10)
        print(f"    [DELETE] nettoyage de l'événement de test : HTTP {d.status_code}")
    except Exception as e:
        print(f"    [DELETE] {type(e).__name__}: {str(e)[:120]}")

if not did:
    print("\n⚠️  Aucun utilisateur n'a de CALDAV_URL enregistrée.")
    print("    → Vérifie Réglages → Agenda (section CalDAV) et que tu es bien connecté en enregistrant.")

print("\n" + "=" * 70)
print("LECTURE : un PUT en 201/204 = écriture OK. Sinon le code (401/403/404/405/redir)")
print("dit la cause exacte (auth / droits / URL / mauvais endpoint).")
print("=" * 70)

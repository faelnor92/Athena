"""Outils Nextcloud (auto-hébergé) — natifs, sans SDK.

- Fichiers (WebDAV)  : lister / lire / écrire / supprimer.
- Tâches   (CalDAV)  : lister les tâches (VTODO).
- Contacts (CardDAV) : rechercher un contact.

Sécurité :
- net_guard (anti-SSRF) sur CHAQUE URL — un Nextcloud LAN exige son hôte dans NET_GUARD_ALLOW_HOSTS.
- can_write() (lecture seule pour les viewers) sur écriture/suppression.
- confinement de chemin (anti-traversal) : pas de `..`, tout est relatif à la racine de l'utilisateur.
- identifiants par-utilisateur (mot de passe d'application Nextcloud recommandé).
"""
import re
# Parsing XML DURCI (anti-XXE / entity-expansion) : defusedxml si dispo, repli stdlib sinon.
try:
    from defusedxml.ElementTree import fromstring as _xml_fromstring
except Exception:  # defusedxml absent → repli stdlib (réponses DAV d'un Nextcloud de confiance)
    from xml.etree.ElementTree import fromstring as _xml_fromstring
import urllib.parse
from typing import List

import requests

from core import nextcloud, projects
from tools.net_guard import is_blocked_url

_TIMEOUT = 15
_MAX_READ = 200_000   # garde-fou taille de lecture (caractères)


def _not_configured() -> str:
    return ("Nextcloud non configuré. Va dans Réglages → Nextcloud et renseigne l'URL, "
            "l'utilisateur et un mot de passe d'application.")


def _guard(url: str):
    if is_blocked_url(url):
        return ("Erreur : l'hôte Nextcloud est une adresse interne bloquée (anti-SSRF). "
                "Ajoute son hôte à NET_GUARD_ALLOW_HOSTS pour autoriser ce service de confiance.")
    return None


def _safe_path(path: str) -> str:
    """Nettoie un chemin distant relatif à la racine de l'utilisateur (anti-traversal)."""
    p = (path or "").strip().lstrip("/")
    segs = [s for s in p.split("/") if s not in ("", ".")]
    if any(s == ".." for s in segs):
        raise ValueError("chemin invalide (remontée '..' interdite).")
    return "/".join(segs)


def _check_path(path: str):
    """Renvoie un message d'erreur si le chemin est invalide (anti-traversal), sinon None."""
    try:
        _safe_path(path)
        return None
    except ValueError as e:
        return f"Erreur : {e}"


def _files_url(path: str) -> str:
    segs = _safe_path(path).split("/") if _safe_path(path) else []
    quoted = "/".join(urllib.parse.quote(s) for s in segs)
    return nextcloud.files_base() + quoted


# --- FICHIERS (WebDAV) ------------------------------------------------------
def nextcloud_list_files(path: str = "") -> str:
    """
    Liste le contenu d'un dossier Nextcloud (fichiers et sous-dossiers).

    Args:
        path (str): Dossier à lister, relatif à ta racine (vide = racine). Ex: "Documents/Romans".

    Returns:
        str: Liste des entrées (nom, type, taille).
    """
    if not nextcloud.is_configured():
        return _not_configured()
    perr = _check_path(path)
    if perr:
        return perr
    url = _files_url(path)
    err = _guard(url)
    if err:
        return err
    body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
            '<d:resourcetype/><d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>')
    try:
        r = requests.request("PROPFIND", url, auth=nextcloud.auth(),
                             headers={"Depth": "1", "Content-Type": "application/xml"},
                             data=body, timeout=_TIMEOUT)
        if r.status_code not in (207, 200):
            return f"Erreur Nextcloud ({r.status_code}) : {r.text[:200]}"
        root = _xml_fromstring(r.content)
        ns = {"d": "DAV:"}
        base_path = urllib.parse.urlparse(url).path
        out = []
        for resp in root.findall("d:response", ns):
            href = resp.findtext("d:href", "", ns)
            hpath = urllib.parse.unquote(urllib.parse.urlparse(href).path)
            if hpath.rstrip("/") == base_path.rstrip("/"):
                continue  # le dossier lui-même
            name = hpath.rstrip("/").split("/")[-1]
            is_dir = resp.find(".//d:collection", ns) is not None
            size = resp.findtext(".//d:getcontentlength", "", ns)
            out.append(f"  {'📁' if is_dir else '📄'} {name}" + (f"  ({size} o)" if size and not is_dir else ""))
        if not out:
            return f"📂 Dossier vide : /{_safe_path(path)}"
        return f"📂 /{_safe_path(path) or ''} :\n" + "\n".join(sorted(out))
    except Exception as e:
        return f"Erreur lors du listing Nextcloud : {e}"


def nextcloud_read_file(path: str) -> str:
    """
    Lit le contenu texte d'un fichier Nextcloud.

    Args:
        path (str): Chemin du fichier relatif à ta racine. Ex: "Documents/notes.txt".

    Returns:
        str: Contenu du fichier (tronqué si très long).
    """
    if not nextcloud.is_configured():
        return _not_configured()
    if not (path or "").strip():
        return "Erreur : chemin de fichier requis."
    perr = _check_path(path)
    if perr:
        return perr
    url = _files_url(path)
    err = _guard(url)
    if err:
        return err
    try:
        r = requests.get(url, auth=nextcloud.auth(), timeout=_TIMEOUT)
        if r.status_code == 404:
            return f"Fichier introuvable : /{_safe_path(path)}"
        if r.status_code != 200:
            return f"Erreur Nextcloud ({r.status_code}) : {r.text[:200]}"
        text = r.text
        if len(text) > _MAX_READ:
            return text[:_MAX_READ] + "\n[...tronqué...]"
        return text
    except Exception as e:
        return f"Erreur lors de la lecture Nextcloud : {e}"


def nextcloud_write_file(path: str, content: str) -> str:
    """
    Écrit (crée ou remplace) un fichier texte sur Nextcloud.

    Args:
        path (str): Chemin du fichier relatif à ta racine. Ex: "Documents/notes.txt".
        content (str): Contenu texte à écrire.

    Returns:
        str: Message de confirmation.
    """
    if not projects.can_write():
        return "Erreur : écriture non autorisée (accès en lecture seule)."
    if not nextcloud.is_configured():
        return _not_configured()
    if not (path or "").strip():
        return "Erreur : chemin de fichier requis."
    perr = _check_path(path)
    if perr:
        return perr
    url = _files_url(path)
    err = _guard(url)
    if err:
        return err
    try:
        r = requests.put(url, auth=nextcloud.auth(),
                         data=(content or "").encode("utf-8"),
                         headers={"Content-Type": "text/plain; charset=utf-8"}, timeout=_TIMEOUT)
        if r.status_code in (200, 201, 204):
            return f"✅ Fichier enregistré sur Nextcloud : /{_safe_path(path)}"
        if r.status_code == 409:
            return ("Erreur : le dossier parent n'existe pas sur Nextcloud "
                    f"(crée-le d'abord). Chemin : /{_safe_path(path)}")
        return f"Erreur Nextcloud ({r.status_code}) : {r.text[:200]}"
    except Exception as e:
        return f"Erreur lors de l'écriture Nextcloud : {e}"


def nextcloud_delete_file(path: str) -> str:
    """
    Supprime un fichier ou dossier sur Nextcloud.

    Args:
        path (str): Chemin relatif à ta racine.

    Returns:
        str: Message de confirmation.
    """
    if not projects.can_write():
        return "Erreur : suppression non autorisée (accès en lecture seule)."
    if not nextcloud.is_configured():
        return _not_configured()
    perr = _check_path(path)
    if perr:
        return perr
    if not _safe_path(path):
        return "Erreur : refus de supprimer la racine."
    url = _files_url(path)
    err = _guard(url)
    if err:
        return err
    try:
        r = requests.delete(url, auth=nextcloud.auth(), timeout=_TIMEOUT)
        if r.status_code in (200, 204):
            return f"🗑️ Supprimé sur Nextcloud : /{_safe_path(path)}"
        if r.status_code == 404:
            return f"Déjà absent : /{_safe_path(path)}"
        return f"Erreur Nextcloud ({r.status_code}) : {r.text[:200]}"
    except Exception as e:
        return f"Erreur lors de la suppression Nextcloud : {e}"


# --- Helpers DAV (découverte de collections) --------------------------------
def _propfind_collections(base_url: str) -> List[str]:
    """Renvoie les URLs des collections enfants (depth 1) d'une base DAV."""
    body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
    r = requests.request("PROPFIND", base_url, auth=nextcloud.auth(),
                         headers={"Depth": "1", "Content-Type": "application/xml"},
                         data=body, timeout=_TIMEOUT)
    if r.status_code not in (207, 200):
        return []
    root = _xml_fromstring(r.content)
    ns = {"d": "DAV:"}
    base_path = urllib.parse.urlparse(base_url).path.rstrip("/")
    scheme_host = base_url.split(urllib.parse.urlparse(base_url).path)[0]
    cols = []
    for resp in root.findall("d:response", ns):
        href = resp.findtext("d:href", "", ns)
        hpath = urllib.parse.urlparse(href).path
        if hpath.rstrip("/") == base_path:
            continue
        if resp.find(".//d:collection", ns) is not None:
            cols.append(scheme_host + hpath)
    return cols


# --- TÂCHES (CalDAV / VTODO) ------------------------------------------------
def nextcloud_list_tasks() -> str:
    """
    Liste tes tâches Nextcloud (non terminées) tous calendriers de tâches confondus.

    Returns:
        str: Liste des tâches (titre, échéance si présente).
    """
    if not nextcloud.is_configured():
        return _not_configured()
    base = nextcloud.calendars_base()
    err = _guard(base)
    if err:
        return err
    report = ('<?xml version="1.0"?><c:calendar-query xmlns:d="DAV:" '
              'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data/></d:prop>'
              '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/>'
              '</c:comp-filter></c:filter></c:calendar-query>')
    tasks = []
    try:
        for col in _propfind_collections(base):
            if is_blocked_url(col):
                continue
            r = requests.request("REPORT", col, auth=nextcloud.auth(),
                                 headers={"Depth": "1", "Content-Type": "application/xml"},
                                 data=report, timeout=_TIMEOUT)
            if r.status_code not in (207, 200):
                continue
            for block in re.findall(r"BEGIN:VTODO.*?END:VTODO", r.text, re.DOTALL):
                if re.search(r"STATUS:COMPLETED", block):
                    continue
                summ = re.search(r"\nSUMMARY:(.+)", block)
                due = re.search(r"\nDUE[^:]*:(.+)", block)
                title = summ.group(1).strip() if summ else "(sans titre)"
                line = f"  ☐ {title}"
                if due:
                    line += f"  (échéance : {due.group(1).strip()[:16]})"
                tasks.append(line)
        if not tasks:
            return "✅ Aucune tâche en cours sur Nextcloud."
        return "🗒️ Tâches Nextcloud :\n" + "\n".join(tasks)
    except Exception as e:
        return f"Erreur lors de la lecture des tâches Nextcloud : {e}"


# --- CONTACTS (CardDAV) -----------------------------------------------------
def nextcloud_search_contacts(query: str = "") -> str:
    """
    Recherche un contact dans ton carnet d'adresses Nextcloud.

    Args:
        query (str): Texte à chercher (nom, email…). Vide = tout lister (limité).

    Returns:
        str: Contacts correspondants (nom, emails, téléphones).
    """
    if not nextcloud.is_configured():
        return _not_configured()
    base = nextcloud.addressbooks_base()
    err = _guard(base)
    if err:
        return err
    report = ('<?xml version="1.0"?><c:addressbook-query xmlns:d="DAV:" '
              'xmlns:c="urn:ietf:params:xml:ns:carddav"><d:prop><c:address-data/></d:prop>'
              '</c:addressbook-query>')
    q = (query or "").strip().lower()
    found = []
    try:
        for col in _propfind_collections(base):
            if is_blocked_url(col):
                continue
            r = requests.request("REPORT", col, auth=nextcloud.auth(),
                                 headers={"Depth": "1", "Content-Type": "application/xml"},
                                 data=report, timeout=_TIMEOUT)
            if r.status_code not in (207, 200):
                continue
            for card in re.findall(r"BEGIN:VCARD.*?END:VCARD", r.text, re.DOTALL):
                fn = re.search(r"\nFN[^:]*:(.+)", card)
                name = fn.group(1).strip() if fn else ""
                emails = [m.strip() for m in re.findall(r"\nEMAIL[^:]*:(.+)", card)]
                tels = [m.strip() for m in re.findall(r"\nTEL[^:]*:(.+)", card)]
                blob = f"{name} {' '.join(emails)} {' '.join(tels)}".lower()
                if q and q not in blob:
                    continue
                line = f"  👤 {name or '(sans nom)'}"
                if emails:
                    line += f" — {', '.join(emails)}"
                if tels:
                    line += f" — {', '.join(tels)}"
                found.append(line)
                if len(found) >= 30:
                    break
        if not found:
            return "Aucun contact trouvé." if q else "Carnet d'adresses vide."
        return "📇 Contacts Nextcloud :\n" + "\n".join(found)
    except Exception as e:
        return f"Erreur lors de la recherche de contacts Nextcloud : {e}"

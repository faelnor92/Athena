"""Synchronisation BIDIRECTIONNELLE des listes (courses, tâches…) avec Nextcloud Notes.

Quand elle est activée (par-utilisateur, optionnelle), Nextcloud est la SOURCE DE VÉRITÉ :
- une liste = une note Markdown (case à cocher) dans le dossier Notes de l'utilisateur ;
- toute mutation locale est poussée immédiatement dans la note ;
- les lectures rafraîchissent depuis Nextcloud (cache TTL court) et réconcilient par TEXTE
  pour préserver les identifiants locaux (le Markdown ne porte pas d'id).

Garde-fou anti-perte : si Nextcloud est injoignable / renvoie une erreur, on NE touche PAS
au cache local (on ne vide jamais une liste à cause d'un souci réseau).

Natif (WebDAV via requests), sans SDK. Le dossier « Notes » est celui de l'app Notes de
Nextcloud (réglable via LISTS_NEXTCLOUD_FOLDER).
"""
import os
import re
import time
import uuid
import urllib.parse

import requests

from core import nextcloud, user_config
from tools.net_guard import is_blocked_url

_TIMEOUT = 12
K_ENABLED = "LISTS_SYNC_NEXTCLOUD"
K_FOLDER = "LISTS_NEXTCLOUD_FOLDER"

# Cache de pull par (utilisateur, liste) -> (timestamp, items). TTL court : l'UI reste
# réactive tout en reflétant les éditions faites côté Nextcloud en quelques secondes.
_PULL_TTL = float(os.getenv("LISTS_SYNC_PULL_TTL", "20"))
_pull_cache: dict = {}


def is_enabled() -> bool:
    """Sync active pour l'utilisateur courant (toggle ON ET Nextcloud configuré)."""
    val = str(user_config.get(K_ENABLED, "") or "").strip().lower()
    return val in ("1", "true", "yes", "on") and nextcloud.is_configured()


def _folder() -> str:
    f = str(user_config.get(K_FOLDER, "") or os.getenv("LISTS_NEXTCLOUD_FOLDER", "") or "Notes").strip()
    return f.strip("/") or "Notes"


def _pretty(list_name: str) -> str:
    """Nom de fichier de note lisible pour une liste (ex. 'courses' -> 'Courses')."""
    base = (list_name or "liste").strip().replace("/", "-")
    return base[:1].upper() + base[1:]


def _note_url(list_name: str) -> str:
    segs = [_folder(), f"{_pretty(list_name)}.md"]
    quoted = "/".join(urllib.parse.quote(s) for s in segs)
    return nextcloud.files_base() + quoted


def _folder_url() -> str:
    return nextcloud.files_base() + urllib.parse.quote(_folder()) + "/"


def _render(list_name: str, items: list) -> str:
    """Liste -> Markdown (titre + cases à cocher)."""
    lines = [f"# {_pretty(list_name)}", ""]
    for it in items or []:
        box = "x" if it.get("completed") else " "
        lines.append(f"- [{box}] {it.get('text', '').strip()}")
    return "\n".join(lines) + "\n"


_LINE_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+?)\s*$")


def _parse(text: str) -> list:
    """Markdown -> [(texte, completed)] (ignore le titre et les lignes hors cases)."""
    out = []
    for line in (text or "").splitlines():
        m = _LINE_RE.match(line)
        if m:
            out.append((m.group(2).strip(), m.group(1).lower() == "x"))
    return out


def _reconcile(parsed: list, local_items: list) -> list:
    """Fusionne l'état distant (texte, completed) avec le local pour PRÉSERVER les id.
    Match par texte (insensible à la casse) ; nouveaux textes -> nouvel id ; les éléments
    absents du distant sont supprimés (Nextcloud fait foi)."""
    by_text = {}
    for it in local_items or []:
        by_text.setdefault((it.get("text", "").strip().lower()), it)
    result = []
    used = set()
    for text, completed in parsed:
        key = text.lower()
        src = by_text.get(key)
        if src and id(src) not in used:
            used.add(id(src))
            result.append({"id": src.get("id") or uuid.uuid4().hex[:12], "text": text, "completed": completed})
        else:
            result.append({"id": uuid.uuid4().hex[:12], "text": text, "completed": completed})
    return result


def _guarded(url: str) -> bool:
    return not is_blocked_url(url)


def push(list_name: str, items: list) -> bool:
    """Écrit la note Nextcloud correspondant à la liste. Best-effort (renvoie False si KO)."""
    if not is_enabled():
        return False
    try:
        # S'assure que le dossier existe (MKCOL idempotent : 201 créé / 405 déjà là).
        furl = _folder_url()
        if not _guarded(furl):
            return False
        try:
            requests.request("MKCOL", furl, auth=nextcloud.auth(), timeout=_TIMEOUT)
        except Exception:
            pass
        url = _note_url(list_name)
        if not _guarded(url):
            return False
        r = requests.put(url, auth=nextcloud.auth(),
                         data=_render(list_name, items).encode("utf-8"),
                         headers={"Content-Type": "text/markdown; charset=utf-8"}, timeout=_TIMEOUT)
        ok = r.status_code in (200, 201, 204)
        if ok:
            _pull_cache[(user_config.current_user_key(), list_name.lower())] = (time.time(), list(items or []))
        return ok
    except Exception:
        return False


def pull(list_name: str, local_items: list):
    """Renvoie les items réconciliés depuis Nextcloud, ou None si rien à faire / erreur
    (dans ce cas l'appelant garde le local — JAMAIS d'écrasement sur échec réseau)."""
    if not is_enabled():
        return None
    ck = (user_config.current_user_key(), list_name.lower())
    cached = _pull_cache.get(ck)
    if cached and (time.time() - cached[0]) < _PULL_TTL:
        return None  # frais : pas de re-fetch, le local fait foi entre deux TTL
    url = _note_url(list_name)
    if not _guarded(url):
        return None
    try:
        r = requests.get(url, auth=nextcloud.auth(), timeout=_TIMEOUT)
    except Exception:
        return None
    if r.status_code == 404:
        # La note n'existe pas encore côté Nextcloud → on la crée à partir du local.
        push(list_name, local_items)
        return None
    if r.status_code != 200:
        return None  # erreur transitoire : on garde le local
    reconciled = _reconcile(_parse(r.text), local_items)
    _pull_cache[ck] = (time.time(), reconciled)
    return reconciled


def list_remote_notes() -> list:
    """Noms de listes présentes côté Nextcloud (fichiers .md du dossier Notes)."""
    if not is_enabled():
        return []
    furl = _folder_url()
    if not _guarded(furl):
        return []
    body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
            '<d:resourcetype/></d:prop></d:propfind>')
    try:
        r = requests.request("PROPFIND", furl, auth=nextcloud.auth(),
                             headers={"Depth": "1", "Content-Type": "application/xml"},
                             data=body, timeout=_TIMEOUT)
        if r.status_code not in (207, 200):
            return []
        names = re.findall(r"/([^/<>]+)\.md</d:href>", r.text, flags=re.IGNORECASE)
        return [urllib.parse.unquote(n).lower() for n in names]
    except Exception:
        return []

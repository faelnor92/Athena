"""Registre MULTI-HÔTES SSH (admin) — pratique pour un admin sys : brancher plusieurs
serveurs et cibler celui qu'on veut (par commande / console codeur), au lieu de l'unique
hôte du `.env`.

- Stockage : `shared_store` ns « ssh_hosts » clé « registry » = liste de dicts. Données
  LOCALES (SQLite gitignoré). Secrets sensibles → préférer `key_path` à `password`.
- Rétro-compatible : l'hôte unique du `.env` (SSH_HOST…) reste disponible sous l'id « env ».
- SSH est admin-only ; ce registre l'est donc aussi (garde côté endpoint).
"""
import contextvars
import os
import uuid
from typing import List, Optional

from core import shared_store

_NS = "ssh_hosts"
_KEY = "registry"

# Hôte ACTIF pour le contexte courant (ContextVar) : posé par la console codeur pour cibler
# un serveur précis sur SON run, sans toucher les autres canaux.
_active = contextvars.ContextVar("ssh_active_host", default=None)


def set_active(host_id):
    """Force l'hôte SSH actif pour le contexte courant. Renvoie un token (reset_active)."""
    return _active.set(host_id or None)


def reset_active(token):
    try:
        _active.reset(token)
    except Exception:
        pass


def active_host():
    """Id de l'hôte SSH actif pour le contexte courant (ou None)."""
    return _active.get()


def _registry() -> List[dict]:
    return list(shared_store.get(_NS, _KEY) or [])


def effective_id(host_id: Optional[str] = None) -> Optional[str]:
    """Id d'hôte EFFECTIF : param explicite > hôte actif du contexte > 'env' > 1er du registre."""
    hid = host_id or _active.get()
    if hid:
        return hid
    if _env_host():
        return "env"
    reg = _registry()
    return reg[0].get("id") if reg else None


def _cwd_key(eid: str) -> str:
    """Clé de cwd distant PAR (utilisateur, hôte) → un `cd` indépendant par serveur."""
    try:
        from core.user_config import current_user_key
        u = current_user_key()
    except Exception:
        u = "local"
    return f"{u}:{eid}"


def get_cwd(host_id: Optional[str] = None) -> Optional[str]:
    """Répertoire de travail distant courant pour l'hôte effectif (ou None)."""
    eid = effective_id(host_id)
    if not eid:
        return None
    return shared_store.get("ssh_cwd", _cwd_key(eid))


def set_cwd(path: str, host_id: Optional[str] = None) -> None:
    """Mémorise le cwd distant pour l'hôte effectif (suivi du `cd` par serveur)."""
    eid = effective_id(host_id)
    if eid and path:
        shared_store.set("ssh_cwd", _cwd_key(eid), path)


def _env_host() -> Optional[dict]:
    """Hôte unique historique du `.env` (id='env'), ou None si SSH_HOST absent."""
    h = os.getenv("SSH_HOST")
    if not h:
        return None
    label = os.getenv("SSH_LABEL") or (f"{os.getenv('SSH_USERNAME', '')}@{h}".strip("@")) or h
    return {
        "id": "env", "label": label, "host": h,
        "port": int(os.getenv("SSH_PORT", "22") or 22),
        "username": os.getenv("SSH_USERNAME"), "password": os.getenv("SSH_PASSWORD"),
        "key_path": os.getenv("SSH_KEY_PATH"), "remote_cwd": os.getenv("SSH_REMOTE_CWD"),
        "known_hosts": os.getenv("SSH_KNOWN_HOSTS"),
        "auto_add": os.getenv("SSH_AUTO_ADD_HOST_KEYS", "False"),
    }


def list_hosts(mask: bool = True) -> List[dict]:
    """Tous les hôtes (env + registre). mask=True masque les secrets (affichage UI)."""
    out = []
    env = _env_host()
    if env:
        out.append(env)
    out.extend(_registry())
    if mask:
        out = [{**h, "password": ("***" if h.get("password") else ""),
                "has_key": bool(h.get("key_path"))} for h in out]
    return out


def resolve(host_id: Optional[str] = None) -> dict:
    """Config de connexion effective pour `host_id` (sinon hôte actif du contexte, sinon
    défaut .env, sinon 1er du registre). Les champs remote_cwd/known_hosts/auto_add absents
    retombent sur les valeurs du `.env`."""
    hid = host_id or _active.get()
    env = _env_host()
    chosen = None
    if hid:
        if hid == "env":
            chosen = env
        else:
            chosen = next((h for h in _registry() if h.get("id") == hid), None)
    if chosen is None:
        reg = _registry()
        chosen = env or (reg[0] if reg else {})
    base = {
        "remote_cwd": os.getenv("SSH_REMOTE_CWD"),
        "known_hosts": os.getenv("SSH_KNOWN_HOSTS"),
        "auto_add": os.getenv("SSH_AUTO_ADD_HOST_KEYS", "False"),
    }
    # Les valeurs non vides de l'hôte choisi priment sur les défauts .env.
    merged = {**base, **{k: v for k, v in (chosen or {}).items() if v not in (None, "")}}
    # Le `cd` SUIVI par hôte (s'il existe) prime sur le remote_cwd configuré → cwd
    # indépendant par serveur.
    tracked = get_cwd(host_id)
    if tracked:
        merged["remote_cwd"] = tracked
    return merged


def find(label_or_id: str) -> Optional[str]:
    """Renvoie l'id d'un hôte par son id OU son label (insensible à la casse), sinon None."""
    if not label_or_id:
        return None
    s = label_or_id.strip().lower()
    for h in list_hosts(mask=False):
        if str(h.get("id", "")).lower() == s or str(h.get("label", "")).lower() == s:
            return h.get("id")
    return None


def labels() -> str:
    """Libellés des hôtes disponibles (pour aiguiller un agent), ou '(aucun)'."""
    out = [h.get("label") or h.get("host") for h in list_hosts()]
    return ", ".join(o for o in out if o) or "(aucun)"


def add_host(label: str, host: str, username: str = "", port=22, password: str = "",
             key_path: str = "", remote_cwd: str = "", known_hosts: str = "",
             auto_add=False) -> dict:
    """Ajoute un hôte au registre. Renvoie l'entrée (secret masqué)."""
    if not (host or "").strip():
        raise ValueError("host requis")
    reg = _registry()
    entry = {
        "id": uuid.uuid4().hex[:8], "label": (label or host).strip(), "host": host.strip(),
        "port": int(port or 22), "username": (username or "").strip(),
        "password": password or "", "key_path": (key_path or "").strip(),
        "remote_cwd": (remote_cwd or "").strip(), "known_hosts": (known_hosts or "").strip(),
        "auto_add": "true" if auto_add in (True, "true", "1", "yes") else "false",
    }
    reg.append(entry)
    shared_store.set(_NS, _KEY, reg)
    return {**entry, "password": ("***" if entry["password"] else "")}


def remove_host(host_id: str) -> bool:
    """Retire un hôte du registre (l'hôte 'env' du .env n'est pas supprimable ici)."""
    reg = _registry()
    new = [h for h in reg if h.get("id") != host_id]
    if len(new) == len(reg):
        return False
    shared_store.set(_NS, _KEY, new)
    return True

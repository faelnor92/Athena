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


def _user_key() -> str:
    """Clé de registre PROPRE À L'UTILISATEUR courant : un hôte SSH (et ses identifiants)
    n'appartient qu'à l'utilisateur qui l'a déclaré — jamais partagé entre comptes."""
    from core import user_config
    return f"{_KEY}::{user_config.user_slug()}"


def _registry() -> List[dict]:
    cur = shared_store.get(_NS, _user_key())
    if cur is not None:
        return list(cur)
    # Migration douce : l'ancien registre GLOBAL (clé historique) revient à l'admin/local
    # à la 1ère lecture, puis devient privé. Les autres comptes démarrent vides.
    from core import user_config
    if user_config.current_user_key() in ("local", "admin"):
        legacy = shared_store.get(_NS, _KEY)
        if legacy:
            shared_store.set(_NS, _user_key(), legacy)
            return list(legacy)
    return []


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


def _all_user_registries() -> dict:
    """{user_slug: [hôtes]} pour TOUS les comptes (clés 'registry::<slug>')."""
    out = {}
    pref = _KEY + "::"
    for k, v in shared_store.items(_NS).items():
        if isinstance(k, str) and k.startswith(pref) and isinstance(v, list):
            out[k[len(pref):]] = v
    return out


def _shared_with_me() -> List[dict]:
    """Hôtes d'AUTRES utilisateurs explicitement PARTAGÉS avec l'utilisateur courant
    (champ `shared_with`). Permet d'autoriser le SSH d'un user sur le compte des satellites."""
    from core import user_config
    me = user_config.user_slug().lower()
    out = []
    for slug, hosts in _all_user_registries().items():
        if slug.lower() == me:
            continue
        for h in hosts:
            sw = [str(x).lower() for x in (h.get("shared_with") or [])]
            if me in sw:
                out.append({**h, "owner": slug, "shared": True})
    return out


def _accessible() -> List[dict]:
    """Hôtes accessibles à l'utilisateur courant : les SIENS + ceux partagés avec lui."""
    own = _registry()
    seen = {h.get("id") for h in own}
    return own + [h for h in _shared_with_me() if h.get("id") not in seen]


def share_host(host_id: str, username: str) -> bool:
    """Autorise `username` à utiliser l'hôte `host_id` de l'utilisateur COURANT (propriétaire).
    Renvoie True si l'autorisation a été ajoutée."""
    from core import user_config
    grantee = user_config.user_slug(username)
    reg = _registry()
    changed = False
    for h in reg:
        if h.get("id") == host_id:
            sw = h.setdefault("shared_with", [])
            if grantee not in sw:
                sw.append(grantee)
                changed = True
    if changed:
        shared_store.set(_NS, _user_key(), reg)
    return changed


def unshare_host(host_id: str, username: str) -> bool:
    """Retire l'autorisation de `username` sur l'hôte `host_id` de l'utilisateur courant."""
    from core import user_config
    grantee = user_config.user_slug(username)
    reg = _registry()
    changed = False
    for h in reg:
        if h.get("id") == host_id and grantee in (h.get("shared_with") or []):
            h["shared_with"] = [u for u in h["shared_with"] if u != grantee]
            changed = True
    if changed:
        shared_store.set(_NS, _user_key(), reg)
    return changed


def list_hosts(mask: bool = True) -> List[dict]:
    """Hôtes accessibles à l'utilisateur courant (les siens + partagés) + l'hôte .env.
    mask=True masque les secrets (affichage UI)."""
    out = []
    env = _env_host()
    if env:
        out.append(env)
    out.extend(_accessible())
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
            # Cherche parmi les hôtes ACCESSIBLES (les siens + ceux partagés avec lui) →
            # un hôte d'un autre user n'est résolu QUE s'il a été explicitement partagé.
            chosen = next((h for h in _accessible() if h.get("id") == hid), None)
    if chosen is None:
        acc = _accessible()
        chosen = env or (acc[0] if acc else {})
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
    """Renvoie l'id d'un hôte par son id OU son label (insensible à la casse). À défaut de
    correspondance exacte, tente une correspondance par SOUS-CHAÎNE UNIQUE (label ou hôte),
    pour qu'un agent puisse cibler « immich » → « VM Immich ». None si ambigu ou introuvable."""
    if not label_or_id:
        return None
    s = label_or_id.strip().lower()
    hosts = list_hosts(mask=False)
    for h in hosts:
        if str(h.get("id", "")).lower() == s or str(h.get("label", "")).lower() == s:
            return h.get("id")
    matches = [h for h in hosts
               if s in str(h.get("label", "")).lower() or s in str(h.get("host", "")).lower()]
    if len(matches) == 1:
        return matches[0].get("id")
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
    shared_store.set(_NS, _user_key(), reg)
    return {**entry, "password": ("***" if entry["password"] else "")}


def remove_host(host_id: str) -> bool:
    """Retire un hôte du registre (l'hôte 'env' du .env n'est pas supprimable ici)."""
    reg = _registry()
    new = [h for h in reg if h.get("id") != host_id]
    if len(new) == len(reg):
        return False
    shared_store.set(_NS, _user_key(), new)
    return True

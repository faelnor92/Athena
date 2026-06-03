"""Registre TRANSVERSAL de partage de projets (collaboration entre comptes).

project_id -> {owner, name, path, members: {username: "viewer"|"editor"}}

Permet à un propriétaire de partager un projet avec d'autres comptes selon un rôle.
Les fichiers restent physiquement chez le propriétaire ; les membres y accèdent via le
chemin enregistré (validé), en lecture seule (viewer) ou en écriture (editor).
Store JSON global (atomique + verrou).
"""
import json
import os
import tempfile
import threading

_LOCK = threading.Lock()
_DATA = {}
_LOADED = False


def _path():
    return os.getenv("SHARED_PROJECTS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared_projects.json")


def _load():
    global _LOADED
    if _LOADED:
        return
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                _DATA.update(d)
    except Exception:
        pass
    _LOADED = True


def _save():
    p = _path()
    try:
        fd, tmp = tempfile.mkstemp(prefix=".shproj-", suffix=".tmp", dir=os.path.dirname(os.path.abspath(p)) or ".")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_DATA, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def share(pid: str, owner: str, name: str, path: str, member: str, role: str = "viewer") -> bool:
    member = (member or "").strip()
    if not member or member == owner:
        return False
    role = role if role in ("viewer", "editor") else "viewer"
    with _LOCK:
        _load()
        entry = _DATA.setdefault(pid, {"owner": owner, "name": name, "path": path, "members": {}})
        entry.update({"owner": owner, "name": name, "path": path})
        entry.setdefault("members", {})[member] = role
        _save()
    return True


def unshare(pid: str, member: str) -> bool:
    with _LOCK:
        _load()
        e = _DATA.get(pid)
        if e and member in e.get("members", {}):
            del e["members"][member]
            if not e["members"]:
                del _DATA[pid]
            _save()
            return True
    return False


def get(pid: str):
    with _LOCK:
        _load()
        return _DATA.get(pid)


def members(pid: str) -> dict:
    e = get(pid)
    return dict(e.get("members", {})) if e else {}


def role_for(pid: str, user: str):
    """'owner' | 'editor' | 'viewer' | None pour un projet partagé."""
    e = get(pid)
    if not e:
        return None
    if e.get("owner") == user:
        return "owner"
    return e.get("members", {}).get(user)


def projects_for(user: str) -> list:
    """Projets PARTAGÉS avec `user` (membre), avec rôle et chemin."""
    with _LOCK:
        _load()
        out = []
        for pid, e in _DATA.items():
            role = e.get("members", {}).get(user)
            if role:
                out.append({"id": pid, "name": e.get("name", pid), "path": e.get("path", ""),
                            "shared": True, "owner": e.get("owner"), "role": role})
        return out


def remove_project(pid: str):
    """Supprime tout partage d'un projet (à sa suppression par le propriétaire)."""
    with _LOCK:
        _load()
        if pid in _DATA:
            del _DATA[pid]
            _save()

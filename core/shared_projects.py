"""Registre TRANSVERSAL de partage de projets (collaboration entre comptes).

project_id -> {owner, name, path, members: {username: "viewer"|"editor"}}

Permet à un propriétaire de partager un projet avec d'autres comptes selon un rôle.
Les fichiers restent physiquement chez le propriétaire ; les membres y accèdent via le
chemin enregistré (validé), en lecture seule (viewer) ou en écriture (editor).
Store JSON global (atomique + verrou).
"""
import os

from core import shared_store

_NS = "shared_projects"
_migrated = False


def _ensure_migrated():
    """Importe une fois un éventuel shared_projects.json hérité dans le store SQLite."""
    global _migrated
    if _migrated:
        return
    legacy = os.getenv("SHARED_PROJECTS_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared_projects.json")
    shared_store.migrate_json_dict(legacy, _NS)
    _migrated = True


def share(pid: str, owner: str, name: str, path: str, member: str, role: str = "viewer") -> bool:
    member = (member or "").strip()
    if not member or member == owner:
        return False
    role = role if role in ("viewer", "editor") else "viewer"
    _ensure_migrated()

    def _set(e):
        e = e or {"owner": owner, "name": name, "path": path, "members": {}}
        e.update({"owner": owner, "name": name, "path": path})
        e.setdefault("members", {})[member] = role
        return e
    shared_store.update(_NS, pid, _set)
    return True


def unshare(pid: str, member: str) -> bool:
    _ensure_migrated()
    outcome = {"ok": False}

    def _rm(e):
        if e and member in e.get("members", {}):
            del e["members"][member]
            outcome["ok"] = True
            if not e["members"]:
                return None  # plus aucun membre → suppression du partage
        return e
    if shared_store.get(_NS, pid) is None:
        return False
    shared_store.update(_NS, pid, _rm)
    return outcome["ok"]


def get(pid: str):
    _ensure_migrated()
    return shared_store.get(_NS, pid)


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
    _ensure_migrated()
    out = []
    for pid, e in shared_store.items(_NS).items():
        role = e.get("members", {}).get(user)
        if role:
            out.append({"id": pid, "name": e.get("name", pid), "path": e.get("path", ""),
                        "shared": True, "owner": e.get("owner"), "role": role})
    return out


def remove_project(pid: str):
    """Supprime tout partage d'un projet (à sa suppression par le propriétaire)."""
    _ensure_migrated()
    shared_store.delete(_NS, pid)

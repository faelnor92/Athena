"""Sauvegarde / restauration de l'état de Jarvis (archive ZIP).

Sauvegarde l'état local (conversations, mémoire core + vectorielle, runs,
routines, compétences, configs MCP/canaux/pricing) dans un seul .zip
téléchargeable, et le restaure depuis une archive.
"""
import glob
import io
import os
import zipfile


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _file_targets() -> list:
    root = _root()
    patterns = [
        "conversations.json", "conversations_*.json", "core_memory.json",
        "routines.json", "runs.sqlite3", "mcp_servers.json",
        "channel_policies.json", "workspace/pricing_config.json",
    ]
    out = []
    for pat in patterns:
        out += glob.glob(os.path.join(root, pat))
    return out


def _dir_targets() -> list:
    root = _root()
    candidates = [os.getenv("CHROMA_DB_PATH", ".chroma_db"), "skills"]
    dirs = []
    for d in candidates:
        p = d if os.path.isabs(d) else os.path.join(root, d)
        if os.path.isdir(p):
            dirs.append(p)
    return dirs


def make_backup() -> bytes:
    root = _root()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _file_targets():
            if os.path.isfile(f):
                z.write(f, os.path.relpath(f, root))
        for d in _dir_targets():
            for r, _dirs, files in os.walk(d):
                if "__pycache__" in r:
                    continue
                for fn in files:
                    fp = os.path.join(r, fn)
                    z.write(fp, os.path.relpath(fp, root))
    return buf.getvalue()


def restore_backup(data: bytes) -> dict:
    root = _root()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        # Sécurité : refuser toute entrée qui sortirait du dossier projet (zip-slip).
        for n in names:
            dest = os.path.abspath(os.path.join(root, n))
            if os.path.commonpath([dest, root]) != root:
                raise ValueError(f"Entrée d'archive non sûre : {n}")
        z.extractall(root)
    return {"restored": len(names)}

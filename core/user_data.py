"""Purge des données d'un utilisateur (suppression de compte / RGPD).

Efface, en best-effort, TOUT ce qui est propre à un compte : profil, mémoire clé-valeur,
mémoire-graphe, agenda + identifiants calendrier, listes, plans, routines, config
par-utilisateur, conversations, et la collection vectorielle (Chroma).
"""
import os
import glob


def _rm(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
            return True
    except Exception:
        pass
    return False


def purge_user(username: str) -> dict:
    """Supprime toutes les données de `username`. Renvoie un petit rapport."""
    from core.user_config import user_slug
    slug = user_slug(username)
    removed = []

    # 1. Fichiers à la racine (profil, mémoire, graphe), en respectant les overrides d'env.
    def _suffixed(base):
        root, ext = os.path.splitext(base)
        return f"{root}_{slug}{ext}"

    for base in (
        os.getenv("USER_PROFILE_PATH", "user_profile.md"),
        os.getenv("CORE_MEMORY_PATH", "core_memory.json"),
        os.getenv("GRAPH_MEMORY_PATH", "graph_memory.db"),
        os.getenv("GRAPH_MEMORY_PATH", "graph_memory.db") + "-wal",
        os.getenv("GRAPH_MEMORY_PATH", "graph_memory.db") + "-shm",
        os.getenv("GRAPH_MEMORY_PATH", "graph_memory.json"),
    ):
        if _rm(_suffixed(base)):
            removed.append(os.path.basename(_suffixed(base)))

    # 2. Fichiers du workspace (agenda, clé Google, listes).
    for pat in (f"agenda_{slug}.json", f"google_credentials_{slug}.json", f"lists_{slug}.json"):
        p = os.path.join("workspace", pat)
        if _rm(p):
            removed.append(pat)

    # 2b. Dossiers de PROJETS de l'utilisateur (workspace/projects/<slug>/).
    try:
        import shutil
        pdir = os.path.join("workspace", "projects", slug)
        if os.path.isdir(pdir):
            shutil.rmtree(pdir, ignore_errors=True)
            removed.append(f"projects/{slug}")
    except Exception:
        pass

    # 3. Conversations scopées (conversations_u_<user>_*.json) + variantes.
    try:
        base = os.getenv("CONVERSATIONS_PATH", "").strip() or "conversations.json"
        root, ext = os.path.splitext(base)
        for p in glob.glob(f"{root}_*{slug}*{ext}") + glob.glob(f"{root}*u_{slug}_*{ext}"):
            if _rm(p):
                removed.append(os.path.basename(p))
    except Exception:
        pass

    # 4. Stores en mémoire / structurés.
    try:
        from core import plan_store
        plan_store.purge_user(username)
        removed.append("plans")
    except Exception:
        pass
    try:
        from core.routines import routine_store
        for r in [x for x in routine_store.list() if (x.get("owner") or "local") == username]:
            routine_store.delete(r["id"])
        removed.append("routines")
    except Exception:
        pass
    try:
        from core import user_config
        if user_config.delete_user(username):
            removed.append("user_config")
    except Exception:
        pass

    # 5. Collection vectorielle (Chroma).
    try:
        from tools.memory_tools import semantic_mem
        if semantic_mem.drop_user(username):
            removed.append("rag_collection")
    except Exception:
        pass

    return {"user": username, "removed": removed}

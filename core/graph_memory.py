"""Mémoire-graphe légère : stocke des relations (sujet, relation, objet) et permet
d'interroger le VOISINAGE d'une entité — complément du RAG vectoriel (ChromaDB) qui,
lui, ne capture que la similarité de texte. Pur-Python (aucune dépendance), persistance
atomique. Ce n'est PAS du GraphRAG complet (pas d'extraction massive ni de communautés) :
juste un graphe de faits reliés, le « 20 % qui donne 80 % ».

PAR UTILISATEUR : chaque utilisateur a ses propres relations (graph_memory_<user>.json),
résolu à chaque accès via core.user_config.
"""
import json
import os
import tempfile
import threading

_LOCK = threading.Lock()
_BY_USER = {}      # user -> [{"s","r","o"}]
_LOADED = set()    # users déjà chargés
_MAX = int(os.getenv("GRAPH_MEMORY_MAX", "5000") or 5000)


def _key() -> str:
    from core.user_config import current_user_key
    return current_user_key()


def _path() -> str:
    base = os.getenv("GRAPH_MEMORY_PATH", "").strip() or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "graph_memory.json")
    from core.user_config import user_slug
    root, ext = os.path.splitext(base)
    return f"{root}_{user_slug()}{ext or '.json'}"


def _triples() -> list:
    """Liste de triplets de l'utilisateur courant (chargée paresseusement). Appeler sous _LOCK."""
    u = _key()
    if u not in _LOADED:
        data = []
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
                if isinstance(d, list):
                    data = d
        except Exception:
            pass
        _BY_USER[u] = data
        _LOADED.add(u)
    return _BY_USER.setdefault(u, [])


def _save():
    p = _path()
    directory = os.path.dirname(os.path.abspath(p)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".graph-", suffix=".tmp", dir=directory)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_BY_USER.get(_key(), [])[-_MAX:], f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def _norm(x):
    return " ".join((x or "").strip().split())


def add_triple(s, r, o):
    s, r, o = _norm(s), _norm(r), _norm(o)
    if not s or not o:
        return False
    with _LOCK:
        triples = _triples()
        key = (s.lower(), r.lower(), o.lower())
        if any((t["s"].lower(), t["r"].lower(), t["o"].lower()) == key for t in triples):
            return True  # déjà connu
        triples.append({"s": s, "r": r, "o": o})
        _save()
    return True


def add_triples(triples):
    n = 0
    for t in triples or []:
        if isinstance(t, (list, tuple)) and len(t) >= 3:
            if add_triple(t[0], t[1], t[2]):
                n += 1
        elif isinstance(t, dict):
            if add_triple(t.get("s"), t.get("r"), t.get("o")):
                n += 1
    return n


def neighborhood(entity, depth=1):
    """Renvoie les triplets touchant `entity` (sujet OU objet), étendus de `depth` sauts."""
    ent = _norm(entity).lower()
    if not ent:
        return []
    with _LOCK:
        triples = list(_triples())
    seen_entities = {ent}
    result = []
    frontier = {ent}
    for _ in range(max(1, depth)):
        next_frontier = set()
        for t in triples:
            if t in result:
                continue
            sl, ol = t["s"].lower(), t["o"].lower()
            # match par sous-chaîne tolérant (ex. "olympe" ∈ "les larmes de l'olympe")
            if any(f and (f in sl or sl in f or f in ol or ol in f) for f in frontier):
                result.append(t)
                for e in (sl, ol):
                    if e not in seen_entities:
                        seen_entities.add(e)
                        next_frontier.add(e)
        frontier = next_frontier
        if not frontier:
            break
    return result


def stats():
    with _LOCK:
        return {"triples": len(_triples())}

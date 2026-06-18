"""Routage d'outils SÉMANTIQUE et MULTILINGUE (avec repli mots-clés).

Sélectionne les outils GROUPÉS à exposer au modèle par similarité d'embeddings entre la
requête et (nom + 1ʳᵉ ligne de docstring) de chaque outil — donc INDÉPENDANT DE LA LANGUE :
« enciende la luz » (ES) ou « accendi la luce » (IT) activent la domotique, là où les
mots-clés FR/EN codés en dur étaient à la ramasse.

Réutilise l'embedding déjà en place (core.memory) : bge-m3 via endpoint si configuré
(multilingue, idéal), sinon l'embedder local par défaut de ChromaDB (all-MiniLM). Si aucun
embedder n'est disponible, on retombe sur le routage par mots-clés (select_tool_subset).

Sûreté identique au keyword : les outils HORS groupe (cœur) sont TOUJOURS gardés ; on ne
filtre que le SCHÉMA exposé, jamais l'exécution (cf. _secured_tools dans le moteur). Donc
zéro perte de capacité. Désactivable via TOOL_ROUTER=keyword.
"""
import os
import threading

from core.swarm.text_tools import select_tool_subset, _TOOL_DOMAIN

_lock = threading.Lock()
_embedder = None
_embedder_tried = False
_tool_vecs = {}            # nom d'outil -> vecteur normalisé (np.ndarray), calculé une fois
_fail_until = 0.0          # disjoncteur : tant que time < _fail_until, on saute le sémantique


def _semantic_disabled() -> bool:
    import time
    return time.time() < _fail_until


def _trip_breaker():
    """Coupe le sémantique pour un moment après un échec d'embedding (endpoint down/lent) :
    évite de payer un timeout HTTP à CHAQUE tour. On retombe sur le keyword en attendant."""
    global _fail_until
    import time
    try:
        cooldown = float(os.getenv("TOOL_ROUTER_COOLDOWN", "300") or 300)
    except ValueError:
        cooldown = 300.0
    _fail_until = time.time() + cooldown


def _np():
    import numpy as np
    return np


def _get_embedder():
    """Embedder réutilisable : bge-m3 (http) → all-MiniLM (Chroma local) → None.
    Résolu une seule fois (l'échec d'init est mémorisé pour ne pas le retenter à chaque tour)."""
    global _embedder, _embedder_tried
    if _embedder_tried:
        return _embedder
    with _lock:
        if _embedder_tried:
            return _embedder
        ef = None
        # 1) Endpoint configuré (bge-m3…) — multilingue, partagé avec la mémoire.
        try:
            from core.memory import _embedding_function
            ef = _embedding_function()
        except Exception:
            ef = None
        # 2) Repli local : embedder par défaut de ChromaDB (all-MiniLM, déjà installé).
        if ef is None:
            try:
                from chromadb.utils import embedding_functions as _cef
                ef = _cef.DefaultEmbeddingFunction()
            except Exception:
                ef = None
        _embedder = ef
        _embedder_tried = True
    return _embedder


def _encode(texts):
    """Encode une liste de textes en vecteurs L2-normalisés, ou None si indisponible."""
    ef = _get_embedder()
    if ef is None:
        return None
    texts = [str(t) for t in texts]
    try:
        vecs = ef(texts)
    except TypeError:
        try:
            vecs = ef(input=texts)
        except Exception:
            return None
    except Exception:
        return None
    if vecs is None or len(vecs) == 0:
        return None
    np = _np()
    arr = np.asarray(vecs, dtype="float32")
    if arr.ndim != 2:
        return None
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def _tool_text(func) -> str:
    name = getattr(func, "__name__", "")
    doc = (getattr(func, "__doc__", "") or "").strip().split("\n")[0]
    return f"{name.replace('_', ' ')}. {doc}"


def _ensure_tool_vecs(grouped_funcs) -> bool:
    """Calcule (et met en cache) les vecteurs des outils groupés pas encore connus."""
    missing = [f for f in grouped_funcs if f.__name__ not in _tool_vecs]
    if not missing:
        return True
    vecs = _encode([_tool_text(f) for f in missing])
    if vecs is None:
        return False
    with _lock:
        for f, v in zip(missing, vecs):
            _tool_vecs[f.__name__] = v
    return True


def _select_semantic(query: str, available_funcs):
    """Outils groupés sémantiquement proches, par ÉCART-AU-MEILLEUR (gap). Renvoie un set de
    noms d'outils GROUPÉS (sans le cœur), ou None si l'embedding est indisponible.

    Pourquoi le gap et non un seuil absolu : les similarités d'un embedder (bge-m3…) sont
    compressées et de niveau variable → un seuil fixe sur/sous-expose selon la requête. On
    garde donc les outils à moins de TOOL_ROUTER_GAP du MEILLEUR score : si un domaine se
    détache nettement (« enciende la luz » → domotique), on est précis ; si tout se vaut
    (requête hors-sujet/ambiguë), on garde large (sûr : sur-exposer ne coûte que des tokens).
    """
    grouped = [f for f in available_funcs if _TOOL_DOMAIN.get(f.__name__) is not None]
    if not grouped:
        return set()
    if not _ensure_tool_vecs(grouped):
        _trip_breaker()
        return None
    qv = _encode([query or ""])
    if qv is None:
        _trip_breaker()
        return None
    np = _np()
    q = qv[0]
    scores = {}
    for f in grouped:
        v = _tool_vecs.get(f.__name__)
        if v is not None:
            scores[f.__name__] = float(np.dot(q, v))
    if not scores:
        return set()
    mx = max(scores.values())
    try:
        gap = float(os.getenv("TOOL_ROUTER_GAP", "0.06") or 0.06)
    except ValueError:
        gap = 0.06
    return {name for name, s in scores.items() if s >= mx - gap}


def select_tools(query: str, available_funcs) -> set:
    """Point d'entrée du moteur. UNION keyword (précis FR/EN) + sémantique (multilingue).

    `available_funcs` : fonctions-outils candidates (besoin des docstrings pour l'embedding).
    Renvoie le set de NOMS à exposer = cœur (toujours) ∪ groupes activés par mots-clés
    ∪ groupes sémantiquement proches. L'union évite de manquer un outil : le keyword rattrape
    ce que le sémantique rate (ex. « git commit »), le sémantique rattrape les autres langues
    et paraphrases (« enciende la luz », « accendi la luce ») que le keyword FR/EN ignore.
    Repli pur keyword si embedding indisponible ou TOOL_ROUTER=keyword.
    """
    names = {f.__name__ for f in available_funcs}
    keyword_keep = select_tool_subset(query, names)        # cœur + groupes par mots-clés
    mode = (os.getenv("TOOL_ROUTER", "semantic") or "semantic").strip().lower()
    if mode == "keyword" or _semantic_disabled():
        return keyword_keep
    sem = _select_semantic(query, available_funcs)
    if sem is None:
        return keyword_keep                                # embedding KO → keyword seul
    return keyword_keep | sem                              # union : le meilleur des deux

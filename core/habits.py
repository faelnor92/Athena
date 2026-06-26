"""Proactivité ÉMERGENTE : observe les habitudes (requêtes récurrentes à heure régulière) dans
l'historique des runs et PROPOSE de créer une routine. « Tu demandes la météo chaque matin ~8h →
créer une routine météo 8h ? ».

Détection NON-LLM (cheap, sûre par construction) : on regroupe les messages utilisateur par
signature de mots-clés + tranche horaire, et on retient ceux qui reviennent sur ≥ N jours distincts.
Limite v1 : signature lexicale (les paraphrases franches ne se regroupent pas) → améliorable plus
tard par clustering d'embeddings. Les propositions passent par l'utilisateur (création = HITL).
"""
import os
import re
import time
from collections import defaultdict
from datetime import datetime

# Mots vides FR/EN courants à ignorer dans la signature.
_STOP = {
    "quel", "quelle", "quels", "quelles", "est", "les", "des", "une", "mon", "mes", "pour",
    "avec", "dans", "sur", "que", "qui", "quoi", "comment", "aujourd", "hui", "demain", "stp",
    "merci", "peux", "tu", "moi", "fais", "donne", "dis", "what", "the", "for", "and", "you",
    "please", "give", "show", "tell", "this", "that", "have", "are", "can",
}


def enabled() -> bool:
    return os.getenv("HABIT_MINING", "true").lower() in ("true", "1", "yes")


def _signature(msg: str):
    """Signature lexicale stable : jusqu'aux 3 mots-clés les plus longs (≥4 lettres, hors stopwords)."""
    words = re.findall(r"[a-zàâäéèêëîïôöùûüç0-9]{4,}", msg.lower())
    words = [w for w in dict.fromkeys(words) if w not in _STOP]  # uniques, ordre conservé
    words.sort(key=len, reverse=True)
    return tuple(sorted(words[:3]))


def mine_habits(days: int = 14, min_days: int = 3, user: str = None) -> list:
    """Renvoie les habitudes détectées : [{hour, count, days, example, signature}], triées par
    récurrence décroissante. `days` = fenêtre d'observation ; `min_days` = nb de jours distincts
    minimum pour qu'un motif compte comme habitude."""
    since = time.time() - days * 86400
    try:
        runs = run_list(limit=3000, user=user)
    except Exception:
        return []
    # Candidats : (ts, message) des vraies requêtes utilisateur dans la fenêtre.
    cands = []
    for r in runs:
        ts = r.get("created_at") or 0
        if ts < since:
            continue
        if (r.get("status") or "") in ("vigie", "routine", "error"):
            continue
        msg = (r.get("user_message") or "").strip()
        if not msg or msg.startswith("["):  # ignore messages système/Vigie/routine
            continue
        cands.append((ts, msg))
    if not cands:
        return []

    # Regroupement SÉMANTIQUE par embeddings (regroupe les paraphrases) ; repli LEXICAL si indispo.
    clusters = _cluster_embeddings(cands)
    if clusters is None:
        clusters = _cluster_lexical(cands)

    out = []
    for items in clusters:
        distinct_days = {datetime.fromtimestamp(t).date() for t, _ in items}
        if len(distinct_days) < min_days:
            continue
        # Heure dominante du motif (mode), et exemple le plus récent.
        hours = [datetime.fromtimestamp(t).hour for t, _ in items]
        hour = max(set(hours), key=hours.count)
        latest = max(items, key=lambda x: x[0])[1]
        out.append({
            "hour": hour,
            "count": len(items),
            "days": len(distinct_days),
            "example": latest[:120],
            "signature": list(_signature(latest)),
        })
    out.sort(key=lambda x: (-x["days"], -x["count"]))
    return out[:10]


def _cluster_lexical(cands):
    """Repli sans embeddings : regroupe par signature lexicale (mots-clés)."""
    groups = defaultdict(list)
    for ts, msg in cands:
        sig = _signature(msg)
        if sig:
            groups[sig].append((ts, msg))
    return list(groups.values())


def _cluster_embeddings(cands):
    """Regroupement par similarité sémantique (embeddings) : clustering glouton en ligne. Renvoie
    une liste de clusters [(ts, msg), …], ou None si les embeddings sont indisponibles."""
    try:
        from core.tool_router import embed_texts
        vecs = embed_texts([m for _, m in cands])
    except Exception:
        return None
    if not vecs or len(vecs) != len(cands):
        return None
    import math
    try:
        thr = float(os.getenv("HABIT_SIM_THRESHOLD", "0.78"))
    except Exception:
        thr = 0.78

    def _cos(a, b):
        s = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return s / (na * nb) if na and nb else 0.0

    clusters = []  # [{"centroid": vec, "items": [...], "n": k}]
    for (ts, msg), v in zip(cands, vecs):
        best, best_sim = None, thr
        for cl in clusters:
            sim = _cos(v, cl["centroid"])
            if sim >= best_sim:
                best, best_sim = cl, sim
        if best is None:
            clusters.append({"centroid": list(v), "items": [(ts, msg)], "n": 1})
        else:
            n = best["n"]
            best["centroid"] = [(c * n + x) / (n + 1) for c, x in zip(best["centroid"], v)]
            best["n"] = n + 1
            best["items"].append((ts, msg))
    return [cl["items"] for cl in clusters]


def run_list(limit: int = 3000, user: str = None):
    from core.tracing import run_store
    return run_store.list(limit=limit, user=user)

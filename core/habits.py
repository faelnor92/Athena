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
    groups = defaultdict(list)  # (signature, hour) -> [(ts, msg)]
    for r in runs:
        ts = r.get("created_at") or 0
        if ts < since:
            continue
        if (r.get("status") or "") in ("vigie", "routine", "error"):
            continue
        msg = (r.get("user_message") or "").strip()
        if not msg or msg.startswith("["):  # ignore messages système/Vigie/routine
            continue
        sig = _signature(msg)
        if not sig:
            continue
        hour = datetime.fromtimestamp(ts).hour
        groups[(sig, hour)].append((ts, msg))
    out = []
    for (sig, hour), items in groups.items():
        distinct_days = {datetime.fromtimestamp(t).date() for t, _ in items}
        if len(distinct_days) >= min_days:
            out.append({
                "hour": hour,
                "count": len(items),
                "days": len(distinct_days),
                "example": items[-1][1][:120],
                "signature": list(sig),
            })
    out.sort(key=lambda x: (-x["days"], -x["count"]))
    return out[:10]


def run_list(limit: int = 3000, user: str = None):
    from core.tracing import run_store
    return run_store.list(limit=limit, user=user)

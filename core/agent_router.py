"""Routeur de DÉLÉGATION sémantique — ZÉRO appel LLM.

Décide une fois par run si la demande relève d'un agent spécialiste, par similarité
d'embeddings entre la requête (3 derniers messages utilisateur) et la description de chaque
agent. Remplace l'ancien « juge LLM » (un appel de complétion en plus à chaque run, lent,
facturé, biaisé vers « aucun », limité au dernier message). Multilingue et instantané :
réutilise l'embedder de core.tool_router (bge-m3 via endpoint → all-MiniLM local → indispo).

Contrat (identique à l'ancien _route_target, pour ne rien changer dans la boucle) :
- NOM d'agent → un spécialiste se détache nettement → forcer la délégation,
- "" → aucun spécialiste pertinent → l'orchestrateur répond lui-même,
- None → routeur indisponible (embedder KO) → ne RIEN restreindre (le modèle décide).

Conservateur : on ne délègue QUE si le meilleur agent dépasse un PLANCHER et garde un ÉCART
net avec le 2e (sinon « aucun »). Évite la sur-délégation tout en captant les cas francs —
y compris dans une autre langue, là où l'ancien juge biaisait vers « aucun ».
"""
import os
import threading

from core import tool_router

_lock = threading.Lock()
_agent_vecs = {}   # nom agent -> (texte_source, vecteur) ; le texte sert à invalider le cache
_tls = threading.local()  # candidats de la DERNIÈRE décision ambiguë (par thread de run)


def last_candidates() -> list:
    """Top-candidats de la dernière décision AMBIGUË de `route()` sur ce thread (ou []).
    Permet au moteur d'injecter un indice doux (« relève de X ou Y ») sans restreindre."""
    return list(getattr(_tls, "candidates", []) or [])


def _agent_desc(agent) -> str:
    desc = (getattr(agent, "description", "") or "").strip()
    if not desc and getattr(agent, "system_prompt", ""):
        sents = [s.strip() for s in agent.system_prompt.replace("\n", " ").split(".") if s.strip()]
        desc = ". ".join(sents[:2])
    return desc


def route(agents: dict, orch_name: str, messages: list):
    """Renvoie le nom de l'agent cible, "" (aucun), ou None (indécis/indispo). Voir module."""
    _tls.candidates = []
    if os.getenv("DELEGATION_ROUTER", "true").lower() not in ("true", "1", "yes"):
        return None
    specialists = {n: a for n, a in agents.items() if n != orch_name}
    if not specialists:
        return ""

    recent = [str(m.get("content", "")) for m in messages if m.get("role") == "user"][-3:]
    query = "\n".join(recent).strip()
    if not query or len(query) < 10:
        return ""

    named, texts = [], []
    for n, a in specialists.items():
        d = _agent_desc(a)
        if d:
            named.append(n)
            texts.append(f"{(getattr(a, 'display_name', '') or n)}. {d}")
    if not named:
        return ""

    # Embeddings des descriptions (cache, recalcul seulement si la description a changé).
    missing = [(n, t) for n, t in zip(named, texts)
               if _agent_vecs.get(n, ("", None))[0] != t]
    if missing:
        vecs = tool_router.embed_texts([t for _, t in missing])
        if vecs is None:
            return None  # embedder KO → ne pas restreindre (on reste zéro-LLM)
        with _lock:
            for (n, t), v in zip(missing, vecs):
                _agent_vecs[n] = (t, v)

    qv = tool_router.embed_texts([query])
    if qv is None:
        return None
    import numpy as np
    q = qv[0]
    scores = {n: float(np.dot(q, _agent_vecs[n][1])) for n in named if n in _agent_vecs}
    if not scores:
        return ""

    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best, best_s = ordered[0]
    second_s = ordered[1][1] if len(ordered) > 1 else 0.0
    # Seuils calibrés pour bge-m3 (similarités compressées). Ajustables si un autre embedder
    # change l'échelle. Décision à 3 niveaux pour ÉVITER de pénaliser les cas ambigus :
    def _f(key, d):
        try:
            return float(os.getenv(key, str(d)) or d)
        except ValueError:
            return d
    floor = _f("DELEGATION_ROUTER_MIN", 0.50)        # match FRANC (force la délégation)
    gap = _f("DELEGATION_ROUTER_GAP", 0.04)          # écart net avec le 2e
    general = _f("DELEGATION_ROUTER_GENERAL", 0.45)   # sous ce seuil = rien de pertinent

    if best_s >= floor and (best_s - second_s) >= gap:
        # Un spécialiste se détache nettement → on force la délégation.
        print(f"[\033[95mRouteur délégation\033[0m] → {best} (score {best_s:.2f}, 2e {second_s:.2f})")
        return best
    if best_s < general:
        # Aucun agent pertinent (chit-chat, question générale) → l'orchestrateur répond seul.
        return ""
    # Zone AMBIGUË (pertinent mais pas de vainqueur net, ex. deux agents techniques) : on NE
    # restreint PAS → l'orchestrateur garde ses outils delegate_to_/transfer_to_ et tranche
    # lui-même (un LLM distingue « débugge » → Codeur mieux que l'écart d'embeddings).
    # On mémorise les top-candidats : le moteur les injecte en indice doux dans le préambule.
    _tls.candidates = [n for n, s in ordered[:2] if s >= general]
    return None

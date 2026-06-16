"""Pile de contextes (« fil d'Ariane ») PAR SESSION.

Permet de METTRE DE CÔTÉ la tâche/conversation en cours (PUSH) pour traiter une
parenthèse, puis de REPRENDRE exactement où on s'était arrêté (POP).

S'appuie sur l'ARBRE de conversation natif : chaque message porte un id + parent_id, et
le fil actif est le chemin jusqu'à `active_node_id`. Un PUSH ne copie donc PAS l'historique
— il mémorise simplement le `active_node_id` courant (+ agent actif + conteneur sandbox)
puis repart sur une branche neuve ; un POP restaure le `active_node_id` parqué. La sandbox
Docker associée est gelée (`docker pause`) au PUSH et relancée (`unpause`) au POP.

Pile persistée par session (shared_store) → survit à un redémarrage.
"""
import time
from core import shared_store

_NS = "context_stack"


def _stack(session_key: str) -> list:
    return list(shared_store.get(_NS, session_key) or [])


def depth(session_key: str) -> int:
    return len(_stack(session_key))


def push(session_key: str, frame: dict) -> None:
    def _f(cur):
        cur = list(cur or [])
        cur.append(frame)
        return cur
    shared_store.update(_NS, session_key, _f)


def pop(session_key: str):
    out = {"frame": None}

    def _f(cur):
        cur = list(cur or [])
        if cur:
            out["frame"] = cur.pop()
        return cur
    shared_store.update(_NS, session_key, _f)
    return out["frame"]


def peek(session_key: str):
    s = _stack(session_key)
    return s[-1] if s else None


def topics(session_key: str) -> list:
    return [f.get("topic", "(sans titre)") for f in _stack(session_key)]


def new_frame(topic: str, node_id, active_agent: str, container_key, paused: bool) -> dict:
    import uuid
    return {
        "frame_id": uuid.uuid4().hex[:12],
        "topic": (topic or "parenthèse").strip()[:120],
        "node_id": node_id,
        "active_agent": active_agent,
        "container_key": container_key,
        "paused": bool(paused),
        "created_at": time.time(),
    }

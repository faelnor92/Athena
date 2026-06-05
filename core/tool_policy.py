"""Allowlist / denylist d'outils PAR SESSION (contexte d'exécution), façon OpenClaw.

Complète les politiques par CANAL (`core.channels`, globales/config) par une politique
RUNTIME, scopée au run courant via ContextVar : un appelant (console de code, sous-agent
délégué, « mode restreint »…) peut clamper exactement les outils disponibles pour SON run,
sans toucher la config globale. Se propage aux threads (to_thread copie le contexte).

Règles : `deny` est prioritaire sur `allow`. `allow=None` ⇒ tous autorisés (sauf deny).
Les motifs peuvent être un nom exact OU un préfixe terminé par `*` (ex: "transfer_to_*").
"""
import contextvars
from typing import Iterable, Optional, Set, Tuple

_allow: contextvars.ContextVar = contextvars.ContextVar("tool_allow", default=None)
_deny: contextvars.ContextVar = contextvars.ContextVar("tool_deny", default=None)


def _norm(items: Optional[Iterable[str]]) -> Optional[Set[str]]:
    if items is None:
        return None
    return {str(s).strip() for s in items if str(s).strip()}


def set_policy(allow: Optional[Iterable[str]] = None,
               deny: Optional[Iterable[str]] = None) -> Tuple:
    """Pose une politique pour le contexte courant. Renvoie un token à passer à reset_policy."""
    return (_allow.set(_norm(allow)), _deny.set(_norm(deny)))


def reset_policy(token: Tuple) -> None:
    try:
        _allow.reset(token[0])
        _deny.reset(token[1])
    except Exception:
        pass


def active() -> bool:
    """Vrai si une politique runtime (allow ou deny) est posée pour ce contexte."""
    return _allow.get() is not None or bool(_deny.get())


def _match(name: str, patterns: Set[str]) -> bool:
    for p in patterns:
        if p.endswith("*"):
            if name.startswith(p[:-1]):
                return True
        elif name == p:
            return True
    return False


def allowed(tool_name: str) -> bool:
    """L'outil `tool_name` est-il autorisé par la politique runtime courante ?"""
    deny = _deny.get()
    if deny and _match(tool_name, deny):
        return False
    allow = _allow.get()
    if allow is None:
        return True
    return _match(tool_name, allow)

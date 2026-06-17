"""Package `core.swarm` — moteur multi-agents d'Athena.

Découpé (v0.23) depuis l'ancien module monolithique `core/swarm.py` :
- `engine`     : la classe `Swarm` (boucle `run`, routage, complétion, apprentissage) + `AVAILABLE_TOOLS`.
- `schema`     : conversion fonction→schéma d'outil + coercition/validation des arguments.
- `text_tools` : sélection d'outils par pertinence, récupération de tool-calls en texte,
                 détection d'intention annoncée, chargement des skills dynamiques.

Ce `__init__` RÉ-EXPORTE l'API publique historique : tout `from core.swarm import X`
existant continue de fonctionner à l'identique.
"""
# `completion` exposé ICI (et non plus dans le moteur) : c'est le point monkeypatchable
# historique. Le moteur l'appelle via `core.swarm.completion` (cf. engine._completion).
from litellm import completion

from core.agent import Agent, Result
from core.swarm.schema import (
    function_to_schema,
    coerce_arguments,
    validate_args_schema,
)
from core.swarm.text_tools import (
    looks_like_announced_intent,
    select_tool_subset,
    select_relevant_funcs,
    parse_text_tool_calls,
    load_dynamic_skills,
)
from core.swarm.engine import Swarm, AVAILABLE_TOOLS
# État/constantes de niveau module ré-exportés pour compat (lus par le code et les tests
# via `core.swarm.X`). Ce sont les MÊMES objets que dans le moteur : muter `_TOOL_CACHE`
# ou `_delegate_depth` ici agit bien sur la boucle du moteur.
from core.swarm.engine import (
    DELEGATE_BLOCKED_TOOLS,
    _delegate_depth,
    _TOOL_CACHE,
    _TOOL_CACHE_LOCK,
    _cacheable_tools,
    _tool_cache_ttl,
    _push_approval_notice,
    SwarmStepsList,
)

__all__ = [
    "Agent", "Result", "Swarm", "AVAILABLE_TOOLS", "completion",
    "function_to_schema", "coerce_arguments", "validate_args_schema",
    "looks_like_announced_intent", "select_tool_subset", "select_relevant_funcs",
    "parse_text_tool_calls", "load_dynamic_skills",
    "DELEGATE_BLOCKED_TOOLS", "_delegate_depth", "_TOOL_CACHE",
]

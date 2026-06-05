import json
from typing import List, Callable, Optional, Dict, Any

class Agent:
    """Représente un agent dans l'essaim."""
    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str = "gpt-4o",
        tools: Optional[List[Callable]] = None,
        handoffs: Optional[List[str]] = None,
        supports_tools: bool = True,
        display_name: Optional[str] = None,
        welcome_message: Optional[str] = None,
        description: str = "",
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.tools = tools or []
        self.handoffs = handoffs or []
        self.supports_tools = supports_tools
        self.display_name = display_name
        self.welcome_message = welcome_message
        # Spécialité de l'agent, en une phrase, pour le ROUTAGE (mini-routeur) et les
        # docstrings de transfer_to_/delegate_to_. Bien plus fiable que de scraper la 1ʳᵉ
        # phrase du system_prompt. Renseignée à la création (create_agent) ; vide = repli.
        self.description = (description or "").strip()

class Result:
    """Résultat de l'exécution d'une fonction d'outil (Tool).
    Peut contenir une valeur de retour, éventuellement un agent vers lequel transférer,
    et des mises à jour de l'ÉTAT PARTAGÉ du run (context_variables, façon openai/swarm)."""
    def __init__(self, value: str = "", agent: Optional[Agent] = None,
                 context_variables: Optional[Dict[str, Any]] = None):
        self.value = value
        self.agent = agent
        self.context_variables = context_variables or {}

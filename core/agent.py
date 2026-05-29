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
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.tools = tools or []
        self.handoffs = handoffs or []
        self.supports_tools = supports_tools
        self.display_name = display_name
        self.welcome_message = welcome_message

class Result:
    """Résultat de l'exécution d'une fonction d'outil (Tool).
    Peut contenir une valeur de retour, et éventuellement un agent vers lequel transférer."""
    def __init__(self, value: str = "", agent: Optional[Agent] = None):
        self.value = value
        self.agent = agent

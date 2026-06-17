"""Conversion fonction Python → schéma d'outil OpenAI + coercition/validation des arguments.

Fonctions PURES (sans état du Swarm) extraites de l'ancien `core/swarm.py` :
- `function_to_schema` : signature + docstring → schéma `tools` exposé au modèle.
- `coerce_arguments` / `_coerce_value` : rattrapent les types fournis en string par le LLM.
- `validate_args_schema` : valide contre le schéma JSON d'un outil MCP.
"""
import inspect
import json
from typing import Callable

from core import approvals


def _annotation_to_json_type(annotation) -> str:
    """Mappe une annotation Python vers un type JSON Schema. Défaut: string."""
    import typing
    direct = {
        str: "string", int: "integer", float: "number",
        bool: "boolean", list: "array", dict: "object",
    }
    if annotation in direct:
        return direct[annotation]
    origin = typing.get_origin(annotation)
    if origin in (list, tuple, set):
        return "array"
    if origin is dict:
        return "object"
    # Optional[X] / Union[...] : on prend le 1er argument non-None.
    if origin is typing.Union:
        for arg in typing.get_args(annotation):
            if arg is not type(None):
                return _annotation_to_json_type(arg)
    return "string"


def function_to_schema(func: Callable) -> dict:
    """Convertit une fonction Python en schéma d'outil OpenAI avec descriptions de paramètres.

    Si la fonction porte un attribut `_mcp_schema` (outils MCP), ce schéma JSON
    fourni par le serveur MCP est utilisé tel quel pour les `parameters`."""
    sig = inspect.signature(func)
    doc = func.__doc__ or ""

    # Cas des outils MCP : schéma d'entrée fourni par le serveur, on le respecte.
    mcp_schema = getattr(func, "_mcp_schema", None)
    if isinstance(mcp_schema, dict) and mcp_schema:
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": doc.strip().split("\n")[0] if doc.strip() else f"Appelle {func.__name__}",
                "parameters": mcp_schema,
            }
        }

    # Extraire les descriptions de paramètres à partir du docstring
    param_descriptions = {}
    lines = doc.split("\n")
    for line in lines:
        line_str = line.strip()
        # Supporter le format "param_name (type): description" ou "param_name: description"
        if ":" in line_str:
            parts = line_str.split(":", 1)
            left = parts[0].strip()
            right = parts[1].strip()
            # Enlever le type éventuel ex: "key (str)" -> "key"
            param_name = left.split("(")[0].strip()
            if param_name in sig.parameters:
                param_descriptions[param_name] = right

    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    for name, param in sig.parameters.items():
        # `context_variables` = état partagé du run, injecté CÔTÉ SERVEUR (façon
        # openai/swarm) → on le MASQUE du modèle (jamais dans le schéma exposé).
        if name == "context_variables":
            continue
        desc = param_descriptions.get(name, f"Paramètre {name}")
        # Type JSON déduit de l'annotation de signature (string par défaut).
        json_type = "string"
        if param.annotation is not inspect.Parameter.empty:
            json_type = _annotation_to_json_type(param.annotation)
        parameters["properties"][name] = {
            "type": json_type,
            "description": desc
        }
        if param.default == inspect.Parameter.empty:
            parameters["required"].append(name)

    # Outil sensible : on expose un paramètre user_confirmed (optionnel) pour le
    # gate human-in-the-loop, même si la fonction ne le déclare pas.
    if approvals.is_sensitive(func) and "user_confirmed" not in parameters["properties"]:
        parameters["properties"]["user_confirmed"] = {
            "type": "boolean",
            "description": "Mettre à True UNIQUEMENT après accord explicite de l'utilisateur (action sensible).",
        }

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": doc.strip().split("\n")[0] if doc.strip() else f"Appelle {func.__name__}",
            "parameters": parameters
        }
    }


def _coerce_value(value, json_type):
    """Coerce une valeur (souvent une string fournie par le modèle) vers le type attendu."""
    if json_type == "integer" and isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return value
    if json_type == "number" and isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    if json_type == "boolean" and isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "oui"):
            return True
        if low in ("false", "0", "no", "non"):
            return False
        return value
    if json_type in ("array", "object") and isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed
        except Exception:
            return value
    return value


def validate_args_schema(func: Callable, args: dict):
    """Valide les arguments contre le schéma JSON de l'outil (outils MCP surtout).
    Renvoie un message d'erreur clair si invalide, sinon None."""
    schema = getattr(func, "_mcp_schema", None)
    if not isinstance(schema, dict) or not schema:
        return None
    try:
        import jsonschema
        jsonschema.validate(args, schema)
        return None
    except ImportError:
        return None
    except Exception as e:
        return f"Arguments invalides pour '{getattr(func, '__name__', '?')}' : {getattr(e, 'message', str(e))}"


def coerce_arguments(func: Callable, args: dict) -> dict:
    """Valide/coerce les arguments d'un tool_call selon le schéma JSON de l'outil.
    Évite les échecs quand le modèle renvoie '5' pour un entier ou 'true' pour un booléen."""
    if not isinstance(args, dict):
        return args
    try:
        props = function_to_schema(func)["function"]["parameters"].get("properties", {})
    except Exception:
        return args
    return {k: _coerce_value(v, props.get(k, {}).get("type")) for k, v in args.items()}

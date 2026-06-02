import yaml
import json
import inspect
import importlib.util
import glob
import os
import time
import threading
import contextvars
import concurrent.futures
from typing import Callable, Tuple, List
from litellm import completion
from .agent import Agent, Result
from . import approvals
from . import run_context
from . import channels
from . import platform_info
import tools.home_assistant
import tools.memory_tools
import tools.code_sandbox
import tools.system_tools
import tools.skills_manager
import tools.web_tools
import tools.media_tools
import tools.agenda_tools
import tools.list_tools
import tools.image_generator
import tools.briefing_tools
import tools.meeting_summarizer
import tools.conversation_tools
import tools.mcp_manager
import tools.notify_tools
import tools.planning_tools
import tools.agent_tools
import tools.tool_script
import tools.browser_tools
import tools.document_tools
import tools.code_edit
import tools.dev_tools
import tools.git_tools
import tools.code_nav

# Map statique des outils disponibles d'origine
AVAILABLE_TOOLS = {
    "get_ha_state": tools.home_assistant.get_ha_state,
    "call_ha_service": tools.home_assistant.call_ha_service,
    "memorize_fact": tools.memory_tools.memorize_fact,
    "store_document": tools.memory_tools.store_document,
    "search_memory": tools.memory_tools.search_memory,
    "execute_python_code": tools.code_sandbox.execute_python_code,
    "execute_bash_command": tools.system_tools.execute_bash_command,
    "save_new_skill": tools.skills_manager.save_new_skill,
    "delete_skill": tools.skills_manager.delete_skill,
    "web_search": tools.web_tools.web_search,
    "web_scrape": tools.web_tools.web_scrape,
    "generate_image": tools.media_tools.generate_image,
    "ingest_file": tools.memory_tools.ingest_file,
    "add_calendar_event": tools.agenda_tools.add_calendar_event,
    "list_calendar_events": tools.agenda_tools.list_calendar_events,
    "delete_calendar_event": tools.agenda_tools.delete_calendar_event,
    "add_list_item": tools.list_tools.add_list_item,
    "get_list_items": tools.list_tools.get_list_items,
    "toggle_list_item": tools.list_tools.toggle_list_item,
    "delete_list_item": tools.list_tools.delete_list_item,
    "generate_artistic_image": tools.image_generator.generate_artistic_image,
    "generate_artistic_video": tools.image_generator.generate_artistic_video,
    "get_daily_briefing": tools.briefing_tools.get_daily_briefing,
    "transcribe_and_summarize_meeting": tools.meeting_summarizer.transcribe_and_summarize_meeting,
    "manage_conversations": tools.conversation_tools.manage_conversations,
    "query_agent": tools.conversation_tools.query_agent,
    "debate_between_agents": tools.conversation_tools.debate_between_agents,
    "send_notification": tools.notify_tools.send_notification,
    "make_plan": tools.planning_tools.make_plan,
    "update_plan_step": tools.planning_tools.update_plan_step,
    "create_agent": tools.agent_tools.create_agent,
    "run_tool_script": tools.tool_script.run_tool_script,
    "render_page": tools.browser_tools.render_page,
    "analyze_document": tools.document_tools.analyze_document,
    "read_file": tools.code_edit.read_file,
    "write_file": tools.code_edit.write_file,
    "edit_file": tools.code_edit.edit_file,
    "apply_patch": tools.code_edit.apply_patch,
    "run_checks": tools.dev_tools.run_checks,
    "git_status": tools.git_tools.git_status,
    "git_diff": tools.git_tools.git_diff,
    "git_log": tools.git_tools.git_log,
    "git_create_branch": tools.git_tools.git_create_branch,
    "git_commit": tools.git_tools.git_commit,
    "search_code": tools.code_nav.search_code,
    "find_definition": tools.code_nav.find_definition,
    "find_references": tools.code_nav.find_references,
    "file_outline": tools.code_nav.file_outline,
}

def load_dynamic_skills() -> dict:
    """Charge dynamiquement tous les scripts Python du dossier skills/ comme des fonctions."""
    skills = {}
    if not os.path.exists("skills"):
        return skills
    for file_path in glob.glob("skills/*.py"):
        file_name = os.path.basename(file_path)
        skill_name = file_name.replace(".py", "")
        try:
            # Importation dynamique
            spec = importlib.util.spec_from_file_location(skill_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Récupère la fonction qui porte le même nom que le fichier
            func = getattr(module, skill_name, None)
            if func:
                skills[skill_name] = func
        except Exception as e:
            print(f"[\033[91mErreur Skill\033[0m] Impossible de charger {file_name} : {e}")
    return skills

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


# --- Garde-fous qualité : cache de résultats d'outils + validation JSON-schema ---
_TOOL_CACHE = {}
_TOOL_CACHE_LOCK = threading.Lock()


def _cacheable_tools() -> set:
    raw = os.getenv("CACHEABLE_TOOLS", "web_search,web_scrape,search_memory")
    return {t.strip() for t in raw.split(",") if t.strip()}


def _tool_cache_ttl() -> int:
    try:
        return int(os.getenv("TOOL_CACHE_TTL", "300") or 0)
    except ValueError:
        return 0


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

class SwarmStepsList(list):
    """Liste personnalisée qui intercepte les ajouts d'étapes pour les diffuser
    en temps réel dans le run courant (isolé par ContextVar, sûr en concurrence)."""
    def append(self, item):
        super().append(item)
        try:
            from core.run_context import publish_step
            publish_step(item)
        except Exception:
            pass

class Swarm:
    def __init__(self, agents_yaml_path="agents.yaml"):
        self.agents = {}
        self.load_agents(agents_yaml_path)
        
    def load_agents(self, path: str):
        # Bootstrap : à la première installation, agents.yaml n'existe pas encore.
        # On démarre alors avec le SEUL orchestrateur (agents.default.yaml) ; l'utilisateur
        # ajoute ses propres agents ensuite (UI ou outil create_agent). agents.example.yaml
        # contient une équipe complète d'exemple à charger si on veut.
        if not os.path.exists(path):
            import shutil
            default = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agents.default.yaml")
            if os.path.exists(default):
                shutil.copy(default, path)
                print(f"[Essaim] Première exécution : {path} initialisé avec l'orchestrateur seul (agents.default.yaml).")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Reset : repartir d'une table vierge pour que les agents SUPPRIMÉS de
        # agents.yaml disparaissent réellement lors d'un hot-reload (sinon ils
        # survivaient en mémoire jusqu'au redémarrage du serveur).
        self.agents = {}

        # Première passe : créer les agents sans les fonctions de transfert (handoffs)
        for agent_data in data.get("agents", []):
            agent = Agent(
                name=agent_data["name"],
                system_prompt=agent_data["system_prompt"],
                model=agent_data.get("model", "gpt-4o"),
                supports_tools=agent_data.get("supports_tools", True),
                display_name=agent_data.get("display_name"),
                welcome_message=agent_data.get("welcome_message")
            )
            # Ajouter les outils standards
            for tool_name in agent_data.get("tools", []):
                if tool_name in AVAILABLE_TOOLS:
                    agent.tools.append(AVAILABLE_TOOLS[tool_name])
            
            self.agents[agent.name] = agent

        # Détermination de l'ORCHESTRATEUR (renommable) : agent marqué
        # `orchestrator: true`, sinon "Jarvis" s'il existe (compat.), sinon le 1er agent.
        self.orchestrator_name = None
        for agent_data in data.get("agents", []):
            if agent_data.get("orchestrator") is True:
                self.orchestrator_name = agent_data["name"]
                break
        if not self.orchestrator_name:
            if "Jarvis" in self.agents:
                self.orchestrator_name = "Jarvis"
            elif self.agents:
                self.orchestrator_name = next(iter(self.agents))
        orch = self.orchestrator_name

        # Seconde passe : injecter les fonctions de transfert dynamiquement
        for agent_data in data.get("agents", []):
            agent = self.agents[agent_data["name"]]

            # L'orchestrateur a automatiquement des transferts vers TOUS les autres agents !
            targets = list(agent_data.get("handoffs", []))
            if agent.name == orch:
                targets = [name for name in self.agents.keys() if name != orch]
            else:
                if orch and orch not in targets and orch in self.agents:
                    targets.append(orch)
                
            for target_name in targets:
                if target_name in self.agents:
                    target_agent = self.agents[target_name]
                    # Éviter les doublons
                    if not any(f.__name__ == f"transfer_to_{target_agent.name}" for f in agent.tools):
                        handoff_func = self.create_handoff_function(target_agent)
                        agent.tools.append(handoff_func)

    def create_handoff_function(self, target_agent: Agent) -> Callable:
        """Génère une fonction Python dynamiquement pour transférer la conversation."""
        def handoff() -> Result:
            return Result(value=f"Transféré avec succès à {target_agent.name}", agent=target_agent)
        
        # On renomme la fonction pour que le LLM comprenne son but
        handoff.__name__ = f"transfer_to_{target_agent.name}"
        handoff.__doc__ = f"Appelle cette fonction pour transférer la demande à l'agent {target_agent.name} si elle relève de ses compétences."
        return handoff

    def _maybe_continue(self, model: str, base_messages: list, response):
        """Auto-continuation : si la réponse est tronquée (finish_reason='length',
        sans tool_calls), redemande la suite et recolle, jusqu'à
        LLM_MAX_CONTINUATIONS fois. Évite les réponses coupées."""
        max_cont = int(os.getenv("LLM_MAX_CONTINUATIONS", "3") or 0)
        if max_cont <= 0:
            return response
        try:
            choice = response.choices[0]
            msg = choice.message
        except Exception:
            return response
        full = getattr(msg, "content", "") or ""
        cont = 0
        while (cont < max_cont and getattr(choice, "finish_reason", None) == "length"
               and not getattr(msg, "tool_calls", None) and full):
            cont += 1
            follow = list(base_messages) + [
                {"role": "assistant", "content": full},
                {"role": "user", "content": "Continue ta réponse EXACTEMENT là où elle s'est arrêtée (elle a été tronquée). Ne répète rien, n'ajoute aucune introduction."},
            ]
            try:
                nxt = self._complete(model, follow, tools_schema=None, allow_continuation=False)
                nchoice = nxt.choices[0]
                nmsg = nchoice.message
            except Exception:
                break
            piece = getattr(nmsg, "content", "") or ""
            if not piece:
                break
            full += piece
            choice, msg = nchoice, nmsg
            print(f"[\033[96mCONTINUATION\033[0m] réponse tronquée prolongée ({cont}/{max_cont}).")
        try:
            response.choices[0].message.content = full
            response.choices[0].finish_reason = "stop"
        except Exception:
            pass
        return response

    def _complete_streaming(self, completion_kwargs, on_delta):
        """Appel LLM en streaming : diffuse les tokens via on_delta et reconstruit
        un objet réponse compatible avec la boucle (content + tool_calls)."""
        completion_kwargs["stream"] = True
        content_parts = []
        tool_acc = {}   # index -> {id, name, arguments}
        finish_reason = None

        stream_obj = completion(**completion_kwargs)
        # Compat : si l'objet renvoyé est déjà une réponse complète (provider sans
        # streaming, ou tests), on émet le contenu d'un bloc et on le renvoie tel quel.
        _choices = getattr(stream_obj, "choices", None)
        if _choices and getattr(_choices[0], "message", None) is not None:
            msg = _choices[0].message
            if getattr(msg, "content", None):
                try:
                    on_delta(msg.content)
                except Exception:
                    pass
            return stream_obj

        for chunk in stream_obj:
            try:
                choice = chunk.choices[0]
            except (AttributeError, IndexError):
                continue
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                content_parts.append(piece)
                try:
                    on_delta(piece)
                except Exception:
                    pass
            for tc in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc, "index", 0) or 0
                acc = tool_acc.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    acc["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn:
                    if getattr(fn, "name", None):
                        acc["name"] += fn.name
                    if getattr(fn, "arguments", None):
                        acc["arguments"] += fn.arguments

        full = "".join(content_parts)

        class _F:
            def __init__(self, name, args):
                self.name = name
                self.arguments = args

        class _TC:
            def __init__(self, tid, name, args):
                self.id = tid or f"call_{__import__('uuid').uuid4().hex[:8]}"
                self.type = "function"
                self.function = _F(name, args)

        tool_calls = [_TC(a["id"], a["name"], a["arguments"]) for _i, a in sorted(tool_acc.items()) if a["name"]] or None

        class _Msg:
            def __init__(self):
                self.content = full
                self.tool_calls = tool_calls
            def model_dump(self, exclude_none=True):
                d = {"role": "assistant"}
                if full:
                    d["content"] = full
                if tool_calls:
                    d["tool_calls"] = [{"id": t.id, "type": "function",
                                        "function": {"name": t.function.name, "arguments": t.function.arguments}}
                                       for t in tool_calls]
                return d

        class _Usage:
            prompt_tokens = 0
            completion_tokens = 0

        class _Choice:
            def __init__(self):
                self.message = _Msg()
                self.finish_reason = finish_reason or "stop"

        class _Resp:
            def __init__(self):
                self.choices = [_Choice()]
                self.usage = _Usage()

        return _Resp()

    def _apply_prompt_cache(self, messages: list, model: str) -> list:
        """Prompt caching : marque le gros message système comme point de cache pour
        les modèles Anthropic (préfixe stable réutilisé → latence et coût réduits).
        PROMPT_CACHE = auto (défaut, Anthropic seulement) | on (forcé) | off.
        N'est JAMAIS appliqué sur l'endpoint custom (qwen3 = prefix caching serveur)."""
        mode = os.getenv("PROMPT_CACHE", "auto").lower()
        if mode == "off":
            return messages
        is_anthropic = "claude" in (model or "").lower() or "anthropic" in (model or "").lower()
        if mode != "on" and not is_anthropic:
            return messages
        out, cached = [], False
        for m in messages:
            if (not cached and m.get("role") == "system"
                    and isinstance(m.get("content"), str) and len(m["content"]) > 1000):
                out.append({"role": "system", "content": [
                    {"type": "text", "text": m["content"], "cache_control": {"type": "ephemeral"}}
                ]})
                cached = True
            else:
                out.append(m)
        return out

    def _route_target(self, agent: Agent, messages: list):
        """Mini-routeur : à QUEL spécialiste confier la demande ? L'orchestrateur connaît
        ainsi la spécialité de chaque agent (extraite de leur prompt) et route tout seul,
        sans que l'utilisateur ait à nommer l'agent. Indépendant de la langue et des agents.
        Renvoie : le NOM d'un agent (déléguer à lui) ; "" (aucun → l'orchestrateur répond
        lui-même) ; None (routeur désactivé/indisponible → ne rien restreindre)."""
        if os.getenv("DELEGATION_ROUTER", "true").lower() not in ("true", "1", "yes"):
            return None
        orch = getattr(self, "orchestrator_name", "Jarvis")
        specialists = []
        for name, a in self.agents.items():
            if name == orch:
                continue
            desc = ""
            if a.system_prompt:
                sents = [s.strip() for s in a.system_prompt.replace("\n", " ").split(".") if s.strip()]
                desc = ". ".join(sents[:1])
            specialists.append(f"- {name} : {desc}")
        if not specialists:
            return ""
        last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        if not str(last_user).strip():
            return ""
        names = [n for n in self.agents if n != orch]
        try:
            model = os.getenv("FAST_MODEL", "").strip() or agent.model
            sys_p = (
                "Tu es un AIGUILLEUR. Voici les agents spécialisés disponibles :\n" + "\n".join(specialists) +
                "\n\nQuestion : la demande de l'utilisateur est-elle une TÂCHE À CONFIER à l'un de ces "
                "spécialistes ? Réponds par le NOM EXACT de l'agent, ou « AUCUN ».\n"
                "Réponds AUCUN pour : une présentation/identité (« qui es-tu »), une salutation, une "
                "question générale, l'heure/la date, du bavardage, ou tout ce qui ne correspond pas "
                "précisément au métier d'un agent ci-dessus.\n"
                "Exemples : « qui es-tu ? » → AUCUN | « bonjour » → AUCUN | « quelle heure est-il ? » → "
                "AUCUN | « raconte une blague » → AUCUN | une demande relevant clairement d'un des "
                "métiers listés → le nom de cet agent.\n"
                "Ne réponds QUE par un nom de la liste ou AUCUN, rien d'autre."
            )
            resp = self._complete(model, [
                {"role": "system", "content": sys_p},
                {"role": "user", "content": str(last_user)[:1500]},
            ], tools_schema=None, allow_continuation=False, allow_fallback=False)
            ans = (resp.choices[0].message.content or "").strip()
            # Parsing STRICT, biaisé vers « ne pas déléguer » : on délègue uniquement si la
            # réponse correspond exactement (token) à un nom d'agent. Toute ambiguïté → False.
            import re as _re
            token = _re.sub(r"[^a-z0-9_]", "", (ans.split() or [""])[0].lower())
            if token == "aucun" or not token:
                return ""
            for n in names:
                if token == n.lower():
                    return n
            return ""  # réponse non reconnue → biais « ne pas déléguer »
        except Exception as e:
            print(f"[Routeur délégation] indisponible ({e}) — délégation laissée au modèle.")
            return None

    def _route_model(self, default_model: str, messages: list) -> str:
        """Routage par difficulté : pour une requête manifestement triviale, utilise
        un modèle rapide (FAST_MODEL) ; sinon garde le modèle fort. Désactivé tant que
        FAST_MODEL n'est pas défini. Heuristique CONSERVATRICE (en cas de doute → fort)."""
        fast = os.getenv("FAST_MODEL", "").strip()
        if not fast:
            return default_model
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return default_model
        text = str(user_msgs[-1].get("content", "") or "").lower()
        hard_kw = ("```", "code", "python", "script", "debug", "débug", "erreur",
                   "analyse", "compare", "explique", "traduis", "rédige", "écris",
                   "calcule", "pourquoi", "démontre", "résous", "résume", "corrige")
        is_hard = len(text) > 280 or any(k in text for k in hard_kw)
        return default_model if is_hard else fast

    def _complete(self, model: str, messages: list, tools_schema=None, allow_continuation: bool = True, on_delta=None, allow_fallback: bool = True):
        """Appel LLM via litellm avec routage clé officielle / endpoint custom.
        Si on_delta est fourni et STREAM_TOKENS actif, diffuse les tokens au fil
        de l'eau (latence minimale) et reconstruit une réponse compatible.
        En cas d'échec du modèle (après retries), bascule sur FALLBACK_MODELS."""
        completion_kwargs = {"model": model, "messages": messages, "tools": tools_schema}
        custom_base = os.environ.get("CUSTOM_LLM_API_BASE", "").strip()
        custom_key = os.environ.get("CUSTOM_LLM_API_KEY", "").strip()
        model_l = (model or "").lower()
        is_standard = any(p in model_l for p in ["gpt-", "claude-", "gemini-", "groq/", "openrouter/", "ollama/", "mistral/"])
        has_official_key = False
        if "gpt-" in model_l:
            has_official_key = bool(os.environ.get("OPENAI_API_KEY"))
        elif "claude-" in model_l:
            has_official_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif "gemini-" in model_l:
            has_official_key = bool(os.environ.get("GEMINI_API_KEY"))

        use_custom = custom_base and (
            not is_standard or not has_official_key
            or model.startswith("custom_openai/") or model.startswith("openai/")
        )
        if use_custom:
            # Auto-correction pour Open WebUI (/v1 -> /api/v1)
            if "/v1" in custom_base and "/api" not in custom_base:
                custom_base = custom_base.replace("/v1", "/api/v1")
            completion_kwargs["api_base"] = custom_base
            completion_kwargs["api_key"] = custom_key or "placeholder-key"
            local_model = model or "qwen3"
            completion_kwargs["model"] = local_model if "/" in local_model else f"openai/{local_model}"
        else:
            # Prompt caching (Anthropic) hors endpoint custom uniquement — sûr pour qwen3.
            completion_kwargs["messages"] = self._apply_prompt_cache(messages, model)

        stream = on_delta is not None and os.getenv("STREAM_TOKENS", "true").lower() in ("true", "1", "yes")

        # Garde-fou : retries avec backoff exponentiel sur erreur LLM transitoire.
        retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        last_err = None
        for attempt in range(retries + 1):
            try:
                if stream:
                    return self._complete_streaming(dict(completion_kwargs), on_delta)
                response = completion(**completion_kwargs)
                # Recolle automatiquement les réponses tronquées (finish_reason=length).
                if allow_continuation:
                    response = self._maybe_continue(model, messages, response)
                return response
            except Exception as e:
                last_err = e
                if attempt < retries:
                    wait = min(2 ** attempt, 8)
                    print(f"[\033[93mLLM retry\033[0m] tentative {attempt + 1}/{retries} échouée ({e}); nouvelle tentative dans {wait}s")
                    time.sleep(wait)

        # Failover : le modèle principal a échoué → on tente les modèles de secours.
        if allow_fallback:
            fallbacks = [m.strip() for m in os.getenv("FALLBACK_MODELS", "").split(",")
                         if m.strip() and m.strip() != model]
            for fb in fallbacks:
                try:
                    print(f"[\033[96mLLM failover\033[0m] '{model}' indisponible → bascule sur '{fb}'.")
                    return self._complete(fb, messages, tools_schema, allow_continuation,
                                          on_delta, allow_fallback=False)
                except Exception as e:
                    last_err = e
        raise last_err

    def _maybe_compact(self, model: str, history: list, steps: list) -> list:
        """Compacte un historique trop long : résume les anciens messages en un
        seul, garde les plus récents verbatim. N'agit que sur la vue LLM.
        Activé par MEMORY_MAX_MESSAGES (0 = désactivé). Résultats mis en cache
        pour ne pas re-résumer le même bloc à chaque tour."""
        max_msgs = int(os.getenv("MEMORY_MAX_MESSAGES", "40") or 0)
        if not max_msgs or len(history) <= max_msgs:
            return history
        keep = max(1, int(os.getenv("MEMORY_KEEP_RECENT", "12")))
        head, tail = history[:-keep], history[-keep:]
        if not head:
            return history

        cache = getattr(self, "_summary_cache", None)
        if cache is None:
            cache = self._summary_cache = {}

        try:
            key = json.dumps(head, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            key = str(len(head))

        summary = cache.get(key)
        if summary is None:
            transcript = "\n".join(
                f"{m.get('role')}: {m.get('content', '')}" for m in head if m.get("content")
            )[:8000]
            try:
                resp = self._complete(model, [
                    {"role": "system", "content": (
                        "Résume la conversation suivante en 10 lignes maximum, en français, "
                        "en conservant les faits, décisions, préférences utilisateur et le "
                        "contexte utiles à la poursuite. Style condensé, pas de bavardage."
                    )},
                    {"role": "user", "content": transcript},
                ])
                summary = (resp.choices[0].message.content or "").strip()
            except Exception as e:
                print(f"[\033[91mCompaction mémoire erreur\033[0m] {e}")
                return history  # en cas d'échec, on garde l'historique complet
            cache[key] = summary
            if len(cache) > 64:
                cache.pop(next(iter(cache)))
            steps.append({"type": "memory_compaction", "summarized": len(head), "kept": len(tail)})
            print(f"[\033[96mMÉMOIRE\033[0m] Historique compacté : {len(head)} messages résumés, {len(tail)} conservés.")

        summary_msg = {
            "role": "user",
            "content": f"[RÉSUMÉ DE LA CONVERSATION PRÉCÉDENTE — {len(head)} messages condensés]\n{summary}",
        }
        return [summary_msg] + tail

    def _write_experience_report(self, agent: Agent, messages: list, steps: list):
        """Hook post-tâche (auto-amélioration) : génère un court compte-rendu
        structuré (ce qui a marché / échoué / à retenir) et l'archive en mémoire
        sémantique, où il resurgira via le RAG lors d'une tâche similaire."""
        if os.getenv("SELF_IMPROVE", "true").lower() not in ("true", "1", "yes"):
            return
        # On ne produit un retour que pour les tâches non triviales (avec outils/handoffs).
        if not any(s.get("type") in ("tool_call", "handoff") for s in steps):
            return
        try:
            # Reconstruit un transcript compact du dernier échange.
            lines = []
            for m in messages[-12:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"{m.get('name','assistant')}: {m.get('content','')}")
                elif role == "tool":
                    lines.append(f"OUTIL[{m.get('name','?')}]: {str(m.get('content',''))[:400]}")
            transcript = "\n".join(lines)[:6000]

            report_messages = [
                {"role": "system", "content": (
                    "Tu es un module d'auto-amélioration. À partir de l'échange ci-dessous, rédige un "
                    "COMPTE-RENDU TRÈS COURT (5 lignes max) et factuel, en français, au format :\n"
                    "- Tâche: <résumé en une ligne>\n- A marché: <...>\n- A échoué/limites: <...>\n"
                    "- À retenir pour la prochaine fois: <conseil actionnable>\n"
                    "Si rien d'utile n'est à retenir, réponds exactement: RAS."
                )},
                {"role": "user", "content": transcript},
            ]
            resp = self._complete(agent.model, report_messages, tools_schema=None)
            report = (resp.choices[0].message.content or "").strip()
            if not report or report.upper().startswith("RAS"):
                return
            import tools.memory_tools
            tools.memory_tools.store_document(report, source="retour_experience")
            # Consolidation : borne le nombre de retours d'expérience (anti-bloat RAG).
            try:
                keep = int(os.getenv("EXPERIENCE_MAX", "50") or 50)
                pruned = tools.memory_tools.semantic_mem.prune_source("retour_experience", keep)
                if pruned:
                    print(f"[AUTO-AMÉLIORATION] {pruned} ancien(s) retour(s) élagué(s) (cap {keep}).")
            except Exception:
                pass
            steps.append({"type": "self_improve", "agent": agent.name, "content": report})
            print(f"[\033[96mAUTO-AMÉLIORATION\033[0m] Retour d'expérience archivé.")
        except Exception as e:
            print(f"[\033[91mAuto-amélioration erreur\033[0m] {e}")

    def _update_user_profile(self, agent: Agent, messages: list, steps: list):
        """Met à jour le profil utilisateur évolutif à partir du dernier échange
        (personnalisation durable, façon Hermes/Honcho). Gate USER_MODELING."""
        if os.getenv("USER_MODELING", "true").lower() not in ("true", "1", "yes"):
            return
        try:
            from .user_profile import user_profile
            lines = []
            for m in messages[-10:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"ASSISTANT: {m.get('content','')}")
            transcript = "\n".join(lines)[:5000]
            # On ne profile pas les échanges triviaux (évite un appel LLM inutile).
            last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
            if not transcript.strip() or len(str(last_user)) < 60:
                return
            if user_profile.update_from_exchange(transcript, self._complete, agent.model):
                steps.append({"type": "profile_updated", "agent": agent.name})
                print(f"[\033[96mPROFIL\033[0m] Profil utilisateur mis à jour.")
        except Exception as e:
            print(f"[\033[91mProfil utilisateur erreur\033[0m] {e}")

    def _improve_skills(self, agent: Agent, failures: list, steps: list):
        """Amélioration des compétences PENDANT l'usage : si une compétence dynamique a
        échoué, on tente de la RÉPARER automatiquement (LLM) puis on revalide la sûreté.
        N'agit que sur les compétences PURES (les skills complexes de l'utilisateur ne
        sont jamais réécrites automatiquement). Gate SELF_IMPROVE_SKILLS."""
        if os.getenv("SELF_IMPROVE_SKILLS", "true").lower() not in ("true", "1", "yes"):
            return
        if not failures:
            return
        import tools.skills_manager as sm
        seen = set()
        for f in failures:
            name = f.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            path = os.path.join("skills", f"{name}.py")
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    current = fh.read()
                # On ne répare automatiquement que les compétences pures (sûres).
                ok, _ = sm.validate_pure_skill(current, name)
                if not ok:
                    continue
                fixed = (self._complete(agent.model, [
                    {"role": "system", "content": (
                        "Tu es un module de RÉPARATION DE COMPÉTENCE. Corrige la fonction Python "
                        "ci-dessous qui a levé une erreur. Garde EXACTEMENT le même nom et la même "
                        "vocation, reste une fonction PURE (aucune I/O, imports sûrs uniquement). "
                        "Réponds STRICTEMENT par le code Python complet de la fonction corrigée, sans "
                        "texte ni balises markdown.")},
                    {"role": "user", "content": (
                        f"FONCTION ({name}) :\n{current}\n\nERREUR : {f.get('error')}\n"
                        f"ARGS AYANT ÉCHOUÉ : {f.get('args')}")},
                ], tools_schema=None).choices[0].message.content or "").strip()
                # Nettoyage d'éventuelles balises ```python.
                if fixed.startswith("```"):
                    fixed = fixed.strip("`")
                    fixed = fixed[len("python"):].strip() if fixed.lower().startswith("python") else fixed.strip()
                if not fixed or fixed.strip() == current.strip():
                    continue
                ok2, reason = sm.validate_pure_skill(fixed, name)
                if not ok2:
                    print(f"[\033[93mRÉPARATION refusée\033[0m] '{name}' : {reason}")
                    continue
                sm.save_new_skill(name, fixed, f"(réparée auto) {name}")
                steps.append({"type": "skill_improved", "agent": agent.name, "name": name})
                print(f"[\033[96mAUTO-COMPÉTENCE\033[0m] Compétence '{name}' réparée automatiquement.")
            except Exception as e:
                print(f"[\033[91mRéparation skill erreur\033[0m] {e}")

    def _auto_critic(self, agent: Agent, messages: list, steps: list):
        """Passe critique avant livraison (qualité) : un relecteur vérifie la réponse
        finale ; si un problème concret est trouvé, l'agent en produit UNE version
        corrigée. Désactivé par défaut (AUTO_CRITIC=true pour activer ; coût = 1-2
        appels LLM supplémentaires en fin de tâche)."""
        if os.getenv("AUTO_CRITIC", "false").lower() not in ("true", "1", "yes"):
            return
        final = next((m for m in reversed(messages)
                      if m.get("role") == "assistant" and m.get("content")), None)
        if not final or len(str(final.get("content", ""))) < 40:
            return
        user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        if not user:
            return
        try:
            verdict = (self._complete(agent.model, [
                {"role": "system", "content": (
                    "Tu es un relecteur critique. Vérifie si la RÉPONSE traite correctement et "
                    "complètement la DEMANDE, sans erreur factuelle, incohérence ni partie manquante. "
                    "Réponds STRICTEMENT 'OK' si elle est correcte et complète. Sinon, liste en 1 à 3 "
                    "puces les problèmes concrets.")},
                {"role": "user", "content": f"DEMANDE:\n{user}\n\nRÉPONSE:\n{final.get('content','')}"},
            ], tools_schema=None).choices[0].message.content or "").strip()
            if not verdict or verdict.upper().startswith("OK"):
                return
            revised = (self._complete(agent.model, [
                {"role": "system", "content": (
                    "Corrige et complète ta réponse précédente en tenant compte des remarques du "
                    "relecteur. Renvoie UNIQUEMENT la réponse corrigée, complète et autoportante.")},
                {"role": "user", "content": f"DEMANDE:\n{user}\n\nTA RÉPONSE:\n{final.get('content','')}\n\nREMARQUES:\n{verdict}"},
            ], tools_schema=None).choices[0].message.content or "").strip()
            if not revised or revised.strip() == str(final.get("content", "")).strip():
                return
            messages.append({"role": "assistant", "name": agent.name, "content": revised})
            steps.append({"type": "critic", "agent": agent.name, "issues": verdict})
            steps.append({"type": "message", "agent": agent.name, "content": revised})
            print(f"[\033[96mAUTO-CRITIQUE\033[0m] Réponse révisée après vérification.")
        except Exception as e:
            print(f"[\033[91mAuto-critique erreur\033[0m] {e}")

    def _induce_skill(self, agent: Agent, messages: list, steps: list):
        """Acquisition de compétences (façon Voyager) : si une FONCTION PYTHON PURE et
        réutilisable aurait aidé sur cette tâche, on la fait générer puis on l'enregistre
        comme skill permanente (après validation de sûreté). Désactivable via
        SELF_IMPROVE_SKILLS=false."""
        if os.getenv("SELF_IMPROVE", "true").lower() not in ("true", "1", "yes"):
            return
        if os.getenv("SELF_IMPROVE_SKILLS", "true").lower() not in ("true", "1", "yes"):
            return
        # Seulement pour des tâches non triviales (outils/handoffs).
        if not any(s.get("type") in ("tool_call", "handoff") for s in steps):
            return
        try:
            import json as _json
            import re as _re
            import tools.skills_manager as sm
            existing = set(load_dynamic_skills().keys()) | set(AVAILABLE_TOOLS.keys())

            lines = []
            for m in messages[-12:]:
                role = m.get("role")
                if role == "user":
                    lines.append(f"UTILISATEUR: {m.get('content','')}")
                elif role == "assistant" and m.get("content"):
                    lines.append(f"{m.get('name','assistant')}: {m.get('content','')}")
                elif role == "tool":
                    lines.append(f"OUTIL[{m.get('name','?')}]: {str(m.get('content',''))[:300]}")
            transcript = "\n".join(lines)[:6000]

            sys_prompt = (
                "Tu es un module d'ACQUISITION DE COMPÉTENCES. À partir de l'échange, juge si une "
                "FONCTION PYTHON PURE, générique et RÉUTILISABLE aurait évité du travail manuel et "
                "servirait à de futures tâches similaires (ex: calcul, formatage, conversion, parsing).\n"
                "CONTRAINTES STRICTES : fonction pure (déterministe), AUCUNE entrée/sortie, AUCUN accès "
                "réseau/fichier/système ; imports autorisés uniquement parmi math, datetime, json, re, "
                "statistics, itertools, collections, functools, typing, decimal, random, string, "
                "fractions, calendar. Le code doit définir 'def <nom>(...)' avec une docstring.\n"
                "Réponds STRICTEMENT en JSON : "
                '{"skill": true, "name": "<snake_case>", "description": "<courte>", "code": "<python>"} '
                'OU {"skill": false} si aucune compétence générique pertinente. '
                "Ne crée PAS de compétence trop spécifique ou triviale."
            )
            resp = self._complete(agent.model, [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": transcript},
            ], tools_schema=None)
            content = (resp.choices[0].message.content or "").strip()
            # Extraction robuste du JSON.
            start, end = content.find("{"), content.rfind("}")
            if start < 0 or end <= start:
                return
            data = _json.loads(content[start:end + 1])
            if not data.get("skill"):
                return
            name = (data.get("name") or "").strip()
            code = data.get("code") or ""
            desc = (data.get("description") or "").strip() or name
            if not _re.match(r"^[a-z0-9_]+$", name):
                return
            if name in existing:
                print(f"[AUTO-COMPÉTENCE] '{name}' existe déjà — ignorée.")
                return
            ok, reason = sm.validate_pure_skill(code, name)
            if not ok:
                print(f"[\033[93mAUTO-COMPÉTENCE refusée\033[0m] '{name}' : {reason}")
                return
            result = sm.save_new_skill(name, code, desc)
            if result.startswith("Succès"):
                steps.append({"type": "skill_learned", "agent": agent.name,
                              "name": name, "description": desc})
                print(f"[\033[96mAUTO-COMPÉTENCE\033[0m] Nouvelle compétence acquise : '{name}'.")
        except Exception as e:
            print(f"[\033[91mAuto-compétence erreur\033[0m] {e}")

    def run(self, starting_agent: Agent, messages: list, max_turns: int = 10,
            max_seconds: float = None, max_tokens: int = None) -> Tuple[Agent, list, list]:
        """
        Boucle principale de l'orchestrateur.
        Retourne l'agent final actif, les messages mis à jour, et l'historique des étapes (steps).

        max_turns   : nombre maximum d'itérations (appels LLM) avant arrêt forcé.
        max_seconds : budget temps mur (défaut env SWARM_MAX_SECONDS, 0 = illimité).
        max_tokens  : budget tokens cumulés (défaut env SWARM_MAX_TOKENS, 0 = illimité).
        """
        if max_seconds is None:
            max_seconds = float(os.getenv("SWARM_MAX_SECONDS", "0") or 0)
        if max_tokens is None:
            max_tokens = int(os.getenv("SWARM_MAX_TOKENS", "0") or 0)

        original_messages_len = len(messages)
        current_agent = starting_agent
        steps = SwarmStepsList()
        turn = 0
        started_at = time.time()
        tokens_used = 0
        skill_failures = []  # échecs de compétences dynamiques → réparées en fin de run
        _route_done = False   # routeur de délégation : décidé une seule fois par run
        _route_target = None  # spécialiste ciblé (nom) | "" (aucun) | None (non décidé)

        while True:
            # Annulation (barge-in vocal / bouton stop) : vérifiée à chaque tour.
            if run_context.is_cancelled_current():
                cancel_msg = "🛑 Run annulé par l'utilisateur."
                print(f"[\033[91mSWARM\033[0m] {cancel_msg}")
                steps.append({"type": "message", "agent": current_agent.name, "content": cancel_msg})
                messages.append({"role": "assistant", "name": current_agent.name, "content": cancel_msg})
                break
            # Garde-fou : budget temps mur (latence vocale / runaway).
            if max_seconds and (time.time() - started_at) > max_seconds:
                budget_msg = (
                    f"⏱️ Budget temps atteint ({max_seconds:.0f}s). Arrêt de l'essaim ; "
                    "la tâche est peut-être incomplète."
                )
                print(f"[\033[91mSWARM\033[0m] {budget_msg}")
                steps.append({"type": "message", "agent": current_agent.name, "content": budget_msg})
                messages.append({"role": "assistant", "name": current_agent.name, "content": budget_msg})
                break
            # Garde-fou : budget tokens cumulés.
            if max_tokens and tokens_used > max_tokens:
                budget_msg = (
                    f"🪙 Budget tokens atteint ({tokens_used}/{max_tokens}). Arrêt de l'essaim ; "
                    "la tâche est peut-être incomplète."
                )
                print(f"[\033[91mSWARM\033[0m] {budget_msg}")
                steps.append({"type": "message", "agent": current_agent.name, "content": budget_msg})
                messages.append({"role": "assistant", "name": current_agent.name, "content": budget_msg})
                break
            # Garde-fou anti-boucle infinie : on borne le nombre de tours.
            if turn >= max_turns:
                limit_msg = (
                    f"⚠️ Limite d'orchestration atteinte ({max_turns} tours). "
                    "Arrêt de l'essaim pour éviter une boucle infinie ; la tâche est "
                    "peut-être incomplète. Reformulez ou augmentez max_turns si nécessaire."
                )
                print(f"[\033[91mSWARM\033[0m] {limit_msg}")
                steps.append({
                    "type": "message",
                    "agent": current_agent.name,
                    "content": limit_msg
                })
                messages.append({
                    "role": "assistant",
                    "name": current_agent.name,
                    "content": limit_msg
                })
                break
            turn += 1
            # 1. Outils effectifs du tour, calculés LOCALEMENT (on ne mute pas
            #    l'objet Agent partagé : indispensable pour la concurrence).
            effective_tools = list(current_agent.tools)
            if current_agent.name in (getattr(self, "orchestrator_name", "Jarvis"), "Codeur"):
                existing = {f.__name__ for f in effective_tools}
                # Compétences dynamiques (auto-amélioration) rechargées à chaque tour.
                for skill_name, func in load_dynamic_skills().items():
                    if skill_name not in existing:
                        effective_tools.append(func)
                        existing.add(skill_name)
                # Outils MCP (serveurs externes) injectés comme des outils natifs.
                for tool_name, func in tools.mcp_manager.mcp_manager.tool_functions().items():
                    if tool_name not in existing:
                        effective_tools.append(func)
                        existing.add(tool_name)

            # Permissions par canal : on retire les outils interdits pour ce canal.
            chan = channels.current_channel.get()
            if chan:
                effective_tools = [f for f in effective_tools if channels.tool_allowed(chan, f.__name__)]

            # Garde-fou anti sur-délégation : pour une question triviale/générale adressée
            # à l'orchestrateur, on RETIRE les outils de délégation pour ce tour → il répond
            # lui-même (qwen3 a tendance à transférer à tort sinon).
            # Routeur de délégation (indépendant de la langue ET des agents) : un mini-appel
            # LLM décide UNE fois par run si la demande relève d'un spécialiste présent. Sinon,
            # on retire les outils de délégation → l'orchestrateur répond lui-même (qwen3 a
            # tendance à sur-déléguer). Le LLM comprend toutes les langues et utilise la liste
            # DYNAMIQUE des agents, donc tout nouvel agent est pris en compte automatiquement.
            if current_agent.name == getattr(self, "orchestrator_name", "Jarvis") and len(self.agents) > 1:
                if not _route_done:
                    _route_done = True
                    _route_target = self._route_target(current_agent, messages)
                if _route_target == "":
                    # Aucun spécialiste pertinent → l'orchestrateur répond lui-même : on retire
                    # les outils de délégation (il garde ses propres outils).
                    effective_tools = [f for f in effective_tools
                                       if not f.__name__.startswith("transfer_to_")
                                       and f.__name__ not in ("query_agent", "debate_between_agents")]
                elif _route_target:
                    # Un spécialiste correspond → on FORCE la délégation : on retire à
                    # l'orchestrateur les outils-MÉTIER de ce spécialiste (il ne peut plus
                    # faire son travail lui-même), en gardant ses outils d'orchestration.
                    tgt = self.agents.get(_route_target)
                    if tgt:
                        tgt_tools = {f.__name__ for f in tgt.tools}
                        _orch_keep = {"query_agent", "debate_between_agents", "memorize_fact",
                                      "store_document", "search_memory", "send_notification",
                                      "make_plan", "update_plan_step", "create_agent", "run_tool_script"}
                        effective_tools = [f for f in effective_tools
                                           if f.__name__.startswith("transfer_to_")
                                           or f.__name__ not in tgt_tools
                                           or f.__name__ in _orch_keep]

            # Enregistrer l'activation de l'agent
            steps.append({
                "type": "activation",
                "agent": current_agent.name
            })

            tools_schema = [function_to_schema(f) for f in effective_tools] if (effective_tools and current_agent.supports_tools) else None
            
            # Injection dynamique des informations mémorisées (Core Memory) dans Jarvis
            system_prompt = current_agent.system_prompt
            # Ne forcer la présentation que si aucun message de cet agent n'est déjà présent dans l'historique
            has_agent_spoken = any(msg.get("role") == "assistant" and msg.get("name") == current_agent.name for msg in messages)
            if getattr(current_agent, "welcome_message", None) and not has_agent_spoken and current_agent.name != getattr(self, "orchestrator_name", "Jarvis"):
                system_prompt += f"\n\n⚠️ INSTRUCTION DE PRÉSENTATION OBLIGATOIRE :\n"
                system_prompt += f"Tu DOIS commencer ta toute première réponse par la phrase d'introduction suivante exactement : \"{current_agent.welcome_message}\". Ne change pas un seul mot de cette phrase de présentation, commence directement par elle, puis poursuis naturellement pour répondre à l'utilisateur.\n"
                
            if current_agent.name == getattr(self, "orchestrator_name", "Jarvis"):
                # Date/heure courantes (l'orchestrateur peut répondre « quelle heure ? »).
                try:
                    import datetime as _dt
                    system_prompt += f"\nContexte : nous sommes le {_dt.datetime.now().strftime('%A %d %B %Y, %H:%M')} (heure du serveur).\n"
                except Exception:
                    pass
                system_prompt += tools.memory_tools.core_mem.get_as_prompt()
                # Profil utilisateur évolutif (personnalisation durable).
                try:
                    from .user_profile import user_profile
                    system_prompt += user_profile.as_prompt()
                except Exception:
                    pass
                # Indice de routage : un spécialiste a été identifié pour cette demande.
                if _route_target:
                    system_prompt += (
                        f"\n➡️ AIGUILLAGE : cette demande relève du métier de « {_route_target} ». "
                        f"Délègue-lui MAINTENANT (transfer_to_{_route_target} ou query_agent('{_route_target}', …)) "
                        "— ne la traite pas toi-même.\n")

            # Si l'agent peut analyser des documents ET qu'un fichier est joint dans la
            # conversation, lui rappeler de l'analyser avec analyze_document (jamais le web).
            # Robuste : marche quel que soit l'agent à qui la tâche est confiée.
            if any(getattr(f, "__name__", "") == "analyze_document" for f in effective_tools):
                import re as _re2
                upl = None
                for _m in reversed(messages):
                    _mt = _re2.search(r"(uploads/[^\s\)\]\"']+)", str(_m.get("content", "") or ""))
                    if _mt:
                        upl = _mt.group(1)
                        break
                if upl:
                    system_prompt += (
                        f"\n📎 DOCUMENT JOINT : « {upl} ». Pour le relire / l'analyser / le critiquer / "
                        f"le résumer, appelle analyze_document('{upl}') — il lit le fichier RÉEL EN ENTIER. "
                        "N'utilise JAMAIS le web et n'invente rien à partir du titre.\n")

            # Liste GÉNÉRIQUE des outils de l'agent : tout outil COCHÉ est utilisable, quel
            # que soit son prompt métier. Surface chaque outil (nom + description) pour que
            # le modèle (même léger) sache qu'il PEUT l'utiliser et ne dise jamais « je ne
            # peux pas » alors qu'il a l'outil. Les transferts sont gérés par le routage.
            if effective_tools and current_agent.supports_tools:
                _tool_lines = []
                for _f in effective_tools:
                    _n = getattr(_f, "__name__", "")
                    if _n.startswith("transfer_to_") or not _n:
                        continue
                    _doc = (getattr(_f, "__doc__", "") or "").strip().replace("\n", " ")
                    _doc = " ".join(_doc.split())[:90]
                    _tool_lines.append(f"- {_n} : {_doc}" if _doc else f"- {_n}")
                if _tool_lines:
                    system_prompt += (
                        "\n🧰 OUTILS À TA DISPOSITION (utilise-les dès qu'ils sont pertinents ; "
                        "ne dis JAMAIS que tu ne peux pas faire ce qu'un de ces outils permet) :\n"
                        + "\n".join(_tool_lines) + "\n")

            # Expressivité vocale (optionnelle) : autorise une balise d'émotion en TÊTE
            # de réponse, retirée du texte affiché et exploitée par le TTS expressif.
            if os.getenv("VOICE_EMOTION_TAGS", "false").lower() in ("true", "1", "yes"):
                system_prompt += (
                    "\n🎭 EXPRESSIVITÉ : tu peux commencer ta réponse par UNE balise d'émotion "
                    "entre crochets, ex. « [emotion: enjoué] », « [emotion: calme] », "
                    "« [emotion: empathique] » (valeurs : neutre, enjoué, excité, triste, calme, "
                    "sérieux, empathique, fâché, chuchoté). Elle est invisible pour l'utilisateur "
                    "et sert à colorer la voix. N'en mets qu'UNE, au tout début.\n")

            # Chargement en cascade des fichiers de prompt locaux (custom Jarvis Swarm)
            local_instructions = ""
            current_dir = os.getcwd()
            while True:
                system_md = os.path.join(current_dir, "SYSTEM.md")
                append_system_md = os.path.join(current_dir, "APPEND_SYSTEM.md")
                jarvis_md = os.path.join(current_dir, "JARVIS.md")
                
                if os.path.exists(system_md):
                    try:
                        with open(system_md, "r", encoding="utf-8") as f:
                            system_prompt = f.read()
                        break
                    except Exception as e:
                        print(f"[\033[91mErreur SYSTEM.md\033[0m] Impossible de lire {system_md}: {e}")
                        
                if os.path.exists(append_system_md):
                    try:
                        with open(append_system_md, "r", encoding="utf-8") as f:
                            local_instructions = f.read() + "\n" + local_instructions
                    except Exception as e:
                        print(f"[\033[91mErreur APPEND_SYSTEM.md\033[0m] {e}")
                        
                if os.path.exists(jarvis_md):
                    try:
                        with open(jarvis_md, "r", encoding="utf-8") as f:
                            local_instructions = f.read() + "\n" + local_instructions
                    except Exception as e:
                        print(f"[\033[91mErreur JARVIS.md\033[0m] {e}")
                        
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == current_dir:
                    break
                current_dir = parent_dir
                
            if local_instructions.strip():
                system_prompt += "\n\n=== INSTRUCTIONS DE PROJET LOCALES ===\n" + local_instructions

            # Détection automatique de l'OS / environnement d'exécution.
            system_prompt += platform_info.execution_env_hint()

            # Rappel de citation des sources si l'agent dispose d'outils web.
            if any(getattr(f, "__name__", "") in ("web_search", "web_scrape") for f in effective_tools):
                system_prompt += ("\n[CITATIONS] Lorsque tu utilises des informations trouvées via "
                                  "web_search/web_scrape, cite explicitement les sources (URL) à la fin "
                                  "de ta réponse, sous une rubrique « Sources ».\n")

            # Règle d'or sur les mentions @agent
            system_prompt += "\n\n⚠️ INSTRUCTIONS SUR LES MENTIONS @AGENT :\n"
            system_prompt += "L'utilisateur peut cibler un ou plusieurs agents dans son message en écrivant `@NomDeLAgent` ou `@NomAmical` (ex: `@Auteur` ou `@Emilie`, `@CommunityManager` ou `@Lucas` ou `@CM`, `@Traducteur` ou `@Sofia`, `@Codeur` ou `@Robert`, `@Correcteur` ou `@Marc`, `@Jarvis`).\n"
            system_prompt += "Si tu vois une mention `@` ciblant un AUTRE agent dans le message ou dans la suite d'instructions de l'utilisateur, tu as l'obligation absolue d'effectuer ton propre travail (ex: traduire si tu es la traductrice Sofia, rédiger si tu es l'auteur Émilie), PUIS de transférer immédiatement la main à cet autre agent via ta fonction de transfert appropriée pour qu'il exécute sa partie du travail.\n"

            
            # RAG Automatique en arrière-plan
            user_messages = [m for m in messages if m.get("role") == "user"]
            if user_messages:
                last_user_msg = user_messages[-1]["content"]
                try:
                    rag_results = tools.memory_tools.semantic_mem.search(last_user_msg, limit=2)
                    if rag_results:
                        rag_context = "\n=== CONNAISSANCES PERTINENTES RETROUVÉES EN MÉMOIRE (RAG ARRIÈRE-PLAN) ===\n"
                        for res in rag_results:
                            rag_context += f"- {res}\n"
                        rag_context += "========================================================================\n"
                        system_prompt += rag_context
                except Exception as e:
                    print(f"[\033[91mRAG Erreur\033[0m] {e}")
            
            # Renforcer les consignes de transfert pour le superviseur — UNIQUEMENT s'il
            # existe d'autres agents à qui déléguer (sinon l'orchestrateur seul doit
            # répondre directement, pas refuser le travail).
            _orch = getattr(self, "orchestrator_name", "Jarvis")
            if current_agent.name == _orch and len(self.agents) > 1:
                system_prompt += "\n\n⚙️ ROUTAGE DE L'ESSAIM (délègue UNIQUEMENT si nécessaire) :\n"
                system_prompt += f"Tu es {current_agent.name}, l'orchestrateur. Tu réponds TOI-MÊME, sans déléguer, à : "
                system_prompt += "ta présentation/identité, les questions générales ou conversationnelles, et tout ce qui relève de TES propres outils "
                system_prompt += "(mémoire, agenda, listes, domotique, recherche web, notifications, images). "
                system_prompt += "Tu ne délègues QUE si la demande exige EXPLICITEMENT le métier d'un des agents ci-dessous "
                system_prompt += "(ex. écrire/déboguer du code, rédiger un roman, traduire un texte…) — et alors à UN SEUL agent pertinent. "
                system_prompt += "Ne délègue jamais une simple question (comme « qui es-tu ? ») et n'invente pas d'agent inexistant.\n\n"

                for other_name, other_agent in self.agents.items():
                    if other_name == _orch:
                        continue
                    # Description concise du rôle, extraite des 2 premières phrases du prompt de l'agent.
                    agent_desc = ""
                    if other_agent.system_prompt:
                        sentences = [s.strip() for s in other_agent.system_prompt.replace("\n", " ").split(".") if s.strip()]
                        agent_desc = ". ".join(sentences[:2]) + "."
                    system_prompt += f"   - **{other_agent.display_name or other_name}** — {agent_desc} → délègue via `transfer_to_{other_name}` (ou `query_agent('{other_name}', …)`).\n"

                system_prompt += "\nMULTI-TÂCHES : si la demande couvre PLUSIEURS domaines à la fois, utilise `query_agent` pour CHAQUE spécialiste concerné, puis fais une synthèse — n'utilise pas `transfer_to_` dans ce cas (cela perdrait les autres résultats).\n"
                system_prompt += "SUIVI : si l'utilisateur demande une modification d'un livrable produit récemment par un spécialiste, re-transfère à ce spécialiste.\n"
                system_prompt += "LIVRAISON : quand un spécialiste te renvoie son travail, recopie-le INTÉGRALEMENT dans ta réponse.\n"
                
                system_prompt += "\n3.1 GESTION DES DÉBATS & TABLES RONDES (TRÈS IMPORTANT) :\n"
                system_prompt += "   Si l'utilisateur te demande d'organiser un débat, une confrontation, une table ronde ou une discussion/collaboration entre plusieurs agents (ex: 'organise un débat entre toi, le codeur et l'auteur', 'faites une confrontation sur PostgreSQL vs MongoDB') :\n"
                system_prompt += "   - Tu DOIS obligatoirement appeler l'outil `debate_between_agents` immédiatement.\n"
                system_prompt += "   - Appelle directement l'outil avec les bons paramètres (`agents`, `subject`, `turns`), sans préambule.\n"

                system_prompt += "\n6. GESTION DE LA MÉMOIRE & APPRENTISSAGE PROACTIF (TRÈS IMPORTANT) :\n"
                system_prompt += "   - Si l'utilisateur te demande de retenir un fait, une préférence ou une information globale sur lui ou son environnement, appelle l'outil `memorize_fact` immédiatement.\n"
                system_prompt += "   - SOIS PROACTIF : si tu détectes au fil des conversations une préférence utilisateur clé, un prénom, un choix technologique majeur, une configuration ou un élément durable de son projet, utilise automatiquement `memorize_fact` pour le mémoriser dans sa base de connaissances, sans attendre qu'il te le demande explicitement ! C'est ce qui fait que ta mémoire à long terme s'enrichit et vit d'elle-même.\n"

                system_prompt += "\n7. PLANIFICATION DES TÂCHES COMPLEXES :\n"
                system_prompt += "   Pour une demande qui se décompose en PLUSIEURS étapes (ex: une mission multi-agents, un projet), appelle d'abord `make_plan` avec la liste des étapes (une par ligne) pour l'afficher à l'utilisateur, puis appelle `update_plan_step(step=N, status='done')` au fur et à mesure de l'avancement. Cela rend ton raisonnement transparent et suivi.\n"

            # Épuration préventive de l'historique des tours passés (évite les bugs d'IDs d'outils VLLM/Mistral)
            # On ne garde que les messages utilisateur et assistant contenant du texte pour l'historique passé,
            # mais on garde l'intégralité du tour actuel en cours pour préserver le flux de tool calling actif.
            clean_history = []
            for i, msg in enumerate(messages):
                if i >= original_messages_len:
                    clean_history.append(msg)
                else:
                    if msg.get("role") == "user":
                        clean_history.append(msg)
                    elif msg.get("role") == "assistant":
                        if msg.get("content"):
                            clean_msg = {
                                "role": "assistant",
                                "content": msg["content"]
                            }
                            if "name" in msg:
                                clean_msg["name"] = msg["name"]
                            clean_history.append(clean_msg)
                            
            # Mémoire avancée : compaction de l'historique long (résumé + éviction)
            # — n'affecte QUE la vue envoyée au LLM, pas l'historique persistant.
            clean_history = self._maybe_compact(current_agent.model, clean_history, steps)

            # Injection du system prompt de l'agent actif
            current_messages = [{"role": "system", "content": system_prompt}] + clean_history
            
            # Appel API via litellm (compatible OpenAI, Anthropic, Ollama...).
            # Streaming token-par-token (latence minimale, surtout vocal) : les
            # deltas de texte sont publiés en live (event 'message_delta') sans
            # être persistés ; le message final reste enregistré normalement.
            def _emit_delta(chunk, _agent=current_agent.name):
                run_context.publish_step({"type": "message_delta", "agent": _agent, "content": chunk})

            effective_model = self._route_model(current_agent.model, current_messages)
            response = self._complete(effective_model, current_messages, tools_schema, on_delta=_emit_delta)

            message = response.choices[0].message
            msg_dict = message.model_dump(exclude_none=True)
            msg_dict["name"] = current_agent.name
            messages.append(msg_dict)
            
            # Enregistrer la consommation de tokens exacte
            prompt_tokens = 0
            completion_tokens = 0
            if getattr(response, "usage", None):
                prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
            if prompt_tokens == 0 and completion_tokens == 0:
                prompt_tokens = len(str(current_messages)) // 4
                completion_tokens = len(str(msg_dict)) // 4
                
            tokens_used += prompt_tokens + completion_tokens
            steps.append({
                "type": "usage",
                "agent": current_agent.name,
                "model": current_agent.model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens
            })

            if message.content:
                print(f"\033[92m{current_agent.name}:\033[0m {message.content}")
                _has_tools = bool(getattr(message, "tool_calls", None))
                # Narration COURTE qui précède un appel d'outil (« je vais utiliser… ») →
                # step discret 'thought' (pas une bulle de chat), pour éviter le spam de
                # messages intermédiaires avant une délégation.
                if _has_tools and len(message.content.strip()) < 200:
                    steps.append({"type": "thought", "agent": current_agent.name, "content": message.content})
                else:
                    steps.append({
                        "type": "message",
                        "agent": current_agent.name,
                        "content": message.content
                    })

            if not getattr(message, "tool_calls", None):
                # Fallback sémantique si le modèle n'a pas déclenché de tool_call standard
                semantic_transitioned = False
                if True:
                    if message.content:
                        content_lower = message.content.lower()
                        
                        # Liste des mots-clés indiquant une intention de transfert ou délégation
                        handoff_keywords = [
                            "transfère", "transfert", "transférer", 
                            "relais", "délègue", "déléguer", "délégation", 
                            "passe la main", "passer la main", "demande à", "demander à",
                            "charge de", "charger de"
                        ]
                        
                        has_handoff_keyword = any(kw in content_lower for kw in handoff_keywords)
                        
                        if has_handoff_keyword:
                            for target_agent_name, target_agent in self.agents.items():
                                if target_agent_name == current_agent.name:
                                    continue
                                
                                # Identifiants sémantiques pour cet agent
                                agent_identifiers = [target_agent_name.lower()]
                                if target_agent.display_name:
                                    agent_identifiers.append(target_agent.display_name.lower())
                                    for part in target_agent.display_name.lower().split():
                                        if len(part) > 2:
                                            agent_identifiers.append(part)
                                            
                                # Synonymes métier spécifiques pour maximiser la réussite
                                if target_agent_name == "Codeur":
                                    agent_identifiers.extend(["développeur", "dev", "codeur"])
                                elif target_agent_name == "Auteur":
                                    agent_identifiers.extend(["écrivain", "romancier", "auteur"])
                                elif target_agent_name == "CommunityManager":
                                    agent_identifiers.extend(["cm", "influenceur", "community", "social", "facebook", "instagram", "twitter", "reseaux", "réseaux", "post", "promo", "promotion", "publication", "publier", "publie"])
                                elif target_agent_name == "Traducteur":
                                    agent_identifiers.extend(["traducteur", "traductrice", "traduction", "traduire"])
                                    
                                # Si le message mentionne explicitement cet agent, on effectue le relais
                                import re
                                matched = False
                                for ident in agent_identifiers:
                                    # \b assure qu'on matche le mot exact (évite "dev" dans "développer" ou "devenir")
                                    if re.search(rf"\b{re.escape(ident)}\b", content_lower):
                                        matched = True
                                        break
                                        
                                if matched:
                                    previous_agent_name = current_agent.name
                                    current_agent = target_agent
                                    print(f"[\033[95mTRANSITION SÉMANTIQUE ULTRA-ROBUSTE\033[0m -> Passage à l'agent \033[94m{current_agent.name}\033[0m]")
                                    steps.append({
                                        "type": "handoff",
                                        "from": previous_agent_name,
                                        "to": current_agent.name
                                    })
                                    messages.append({
                                        "role": "user",
                                        "content": f"[Relais système : La demande a été transférée à l'agent {target_agent_name} ({target_agent.display_name or target_agent_name}). Veuillez répondre à l'utilisateur.]"
                                    })
                                    semantic_transitioned = True
                                    break
                                    
                    if semantic_transitioned:
                        continue
                        
                # Plus aucun outil appelé, on a fini le tour
                break
                
            tool_calls = getattr(message, "tool_calls", None) or []

            # Anti-délégation parasite : si l'orchestrateur a DÉJÀ produit une vraie réponse
            # (contenu substantiel) dans ce tour, on ignore les transferts émis en même temps
            # (qwen3 ajoute parfois un transfer_to_ superflu après avoir répondu → il passe la
            # main sans raison, ex. vers l'Auteur non sollicité).
            if (current_agent.name == getattr(self, "orchestrator_name", "Jarvis")
                    and message.content and len(message.content.strip()) >= 200):
                _kept = [tc for tc in tool_calls if not tc.function.name.startswith("transfer_to_")]
                if len(_kept) != len(tool_calls):
                    print("[\033[93mOrchestrateur\033[0m] transfert superflu ignoré (réponse déjà fournie).")
                tool_calls = _kept

            # 1. Préparation : résolution + coercition + validation + gate HITL.
            prepared = []  # (tool_call, func_name, args, func, blocked, call_args, arg_error)
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except Exception:
                    args = {}
                print(f"[\033[93m{current_agent.name}\033[0m exécute \033[96m{func_name}\033[0m avec {args}]")
                steps.append({
                    "type": "tool_call",
                    "agent": current_agent.name,
                    "tool": func_name,
                    "args": args
                })
                func = next((f for f in effective_tools if f.__name__ == func_name), None)
                blocked = False
                call_args = args
                arg_error = None
                if func is not None:
                    # Validation/coercition des arguments selon le schéma de l'outil.
                    args = coerce_arguments(func, args)
                    call_args = dict(args)
                    if "user_confirmed" in call_args and not approvals.accepts_kw(func, "user_confirmed"):
                        call_args.pop("user_confirmed")
                    # Validation JSON-schema (outils MCP) : erreur claire au lieu d'un crash.
                    arg_error = validate_args_schema(func, call_args)
                    # Gate human-in-the-loop.
                    if not arg_error and approvals.is_sensitive(func) and not approvals.auto_approve_enabled() \
                            and not args.get("user_confirmed"):
                        blocked = True
                prepared.append((tool_call, func_name, args, func, blocked, call_args, arg_error))

            def _run_tool(fn, a):
                # Cache TTL des outils idempotents (web_search, etc.).
                name = getattr(fn, "__name__", "")
                ttl = _tool_cache_ttl()
                cache_key = None
                if ttl > 0 and name in _cacheable_tools():
                    try:
                        cache_key = (name, json.dumps(a, sort_keys=True, default=str))
                    except Exception:
                        cache_key = None
                    if cache_key is not None:
                        with _TOOL_CACHE_LOCK:
                            hit = _TOOL_CACHE.get(cache_key)
                        if hit and (time.time() - hit[0]) < ttl:
                            return hit[1]
                try:
                    res = fn(**a)
                except Exception as e:
                    # Si c'est une compétence dynamique (skills/<nom>.py), on note l'échec
                    # pour tenter une réparation automatique en fin de run.
                    try:
                        if os.path.exists(os.path.join("skills", f"{name}.py")):
                            skill_failures.append({"name": name, "error": str(e), "args": a})
                    except Exception:
                        pass
                    return f"Erreur lors de l'exécution de l'outil : {str(e)}"
                if cache_key is not None and isinstance(res, str):
                    with _TOOL_CACHE_LOCK:
                        _TOOL_CACHE[cache_key] = (time.time(), res)
                        if len(_TOOL_CACHE) > 256:
                            _TOOL_CACHE.pop(next(iter(_TOOL_CACHE)))
                return res

            # 2. Exécution. Si l'agent a demandé PLUSIEURS outils, on les lance en
            #    PARALLÈLE (ex: plusieurs query_agent → sous-agents concurrents).
            #    Le contexte (dont current_run_id) est copié dans chaque thread pour
            #    que les étapes des sous-agents remontent dans le même run.
            #    Les outils bloqués (approbation requise) ne sont PAS exécutés.
            results = [None] * len(prepared)
            runnable = [i for i, p in enumerate(prepared) if p[3] is not None and not p[4] and not p[6]]
            max_parallel = int(os.getenv("SWARM_MAX_PARALLEL", "4"))

            if len(runnable) > 1 and max_parallel > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_parallel, len(runnable))) as ex:
                    future_to_idx = {}
                    for i in runnable:
                        ctx_i = contextvars.copy_context()  # snapshot par tâche
                        future_to_idx[ex.submit(ctx_i.run, _run_tool, prepared[i][3], prepared[i][5])] = i
                    for fut in concurrent.futures.as_completed(future_to_idx):
                        results[future_to_idx[fut]] = fut.result()
            else:
                for i in runnable:
                    results[i] = _run_tool(prepared[i][3], prepared[i][5])

            # 3. Traitement SÉQUENTIEL et ORDONNÉ des résultats (préserve la logique
            #    de l'essaim : handoffs/transferts gérés dans l'ordre).
            for i, (tool_call, func_name, args, func, blocked, call_args, arg_error) in enumerate(prepared):
                if func is None:
                    err_msg = f"Erreur: Outil {func_name} introuvable ou non autorisé."
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": err_msg})
                    steps.append({"type": "tool_output", "agent": current_agent.name, "tool": func_name, "output": err_msg})
                    continue

                if arg_error:
                    # Validation JSON-schema échouée : on renvoie l'erreur au modèle (il se corrige).
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": arg_error})
                    steps.append({"type": "tool_output", "agent": current_agent.name, "tool": func_name, "output": arg_error})
                    continue

                if blocked:
                    # Action sensible non confirmée : on n'exécute pas, on demande l'accord.
                    msg = approvals.confirmation_message(func_name, args)
                    steps.append({"type": "approval_required", "agent": current_agent.name, "tool": func_name, "args": args})
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": msg})
                    steps.append({"type": "tool_output", "agent": current_agent.name, "tool": func_name, "output": msg})
                    continue

                result = results[i]
                # Vérifier si c'est un transfert (Handoff)
                if isinstance(result, Result):
                    if result.agent:
                        previous_agent_name = current_agent.name
                        current_agent = result.agent
                        print(f"[\033[95mTRANSITION\033[0m -> Passage à l'agent \033[94m{current_agent.name}\033[0m]")
                        steps.append({
                            "type": "handoff",
                            "from": previous_agent_name,
                            "to": current_agent.name
                        })
                    result_value = result.value
                else:
                    result_value = str(result)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result_value
                })
                steps.append({
                    "type": "tool_output",
                    "agent": current_agent.name,
                    "tool": func_name,
                    "output": result_value
                })

        # Hook post-tâche d'auto-amélioration (best-effort, ne bloque jamais le retour).
        self._improve_skills(current_agent, skill_failures, steps)
        self._auto_critic(current_agent, messages, steps)
        self._write_experience_report(starting_agent, messages, steps)
        self._induce_skill(starting_agent, messages, steps)
        self._update_user_profile(current_agent, messages, steps)

        return current_agent, messages, steps

"""Human-in-the-loop : gate d'approbation des outils sensibles.

Généralise le motif « confirmation sudo » à n'importe quel outil jugé risqué
(exécution shell/python, domotique, suppressions...). Avant d'exécuter un tel
outil, l'essaim exige un accord explicite : le modèle doit montrer l'action à
l'utilisateur puis ré-appeler l'outil avec user_confirmed=True.

Bypass : un canal de confiance (ex: vocal à la maison) peut activer
l'auto-approbation via la ContextVar `auto_approve_var` (posée par le serveur
selon le canal) ou la variable d'env AUTO_APPROVE_SENSITIVE.
"""
import contextvars
import inspect
import os

# Outils sensibles par défaut (surchargés par SENSITIVE_TOOLS, liste CSV).
# NB: execute_python_code est exclu (déjà isolé en sandbox Docker).
_DEFAULT_SENSITIVE = (
    "execute_bash_command,run_ssh_command,"
    "call_ha_service,delete_skill,delete_calendar_event,delete_list_item"
)

# Posée par le serveur pour la durée d'un run (selon le canal). None = défaut env.
auto_approve_var: "contextvars.ContextVar" = contextvars.ContextVar("auto_approve", default=None)


def sensitive_tool_names() -> set:
    raw = os.getenv("SENSITIVE_TOOLS", _DEFAULT_SENSITIVE)
    return {t.strip() for t in raw.split(",") if t.strip()}


def auto_approve_enabled() -> bool:
    v = auto_approve_var.get()
    if v is not None:
        return bool(v)
    return os.getenv("AUTO_APPROVE_SENSITIVE", "false").lower() in ("true", "1", "yes")


def is_sensitive(func) -> bool:
    if getattr(func, "_requires_approval", False):
        return True
    name = getattr(func, "__name__", "")
    # execute_python_code n'est « sûr » que parce qu'il s'exécute en sandbox Docker.
    # Si la sandbox est désactivée (SANDBOX_MODE=off), il tourne avec les droits du
    # serveur → on exige alors une approbation, comme execute_bash_command.
    if name == "execute_python_code" and os.getenv("SANDBOX_MODE", "docker").strip().lower() == "off":
        return True
    return name in sensitive_tool_names()


def accepts_kw(func, name: str) -> bool:
    """Vrai si la fonction accepte le mot-clé `name` (param explicite ou **kwargs)."""
    try:
        params = inspect.signature(func).parameters
    except (ValueError, TypeError):
        return False
    if name in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())


def confirmation_message(tool_name: str, args: dict) -> str:
    return (
        f"⛔ ACTION SENSIBLE « {tool_name} » — confirmation utilisateur requise.\n"
        f"Arguments demandés : {args}\n"
        "Tu DOIS interrompre l'exécution, montrer clairement à l'utilisateur l'action exacte "
        "qui va être réalisée, et attendre son accord explicite. Une fois qu'il a accepté, "
        "ré-appelle le même outil en ajoutant le paramètre user_confirmed=True."
    )

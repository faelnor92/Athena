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
    "execute_bash_command,run_ssh_command,save_new_skill,trigger_workflow,computer_use_action,"
    "call_ha_service,delete_skill,delete_calendar_event,delete_list_item,"
    "write_file,edit_file,apply_patch,code_rollback,run_tool_script,self_update,"
    "nextcloud_write_file,nextcloud_delete_file"
)

# Posée par le serveur pour la durée d'un run (selon le canal). None = défaut env.
auto_approve_var: "contextvars.ContextVar" = contextvars.ContextVar("auto_approve", default=None)


def sensitive_tool_names() -> set:
    # SENSITIVE_TOOLS="" (vide) = valeur PAR DÉFAUT, pas « aucun outil sensible » :
    # une ligne vide oubliée dans .env désactivait TOUT le HITL (faille critique de
    # l'audit 2026-06-22). Désactiver se demande EXPLICITEMENT : SENSITIVE_TOOLS=none.
    raw = os.getenv("SENSITIVE_TOOLS", "").strip()
    if not raw:
        raw = _DEFAULT_SENSITIVE
    elif raw.lower() == "none":
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


def admin_only_tool_names() -> set:
    """Outils réservés au rôle admin (RBAC), via ADMIN_ONLY_TOOLS (CSV). Vide par défaut."""
    raw = os.getenv("ADMIN_ONLY_TOOLS", "")
    return {t.strip() for t in raw.split(",") if t.strip()}


def caller_is_restricted() -> bool:
    """True si l'appelant est un utilisateur NON-admin (auth active). None (mode
    local/no-auth) ou 'admin' → non restreint."""
    try:
        from core.state import _current_role
        role = _current_role.get()
    except Exception:
        role = None
    return role is not None and role != "admin"


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
    if name in ("execute_python_code", "run_checks") and os.getenv("SANDBOX_MODE", "docker").strip().lower() == "off":
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


def get_proposed_diff_contents(func_name: str, args: dict) -> tuple:
    """Simule l'exécution de l'outil d'édition de code pour renvoyer (old_content, new_content)."""
    import os
    try:
        from tools.code_edit import _resolve, _flexible_replace, _apply_unified_diff
    except ImportError:
        return "", ""
        
    path = args.get("path")
    if not path:
        return "", ""
    real, err = _resolve(path, must_exist=False)
    if err:
        return "", ""
    
    old_content = ""
    if os.path.isfile(real):
        try:
            with open(real, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()
        except Exception:
            pass
            
    new_content = ""
    if func_name == "write_file":
        new_content = args.get("content", "")
    elif func_name == "edit_file":
        old_str = args.get("old_string", "")
        new_str = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        
        if old_str == new_str:
            new_content = old_content
        else:
            count = old_content.count(old_str)
            if count >= 1:
                new_content = old_content.replace(old_str, new_str) if replace_all \
                    else old_content.replace(old_str, new_str, 1)
            else:
                flexible, fcount = _flexible_replace(old_content, old_str, new_str, replace_all)
                if flexible is not None:
                    new_content = flexible
                else:
                    new_content = old_content
    elif func_name == "apply_patch":
        patch = args.get("patch", "")
        new_content, reason = _apply_unified_diff(old_content, patch)
        if reason:
            new_content = old_content
    else:
        new_content = old_content
        
    return old_content, new_content


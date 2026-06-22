"""Mode PLAN (lecture seule) pour le coder/agent, façon opencode / Claude Code.

Quand il est actif, l'agent ANALYSE et PROPOSE un plan, mais ne peut ni modifier de fichier
ni exécuter de commande mutante : les outils mutants sont retirés du schéma exposé au modèle
(donc non appelables) et un préambule lui rappelle de planifier sans agir.

Activable PAR UTILISATEUR (persistant, partagé entre athena_cli et l'onglet Code de l'UI).
"""
from core import shared_store

_NS = "plan_mode"

# Outils MUTANTS retirés en mode plan (écriture fichiers, exécution, effets de bord). Les outils
# de LECTURE/ANALYSE restent : read_file, search_code, find_*, file_outline, glob_files, run_checks,
# git_status/diff/log, todo_write, make_plan/get_plan, list_*, search_memory…
BLOCKED = {
    "write_file", "edit_file", "apply_patch",
    "execute_bash_command", "execute_python_code", "run_tool_script", "computer_use_action",
    "git_commit", "git_create_branch", "git_create_worktree", "git_remove_worktree",
    "save_new_skill", "delete_skill", "create_agent", "self_update", "reset_sandbox",
    "create_routine", "configure_monitoring", "trigger_workflow",
    "nextcloud_write_file", "nextcloud_delete_file",
    "document_revise", "document_publish", "document_autorevise", "document_translate",
    "memorize_fact", "store_document", "remember_relation",
    "send_notification",
    "generate_image", "generate_artistic_image", "generate_artistic_video",
    "create_email_draft", "clean_inbox", "archive_emails", "mark_emails_read",
    "add_calendar_event", "delete_calendar_event",
    "add_list_item", "toggle_list_item", "delete_list_item",
    "create_goal", "update_goal_status", "add_goal_step", "complete_goal_step", "set_goal_priority",
    "proxmox_vm_action", "proxmox_vm_exec",
}

PREAMBLE = (
    "\n\n=== MODE PLAN (LECTURE SEULE) ===\n"
    "Tu es en MODE PLAN. Tu DOIS analyser la demande et PROPOSER un plan d'action clair et "
    "ordonné, SANS modifier le moindre fichier ni exécuter de commande qui change l'état "
    "(écriture, shell, git commit…). Les outils mutants sont désactivés. Utilise les outils de "
    "LECTURE (read_file, search_code, glob_files, file_outline, git_diff…) pour étayer ton plan, "
    "puis termine par les ÉTAPES proposées. L'utilisateur basculera en mode normal pour exécuter."
)


def _scope() -> str:
    try:
        from core.user_config import current_user_key
        return current_user_key() or "local"
    except Exception:
        return "local"


def is_active(scope: str = None) -> bool:
    return bool(shared_store.get(_NS, scope or _scope()))


def set_active(active: bool, scope: str = None) -> bool:
    shared_store.set(_NS, scope or _scope(), bool(active))
    return bool(active)


def toggle(scope: str = None) -> bool:
    scope = scope or _scope()
    new = not is_active(scope)
    set_active(new, scope)
    return new


def is_blocked(tool_name: str) -> bool:
    return tool_name in BLOCKED

"""Politiques de permissions par canal.

Chaque canal (web, cli, voice, telegram:<id>...) a une politique :
  - auto_approve : auto-approuver les outils sensibles (cf. core.approvals) ;
  - allow        : "*" ou liste blanche d'outils autorisés ;
  - deny         : liste noire d'outils interdits (prioritaire sur allow).

Surchargeable via un fichier channel_policies.json (format {canal: {...}}) ou la
variable d'env CHANNEL_POLICIES (même JSON). Le canal courant est porté par la
ContextVar `current_channel` (posée par le serveur, propagée au thread swarm).
"""
import contextvars
import json
import os

current_channel: "contextvars.ContextVar" = contextvars.ContextVar("current_channel", default=None)

# Politiques par défaut. Le canal vocal/CLI local est « de confiance » ;
# le web exige confirmation (admin) ; Telegram (distant) interdit shell/ssh.
_DEFAULTS = {
    "web":      {"auto_approve": False, "allow": "*", "deny": []},
    "cli":      {"auto_approve": True,  "allow": "*", "deny": []},
    "voice":    {"auto_approve": True,  "allow": "*", "deny": []},
    "telegram": {"auto_approve": False, "allow": "*", "deny": ["execute_bash_command", "run_ssh_command"]},
    "default":  {"auto_approve": False, "allow": "*", "deny": []},
}

_cache = None


def _load_policies() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    policies = dict(_DEFAULTS)
    # Fichier
    path = os.getenv("CHANNEL_POLICIES_PATH", "channel_policies.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                policies.update(json.load(f))
        except Exception:
            pass
    # Variable d'env (prioritaire)
    env_json = os.getenv("CHANNEL_POLICIES", "").strip()
    if env_json:
        try:
            policies.update(json.loads(env_json))
        except Exception:
            pass
    _cache = policies
    return policies


def policy_for(channel) -> dict:
    if not channel:
        channel = "default"
    policies = _load_policies()
    if channel in policies:
        return policies[channel]
    # Canal namespacé (ex: "telegram:12345") → politique du préfixe.
    prefix = str(channel).split(":", 1)[0]
    return policies.get(prefix, policies["default"])


def auto_approve_for(channel) -> bool:
    return bool(policy_for(channel).get("auto_approve", False))


def tool_allowed(channel, tool_name: str) -> bool:
    pol = policy_for(channel)
    if tool_name in (pol.get("deny") or []):
        return False
    allow = pol.get("allow", "*")
    if allow == "*" or not allow:
        return True
    return tool_name in allow

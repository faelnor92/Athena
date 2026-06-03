"""Outils d'auto-extension : permettre à Athena de créer/configurer des agents.

Garde-fous : on ne touche jamais à l'orchestrateur 'Athena', les outils sont
whitelistés contre AVAILABLE_TOOLS (+ compétences dynamiques), l'avatar est
validé, et le swarm est rechargé à chaud après écriture de agents.yaml.
"""
import os
import re
import yaml

AGENTS_PATH = "agents.yaml"

# Apparences réellement dessinées côté UI (cf. getAgentSpriteSVG dans app.js).
VALID_AVATARS = {
    "robot_neon", "dev_purple", "writer_orange", "manager_gold", "artist_pink",
    "support_green", "scientist_blue", "agent_dark", "wizard_purple",
    "cyber_neko", "astronaut_white", "cyber_ninja",
}


def _known_tool_names():
    """Outils statiques + compétences dynamiques actuellement chargés."""
    import server
    names = set()
    swarm = getattr(server, "swarm", None)
    if swarm is not None:
        # AVAILABLE_TOOLS est défini au niveau du module swarm.
        try:
            from core.swarm import AVAILABLE_TOOLS, load_dynamic_skills
            names.update(AVAILABLE_TOOLS.keys())
            names.update(load_dynamic_skills().keys())
        except Exception:
            pass
    return names


def create_agent(name: str, system_prompt: str, model: str = "", tools: str = "",
                 avatar_type: str = "", display_name: str = "",
                 welcome_message: str = "") -> str:
    """
    Crée un nouvel agent dans l'essaim (ou met à jour un agent existant), puis recharge l'essaim à chaud.
    L'agent devient immédiatement utilisable et Athena peut lui déléguer des tâches (handoff automatique).
    name: Nom unique de l'agent (lettres/chiffres/underscore, ex: 'Analyste'). Le nom 'Athena' est protégé et refusé.
    system_prompt: Instruction système décrivant le rôle, le ton et la mission de l'agent.
    model: Identifiant du modèle LLM (ex: 'gpt-4o'). Vide = réutilise le modèle de Athena.
    tools: Noms d'outils à accorder, séparés par des virgules (ex: 'web_search,execute_python_code'). Les outils inconnus sont ignorés.
    avatar_type: Apparence parmi robot_neon, dev_purple, writer_orange, manager_gold, artist_pink, support_green, scientist_blue, agent_dark, wizard_purple, cyber_neko, astronaut_white, cyber_ninja.
    display_name: Nom affiché optionnel (sinon = name).
    welcome_message: Message d'accueil optionnel de l'agent.
    """
    import server
    swarm = getattr(server, "swarm", None)
    if swarm is None:
        return "Erreur : moteur d'essaim non initialisé."

    orch_name = getattr(swarm, "orchestrator_name", None) or "Athena"
    name = (name or "").strip()
    if not name:
        return "Erreur : le nom de l'agent est requis."
    if name.lower() == orch_name.lower():
        return f"Erreur : '{orch_name}' est l'orchestrateur et ne peut pas être créé ou écrasé."
    if not re.fullmatch(r"[A-Za-z0-9_\-]{2,40}", name):
        return ("Erreur : nom invalide. Utilise 2 à 40 caractères parmi lettres, "
                "chiffres, '_' et '-' (sans espaces ni accents).")
    if not (system_prompt or "").strip():
        return "Erreur : system_prompt est requis pour définir le rôle de l'agent."

    # Modèle : par défaut, on reprend celui de l'orchestrateur pour rester cohérent.
    if not (model or "").strip():
        athena = swarm.agents.get(orch_name)
        model = getattr(athena, "model", None) or "gpt-4o"

    # Outils : whitelist stricte.
    known = _known_tool_names()
    requested = [t.strip() for t in (tools or "").split(",") if t.strip()]
    granted, ignored = [], []
    for t in requested:
        (granted if t in known else ignored).append(t)

    # Avatar : validation douce.
    avatar = (avatar_type or "").strip().lower()
    avatar_note = ""
    if avatar and avatar not in VALID_AVATARS:
        avatar_note = f" (avatar '{avatar}' inconnu → robot_neon par défaut)"
        avatar = "robot_neon"
    if not avatar:
        avatar = "robot_neon"

    # Charger agents.yaml.
    try:
        with open(AGENTS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}
    agents = data.get("agents", []) or []

    # Détecter création vs mise à jour, en préservant les handoffs existants.
    existing = None
    for a in agents:
        if str(a.get("name", "")).lower() == name.lower():
            existing = a
            break

    entry = {
        "name": name,
        "display_name": display_name.strip() or (existing.get("display_name") if existing else None) or name,
        "system_prompt": system_prompt.strip(),
        "model": model,
        "supports_tools": True,
        "tools": granted,
        "avatar_type": avatar,
        "handoffs": (existing.get("handoffs") if existing else []) or [],
    }
    if welcome_message.strip():
        entry["welcome_message"] = welcome_message.strip()
    elif existing and existing.get("welcome_message"):
        entry["welcome_message"] = existing["welcome_message"]

    action = "mis à jour" if existing else "créé"
    if existing:
        agents = [entry if str(a.get("name", "")).lower() == name.lower() else a for a in agents]
    else:
        agents.append(entry)
    data["agents"] = agents

    # Écrire puis recharger à chaud.
    try:
        with open(AGENTS_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        swarm.load_agents(AGENTS_PATH)
    except Exception as e:
        return f"Erreur lors de l'écriture / rechargement de l'essaim : {e}"

    msg = f"Agent '{name}' {action} et activé (modèle {model}, avatar {avatar}{avatar_note})."
    if granted:
        msg += f" Outils accordés : {', '.join(granted)}."
    else:
        msg += " Aucun outil accordé (agent conversationnel)."
    if ignored:
        msg += f" Outils ignorés (inconnus) : {', '.join(ignored)}."
    msg += " Athena peut désormais lui déléguer des tâches via un transfert."
    return msg

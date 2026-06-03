import os
from dotenv import load_dotenv
from core.swarm import Swarm

_HELP = """Commandes CLI :
  /help                 cette aide
  /agents               liste les agents de l'essaim
  /agent <Nom>          bascule sur un agent (ex: /agent Codeur)
  /skills               liste les compétences dynamiques
  /doctor               auto-diagnostic (config, dépendances, services)
  /search <texte>       recherche dans la mémoire sémantique
  /notify [canal] <msg> envoie un message (canal: email/discord/slack/telegram/webhook)
  /profile              affiche le profil utilisateur
  /undo                 annule le dernier échange
  /retry                régénère la réponse à la dernière question
  /reset                efface la conversation courante
  quit / exit           quitter
"""


def _handle_command(text, swarm, current_agent, messages):
    """Traite une slash-command. Renvoie (handled: bool, current_agent)."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print(_HELP)
    elif cmd == "/agents":
        for name, a in swarm.agents.items():
            mark = " (actif)" if a is current_agent else ""
            print(f"  - {name}{mark} [{getattr(a, 'model', '?')}]")
    elif cmd == "/agent":
        target = swarm.agents.get(arg)
        if target:
            print(f"→ Agent actif : {arg}")
            return True, target
        print(f"Agent '{arg}' introuvable. /agents pour la liste.")
    elif cmd == "/skills":
        from core.swarm import load_dynamic_skills
        sk = load_dynamic_skills()
        print("Compétences :", ", ".join(sk.keys()) if sk else "(aucune)")
    elif cmd == "/doctor":
        from core.diagnostics import run_diagnostics
        for c in run_diagnostics(swarm):
            print(f"  {'✅' if c['ok'] else '❌'} {c['name']}: {c['detail']}")
    elif cmd == "/search":
        if not arg:
            print("Usage : /search <texte>")
        else:
            import tools.memory_tools as mt
            for res in (mt.semantic_mem.search(arg, limit=5) or ["(aucun résultat)"]):
                print(f"  • {res}")
    elif cmd == "/notify":
        from tools.notify_tools import send_notification
        chans = {"email", "discord", "slack", "telegram", "webhook"}
        sub = arg.split(maxsplit=1)
        if sub and sub[0].lower() in chans:
            channel, msg = sub[0].lower(), (sub[1] if len(sub) > 1 else "")
        else:
            channel, msg = "", arg
        print(send_notification(msg or "Test depuis le CLI Athena.", channel=channel))
    elif cmd == "/profile":
        from core.user_profile import user_profile
        print(user_profile.get() or "(profil vide)")
    elif cmd == "/undo":
        while messages and messages[-1].get("role") in ("assistant", "tool"):
            messages.pop()
        if messages and messages[-1].get("role") == "user":
            messages.pop()
        print("↩️  Dernier échange annulé.")
    elif cmd == "/retry":
        while messages and messages[-1].get("role") in ("assistant", "tool"):
            messages.pop()
        if messages and messages[-1].get("role") == "user":
            last = messages.pop().get("content")
            print(f"🔁 Régénération pour : {last}")
            messages.append({"role": "user", "content": last})
            agent, _msgs, _ = swarm.run(current_agent, messages)
            return True, agent
        print("Rien à régénérer.")
    elif cmd == "/reset":
        messages.clear()
        print("🧹 Conversation effacée.")
    else:
        print(f"Commande inconnue : {cmd}. Tape /help.")
    return True, current_agent


def main():
    # Chargement des variables d'environnement (.env)
    load_dotenv()

    # Confiner par défaut l'espace de travail au sous-dossier workspace/.
    if not os.environ.get("ACTIVE_WORKSPACE_DIR", "").strip():
        _ws = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace")
        os.makedirs(_ws, exist_ok=True)
        os.environ["ACTIVE_WORKSPACE_DIR"] = _ws

    from core.logging_config import setup_logging
    setup_logging()

    print("Initialisation de l'Orchestrateur...")
    swarm = Swarm("agents.yaml")

    # Démarrage des serveurs MCP configurés (no-op si mcp_servers.json absent).
    try:
        from tools.mcp_manager import mcp_manager
        mcp_manager.start()
    except Exception as e:
        print(f"[MCP] Démarrage ignoré : {e}")

    # On démarre toujours avec Athena
    current_agent = swarm.agents.get("Athena")
    if not current_agent:
        print("Erreur : Agent 'Athena' introuvable dans agents.yaml.")
        return

    messages = []
    print("\n\033[1mOrchestrateur Multi-Agent Prêt.\033[0m")
    print("Tape 'quit'/'exit' pour arrêter, ou \033[96m/help\033[0m pour les commandes.\n")

    while True:
        try:
            user_input = input("\033[94mVous:\033[0m ")
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            if not user_input.strip():
                continue

            # Slash-commands de gestion (parité avec l'UI : doctor, skills, undo…).
            if user_input.startswith("/"):
                _, current_agent = _handle_command(user_input, swarm, current_agent, messages)
                continue

            messages.append({"role": "user", "content": user_input})

            # Lancement de la boucle Swarm
            current_agent, messages, _ = swarm.run(current_agent, messages)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n\033[91mErreur fatale:\033[0m {e}")

if __name__ == "__main__":
    main()

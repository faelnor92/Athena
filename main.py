import os
from dotenv import load_dotenv
from core.swarm import Swarm

def main():
    # Chargement des variables d'environnement (.env)
    load_dotenv()
    
    print("Initialisation de l'Orchestrateur...")
    swarm = Swarm("agents.yaml")

    # Démarrage des serveurs MCP configurés (no-op si mcp_servers.json absent).
    try:
        from tools.mcp_manager import mcp_manager
        mcp_manager.start()
    except Exception as e:
        print(f"[MCP] Démarrage ignoré : {e}")

    # On démarre toujours avec Jarvis
    current_agent = swarm.agents.get("Jarvis")
    if not current_agent:
        print("Erreur : Agent 'Jarvis' introuvable dans agents.yaml.")
        return

    messages = []
    print("\n\033[1mOrchestrateur Multi-Agent Prêt.\033[0m")
    print("Tape 'quit' ou 'exit' pour arrêter.\n")

    while True:
        try:
            user_input = input("\033[94mVous:\033[0m ")
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
                
            messages.append({"role": "user", "content": user_input})
            
            # Lancement de la boucle Swarm
            current_agent, messages, _ = swarm.run(current_agent, messages)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n\033[91mErreur fatale:\033[0m {e}")

if __name__ == "__main__":
    main()

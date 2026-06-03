#!/usr/bin/env python3
import os
import sys
import argparse
from dotenv import load_dotenv
from core.swarm import Swarm

# Chargement du .env
load_dotenv()

# Couleurs ANSI pour le terminal
COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[92m"
COLOR_CYAN = "\033[96m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_MAGENTA = "\033[95m"
COLOR_BOLD = "\033[1m"

def main():
    print(f"{COLOR_BOLD}{COLOR_CYAN}🌿 Athena Coder CLI (Claude Code Style) | Swarm Engine{COLOR_RESET}\n")
    
    # Vérification du dossier de travail
    active_workspace = os.environ.get("ACTIVE_WORKSPACE_DIR", os.getcwd())
    print(f"📁 Dossier de travail : {COLOR_BOLD}{active_workspace}{COLOR_RESET}")
    os.environ["ACTIVE_WORKSPACE_DIR"] = active_workspace
    
    # Initialisation du Swarm
    try:
        swarm = Swarm("agents.yaml")
        coder_agent = swarm.agents.get("Codeur")
        if not coder_agent:
            print(f"{COLOR_RED}Erreur : Agent 'Codeur' introuvable dans agents.yaml.{COLOR_RESET}")
            sys.exit(1)
    except Exception as e:
        print(f"{COLOR_RED}Erreur initialisation Swarm : {e}{COLOR_RESET}")
        sys.exit(1)
        
    # Analyse des arguments pour lancer une seule instruction ou démarrer la boucle interactive
    parser = argparse.ArgumentParser(description="Athena Coder CLI Console")
    parser.add_argument("instruction", nargs="*", help="Instruction de code directe à exécuter")
    args = parser.parse_args()
    
    # Mémoire locale des messages de la session
    messages = []
    
    if args.instruction:
        # Mode une seule instruction
        cmd = " ".join(args.instruction)
        run_command(swarm, coder_agent, messages, cmd)
    else:
        # Mode interactif CLI Loop
        print(f"Tape ta demande de dev ci-dessous (ex: 'Crée un script de test', 'Affiche le code de X').")
        print(f"Écris {COLOR_RED}exit{COLOR_RESET} ou {COLOR_RED}quit{COLOR_RESET} pour fermer.\n")
        
        while True:
            try:
                prompt_str = f"{COLOR_BOLD}{COLOR_GREEN}athena-coder > {COLOR_RESET}"
                cmd = input(prompt_str).strip()
                if not cmd:
                    continue
                if cmd.lower() in ("exit", "quit"):
                    print(f"\n{COLOR_CYAN}Fermeture de la console Coder. À bientôt !{COLOR_RESET}")
                    break
                    
                run_command(swarm, coder_agent, messages, cmd)
            except KeyboardInterrupt:
                print(f"\n{COLOR_CYAN}Fermeture de la console Coder.{COLOR_RESET}")
                break
            except Exception as e:
                print(f"{COLOR_RED}Erreur : {e}{COLOR_RESET}")

def run_command(swarm, agent, messages, command_text):
    messages.append({"role": "user", "content": command_text})
    
    print(f"\n{COLOR_CYAN}⏳ Athena réfléchit et exécute les outils...{COLOR_RESET}")
    
    try:
        # Exécution de l'agent Codeur
        next_agent, new_messages, steps = swarm.run(agent, messages)
        
        # Affichage des étapes (Outils et exécutions bash/python)
        for step in steps:
            agent_name = step.get("agent", "Codeur")
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args = tc.get("function", {}).get("arguments", "")
                print(f"\n⚙️  [{COLOR_MAGENTA}{agent_name}{COLOR_RESET}] Appel de l'outil : {COLOR_BOLD}{func_name}{COLOR_RESET} (args: {func_args})")
                
            results = step.get("results", [])
            for res in results:
                print(f"📥 {COLOR_GREEN}Résultat de l'outil : {COLOR_RESET}")
                # Afficher avec une indentation propre
                lines = str(res.get("content", "")).splitlines()
                for line in lines[:20]: # Max 20 lignes de preview
                    print(f"  {line}")
                if len(lines) > 20:
                    print(f"  ... (+ {len(lines) - 20} lignes)")
        
        # Récupération de la dernière réponse de l'assistant
        last_msg = new_messages[-1] if new_messages else None
        if last_msg and last_msg.get("role") == "assistant" and last_msg.get("content"):
            print(f"\n🤖 {COLOR_BOLD}{COLOR_GREEN}Codeur : {COLOR_RESET}")
            print(last_msg.get("content"))
            print("")
            
        # Mettre à jour l'historique complet pour préserver le contexte
        messages.clear()
        messages.extend(new_messages)
        
    except Exception as e:
        print(f"{COLOR_RED}❌ Erreur lors de l'exécution : {e}{COLOR_RESET}\n")

if __name__ == "__main__":
    main()

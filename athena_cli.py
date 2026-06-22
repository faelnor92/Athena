#!/usr/bin/env python3
import os
import sys
import argparse
import asyncio
from typing import List, Dict

# Assurer que le PYTHONPATH inclut le dossier courant pour pouvoir importer le core
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.swarm import Swarm
from core.session import run_store

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_agent_response(agent_name: str, content: str):
    print(f"\n{Colors.OKCYAN}{Colors.BOLD}🤖 [{agent_name}]{Colors.ENDC}\n{content}\n")

def print_system_msg(msg: str):
    print(f"{Colors.WARNING}[Système] {msg}{Colors.ENDC}")

async def main():
    parser = argparse.ArgumentParser(description="Athena CLI - Terminal pur")
    parser.add_argument("--agent", type=str, default="Codeur", help="L'agent à verrouiller pour la session")
    args = parser.parse_args()

    print(f"{Colors.HEADER}{Colors.BOLD}===================================={Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}      ATHENA CLI - Mode Terminal    {Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}===================================={Colors.ENDC}")
    print(f"Agent ciblé : {Colors.OKGREEN}{args.agent}{Colors.ENDC}")
    print(f"Les transferts (Handoffs) sont bloqués. L'agent utilisera uniquement la sous-traitance (Délégation).")
    print(f"Tapez 'exit' ou 'quit' pour quitter.\n")

    # Initialiser le Swarm
    swarm = Swarm()
    try:
        swarm.load("config/agents.json")
    except Exception as e:
        print_system_msg(f"Erreur de chargement des agents: {e}")
        return

    agent = swarm.agents.get(args.agent)
    if not agent:
        print_system_msg(f"Agent '{args.agent}' introuvable. Agents disponibles: {', '.join(swarm.agents.keys())}")
        if swarm.agents:
            # Fallback sur l'orchestrateur ou le premier agent
            fallback_name = getattr(swarm, "orchestrator_name", None) or list(swarm.agents.keys())[0]
            agent = swarm.agents.get(fallback_name)
            print_system_msg(f"Fallback automatique sur l'agent '{agent.name}'.")
        else:
            print_system_msg("Aucun agent configuré. Veuillez vérifier config/agents.json.")
            return

    messages: List[Dict] = []
    
    while True:
        try:
            # Saisie utilisateur
            user_input = input(f"{Colors.OKGREEN}{Colors.BOLD}❯ Vous: {Colors.ENDC}").strip()
            if user_input.lower() in ["exit", "quit"]:
                break
            if not user_input:
                continue

            # Mode plan (lecture seule) : /plan, /build, /mode — interceptés AVANT le shell.
            if user_input.lower() in ("/plan", "/build", "/mode"):
                from core import plan_mode
                if user_input.lower() == "/plan":
                    plan_mode.set_active(True)
                    print_system_msg("🧭 Mode PLAN activé (lecture seule : l'agent propose un plan, n'écrit rien).")
                elif user_input.lower() == "/build":
                    plan_mode.set_active(False)
                    print_system_msg("🔨 Mode BUILD activé (édition et exécution autorisées).")
                else:
                    print_system_msg(f"Mode plan : {'ACTIF' if plan_mode.is_active() else 'inactif'}")
                continue

            # Commandes bash directes (!, /, $)
            if user_input.startswith(("!", "/", "$")):
                if user_input.startswith(("/bash")):
                    raw_cmd = user_input[5:].strip()
                else:
                    raw_cmd = user_input[1:].strip()
                print_system_msg(f"Exécution directe du shell: {raw_cmd}")
                # Console LOCALE de l'opérateur (pas une surface réseau) : le préfixe ! lance
                # volontairement TA commande dans TON shell. subprocess.run plutôt qu'os.system.
                import subprocess
                subprocess.run(raw_cmd, shell=True)  # nosec B602 — passthrough shell voulu, usage local
                continue

            messages.append({"role": "user", "content": user_input})
            
            print_system_msg("Traitement en cours...")
            
            # Exécution dans le swarm avec le mode verrouillé (locked=True)
            # Puisque le Swarm est asynchrone vis-à-vis des interfaces, on peut utiliser to_thread si besoin, 
            # mais ici on est dans un script natif, swarm.run est synchrone (sauf si on utilise les websockets/channels).
            # En appelant run() nativement, le log terminal sera capturé par sys.stdout ou print direct.
            next_agent, messages, steps = swarm.run(agent, messages, locked=True)

            # Extraire les derniers messages pour les afficher
            for step in steps:
                if step.get("type") == "message":
                    print_agent_response(step.get("agent", "IA"), step.get("content", ""))
                elif step.get("type") == "terminal_output_direct":
                    print(f"{Colors.OKBLUE}{step.get('output', '')}{Colors.ENDC}")
                elif step.get("type") == "tool_call":
                    tool = step.get("tool", "")
                    print(f"{Colors.WARNING}  🔧 Outil utilisé : {tool}{Colors.ENDC}")
                    if tool.startswith("delegate_to_"):
                        print(f"{Colors.WARNING}  🤝 L'agent sous-traite la demande en tâche de fond...{Colors.ENDC}")
                elif step.get("type") == "tool_output":
                    # Rendre VISIBLE ce qui aide l'utilisateur à suivre : la liste de tâches
                    # (todo_write) et les diagnostics de code (boucle de feedback LSP).
                    out = str(step.get("output", ""))
                    tool = step.get("tool", "")
                    if tool == "todo_write" or out.startswith("📋"):
                        print(f"{Colors.OKCYAN}{out}{Colors.ENDC}")
                    elif "❌ Erreurs détectées" in out or "⚠️ Avertissements" in out:
                        idx = out.find("❌")
                        if idx < 0:
                            idx = out.find("⚠️")
                        print(f"{Colors.WARNING}{out[idx:]}{Colors.ENDC}")

        except KeyboardInterrupt:
            print("\n")
            break
        except Exception as e:
            print_system_msg(f"Erreur d'exécution: {e}")

if __name__ == "__main__":
    asyncio.run(main())

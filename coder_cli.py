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
        return
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
                    
                if cmd.startswith("/"):
                    parts = cmd.split(None, 1)
                    slash_cmd = parts[0].lower()
                    slash_args = parts[1] if len(parts) > 1 else ""
                    
                    if slash_cmd == "/help":
                        print(f"\n{COLOR_BOLD}Commandes disponibles :{COLOR_RESET}")
                        print(f"  {COLOR_CYAN}/model [nom_modele]{COLOR_RESET} : Affiche ou change le modèle actif de l'agent.")
                        print(f"  {COLOR_CYAN}/diff{COLOR_RESET}              : Affiche les modifications git en cours dans le workspace.")
                        print(f"  {COLOR_CYAN}/commit{COLOR_RESET}            : Génère et propose un message de commit basé sur le diff, puis commit.")
                        print(f"  {COLOR_CYAN}/clear{COLOR_RESET}             : Efface l'historique de discussion de la session.")
                        print(f"  {COLOR_CYAN}/help{COLOR_RESET}              : Affiche cette aide.")
                        print("")
                        continue
                        
                    elif slash_cmd == "/model":
                        if not slash_args:
                            print(f"\nModèle actif actuel : {COLOR_BOLD}{COLOR_GREEN}{coder_agent.model}{COLOR_RESET}\n")
                        else:
                            coder_agent.model = slash_args
                            print(f"\nModèle modifié pour : {COLOR_BOLD}{COLOR_GREEN}{coder_agent.model}{COLOR_RESET}\n")
                        continue
                        
                    elif slash_cmd == "/diff":
                        import subprocess
                        try:
                            res = subprocess.run(
                                ["git", "diff"],
                                cwd=active_workspace,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            if res.returncode != 0:
                                print(f"{COLOR_RED}Erreur lors de l'exécution de git diff : {res.stderr.strip()}{COLOR_RESET}")
                            elif not res.stdout.strip():
                                print("Aucune modification détectée dans le dépôt git.")
                            else:
                                print(f"\n{COLOR_BOLD}Différence git en cours :{COLOR_RESET}\n")
                                for line in res.stdout.splitlines():
                                    if line.startswith("+"):
                                        print(f"\033[32m{line}\033[0m")
                                    elif line.startswith("-"):
                                        print(f"\033[31m{line}\033[0m")
                                    elif line.startswith("@@"):
                                        print(f"\033[36m{line}\033[0m")
                                    else:
                                        print(line)
                                print("")
                        except Exception as e:
                            print(f"{COLOR_RED}Erreur : {e}{COLOR_RESET}")
                        continue
                        
                    elif slash_cmd == "/commit":
                        import subprocess
                        try:
                            res = subprocess.run(
                                ["git", "diff"],
                                cwd=active_workspace,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            if res.returncode != 0:
                                print(f"{COLOR_RED}Erreur : {res.stderr.strip()}{COLOR_RESET}")
                                continue
                            
                            diff_content = res.stdout.strip()
                            if not diff_content:
                                res_staged = subprocess.run(
                                    ["git", "diff", "--cached"],
                                    cwd=active_workspace,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True
                                )
                                diff_content = res_staged.stdout.strip()
                                
                            if not diff_content:
                                print("Aucune modification à commiter.")
                                continue
                                
                            print(f"{COLOR_CYAN}Génération du message de commit en cours...{COLOR_RESET}")
                            
                            prompt = (
                                "Tu es un assistant spécialisé en gestion de version git. Rédige un message de commit "
                                "court, clair, au format conventionnel (ex. 'feat: description' ou 'fix: description'), "
                                "décrivant les modifications suivantes. Renvoie UNIQUEMENT le message de commit, "
                                "sans aucune introduction ni autre texte.\n\n"
                                f"Voici le diff :\n{diff_content}"
                            )
                            
                            model_to_use = swarm._utility_model(coder_agent.model)
                            resp = swarm._complete(
                                model=model_to_use,
                                messages=[{"role": "user", "content": prompt}]
                            )
                            commit_msg = resp.choices[0].message.content.strip()
                            
                            if commit_msg.startswith('"') and commit_msg.endswith('"'):
                                commit_msg = commit_msg[1:-1].strip()
                            elif commit_msg.startswith("'") and commit_msg.endswith("'"):
                                commit_msg = commit_msg[1:-1].strip()
                                
                            print(f"\nMessage de commit proposé :\n{COLOR_BOLD}{COLOR_GREEN}{commit_msg}{COLOR_RESET}\n")
                            ans = input("Voulez-vous commiter avec ce message ? [y/N] : ").strip().lower()
                            if ans in ("y", "yes", "o", "oui"):
                                commit_res = subprocess.run(
                                    ["git", "commit", "-a", "-m", commit_msg],
                                    cwd=active_workspace,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True
                                )
                                if commit_res.returncode == 0:
                                    print(f"{COLOR_GREEN}✓ Modifications commitées avec succès !{COLOR_RESET}\n")
                                else:
                                    print(f"{COLOR_RED}Erreur commit : {commit_res.stderr.strip() or commit_res.stdout.strip()}{COLOR_RESET}")
                            else:
                                print("Validation annulée.")
                        except Exception as e:
                            print(f"{COLOR_RED}Erreur : {e}{COLOR_RESET}")
                        continue
                        
                    elif slash_cmd == "/clear":
                        messages.clear()
                        print(f"\n{COLOR_CYAN}L'historique des messages a été vidé.{COLOR_RESET}\n")
                        continue
                        
                    else:
                        print(f"{COLOR_RED}Commande slash inconnue : {slash_cmd}. Tapez /help pour voir la liste.{COLOR_RESET}")
                        continue
                
                run_command(swarm, coder_agent, messages, cmd)
            except KeyboardInterrupt:
                print(f"\n{COLOR_CYAN}Fermeture de la console Coder.{COLOR_RESET}")
                break
            except Exception as e:
                print(f"{COLOR_RED}Erreur : {e}{COLOR_RESET}")

def run_command(swarm, agent, messages, command_text):
    messages.append({"role": "user", "content": command_text})
    
    print(f"\n{COLOR_CYAN}⏳ Athena réfléchit et exécute les outils...{COLOR_RESET}")
    
    from tools import dev_container as _dev_container
    from core import channels as _channels
    _dc_token = None
    _chan_token = None
    
    try:
        if _dev_container.enabled():
            _dc_token = _dev_container.activate(_dev_container.sanitize_key("local", None))
        _chan_token = _channels.current_channel.set("cli")
        
        # Exécution de l'agent Codeur
        next_agent, new_messages, steps = swarm.run(agent, messages)
        
        # Affichage des étapes (Outils et exécutions bash/python)
        for step in steps:
            agent_name = step.get("agent", "Codeur")
            tool_calls = step.get("tool_calls", [])
            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args = tc.get("function", {}).get("arguments", "")
                # Masque les éventuels secrets (clés API, mots de passe) avant affichage console.
                try:
                    from core.redaction import redact_secrets
                    func_args = redact_secrets(str(func_args))
                except Exception:
                    pass
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
    finally:
        if _dc_token is not None:
            _dev_container.deactivate(_dc_token)
        if _chan_token is not None:
            _channels.current_channel.reset(_chan_token)

if __name__ == "__main__":
    main()

"""Outil de chaîne de montage (Pipeline rigide)."""

def run_rigid_pipeline(agents_list: str, task: str) -> str:
    """EXÉCUTION STRICTE EN CHAÎNE DE MONTAGE.
    
    Force l'exécution séquentielle d'une tâche à travers une liste stricte d'agents.
    Le résultat du premier agent est passé EXACTEMENT comme entrée au second, et ainsi de suite.
    Les agents n'ont pas le droit de transférer la main à un autre agent hors de la liste.
    
    Args:
        agents_list: Liste des noms exacts des agents séparés par des virgules (ex: "Codeur, Testeur, Documentaliste"). L'ordre est strict.
        task: La tâche ou donnée initiale à traiter par le premier agent.
        
    Returns:
        Le résultat final de la chaîne, ou une erreur si le pipeline échoue.
    """
    from core.state import swarm
    
    names = [n.strip() for n in agents_list.split(",") if n.strip()]
    if not names:
        return "Erreur: Aucun agent fourni dans la liste."
    
    current_input = task
    history_report = []
    
    for i, name in enumerate(names):
        agent = swarm.agents.get(name)
        if not agent:
            return f"Erreur: L'agent '{name}' n'existe pas dans le système."
        
        history_report.append(f"--- [Étape {i+1}/{len(names)}] Tâche envoyée à l'agent '{name}' ---")
        try:
            # Pipeline rigide : locked + lock_delegation retirent TOUTE bascule vers un autre
            # agent (transfer_to_ ET delegate_to_), donc l'agent ne peut pas dévier de la
            # chaîne. max_turns=3 pour éviter qu'un agent ne boucle dans son coin trop longtemps.
            res_agent, res_messages, res_steps = swarm.run(
                starting_agent=agent,
                messages=[{"role": "user", "content": current_input}],
                max_turns=3,
                locked=True,
                lock_delegation=True
            )
            
            # On récupère la dernière réponse de l'agent
            output = ""
            if res_messages:
                # Filtrer les tool_calls pour ne prendre que le contenu textuel final
                for msg in reversed(res_messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        output = msg["content"]
                        break
            
            if not output:
                output = "Aucun résultat texte renvoyé par l'agent."
                
            current_input = output
            history_report.append(f"-> Terminé. Résultat de {name} pris comme entrée pour le suivant.")
            
        except Exception as e:
            return f"Erreur fatale lors de l'exécution du pipeline à l'étape '{name}': {str(e)}"
            
    summary = "\n".join(history_report)
    return f"{summary}\n\n=== RÉSULTAT FINAL DU PIPELINE ===\n{current_input}"

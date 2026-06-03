"""Outil de chaîne de montage (Pipeline rigide).

Deux usages :
- `run_rigid_pipeline` : outil ad-hoc que l'orchestrateur peut appeler (liste d'agents + tâche).
- `run_pipeline` : exécution d'un WORKFLOW nommé/sauvegardé (cf. core/pipelines.py) — mode
  déterministe type CrewAI, lancé directement (UI/API/routine), chaque étape tracée.
"""
import os
import time


def run_pipeline(pipeline: dict, initial_input: str = "") -> dict:
    """Exécute un workflow déterministe : étapes séquentielles, sortie d'une étape = entrée
    de la suivante, aucun agent ne peut dévier (locked + lock_delegation). Chaque étape est
    un run tracé distinct (observabilité). Renvoie {name, steps:[{agent, output, run_id,
    error?}], final, error?}."""
    from core.state import swarm, _orch_agent, _current_username
    from core.tracing import run_store
    from core.run_context import registry as run_registry, current_run_id
    from core import channels, approvals

    steps_def = pipeline.get("steps") or []
    name = pipeline.get("name") or "Workflow"
    if not steps_def:
        return {"name": name, "steps": [], "final": "", "error": "Pipeline sans étape."}

    max_turns = int(os.getenv("PIPELINE_STEP_MAX_TURNS", "6") or 6)
    results = []
    carry = (initial_input or "").strip()

    # Contexte commun : canal dédié + auto-approbation (exécution batch déterministe).
    chan_token = channels.current_channel.set("pipeline")
    appr_token = approvals.auto_approve_var.set(True)
    try:
        for i, step in enumerate(steps_def):
            agent = swarm.agents.get(step["agent"])
            if not agent:
                results.append({"agent": step["agent"], "output": "",
                                "error": "Agent introuvable dans le système."})
                return {"name": name, "steps": results, "final": carry,
                        "error": f"Agent '{step['agent']}' introuvable (étape {i + 1})."}

            parts = [f"[Étape {i + 1}/{len(steps_def)} — instruction]\n{step['instruction']}"]
            if step.get("expected_output"):
                parts.append(f"[Format / sortie attendue]\n{step['expected_output']}")
            if carry:
                parts.append(f"[Entrée fournie par l'étape précédente]\n{carry}")
            content = "\n\n".join(parts)

            rid = run_store.new_run_id()
            started = time.time()
            rid_token = current_run_id.set(rid)
            run_registry.start(rid)
            try:
                final_agent, msgs, steps = swarm.run(
                    starting_agent=agent,
                    messages=[{"role": "user", "content": content}],
                    max_turns=max_turns, locked=True, lock_delegation=True,
                )
                output = ""
                for m in reversed(msgs):
                    if m.get("role") == "assistant" and m.get("content"):
                        output = m["content"]
                        break
                output = output or "(aucun résultat texte)"
                run_store.save(
                    run_id=rid, agent=final_agent.name, status="pipeline",
                    user_message=f"[{name}] étape {i + 1} → {agent.name}",
                    final_response=output,
                    duration_ms=int((time.time() - started) * 1000),
                    steps=list(steps), created_at=started,
                )
                results.append({"agent": agent.name, "output": output, "run_id": rid})
                carry = output
            except Exception as e:
                run_store.save(run_id=rid, agent=agent.name, status="error",
                               user_message=f"[{name}] étape {i + 1}", error=str(e),
                               created_at=started)
                results.append({"agent": agent.name, "output": "", "error": str(e), "run_id": rid})
                return {"name": name, "steps": results, "final": carry,
                        "error": f"Échec à l'étape {i + 1} ({agent.name}) : {e}"}
            finally:
                run_registry.finish(rid)
                current_run_id.reset(rid_token)
    finally:
        channels.current_channel.reset(chan_token)
        approvals.auto_approve_var.reset(appr_token)

    return {"name": name, "steps": results, "final": carry}


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

import os

def manage_conversations(action: str, name: str = None) -> str:
    """
    Gère les conversations de l'historique de discussion.
    action: L'action à réaliser parmi : 'list' (lister les conversations), 'create' (créer une nouvelle), 'delete_current' (supprimer la conversation active courante), 'delete_all' (supprimer toutes les conversations).
    name: Nom optionnel pour une nouvelle conversation à créer.
    """
    # Import dynamique à l'exécution pour éviter les dépendances circulaires
    import server
    session = server.session
    
    if action == "list":
        convs = session.manager.conversations
        summary = "Conversations disponibles :\n"
        for cid, c in convs.items():
            active_marker = " (Active)" if cid == session.manager.active_id else ""
            summary += f"- ID: {cid} | Nom: '{c['name']}'{active_marker}\n"
        return summary
    elif action == "create":
        cid = session.manager.new_conversation(name)
        return f"Nouvelle conversation '{session.manager.conversations[cid]['name']}' créée avec succès (ID: {cid})."
    elif action == "delete_current":
        session.manager.delete_conversation(session.manager.active_id)
        return "La conversation active a été supprimée avec succès. Retour à la discussion principale."
    elif action == "delete_all":
        # Réinitialiser toutes les conversations
        session.manager.conversations = {}
        session.manager.active_id = "default"
        session.manager.load()
        session.manager.save()
        return "Toutes les conversations ont été effacées avec succès."
    return f"Action '{action}' non reconnue."

def query_agent(agent_name: str, prompt: str) -> str:
    """
    Exécute un autre agent de l'essaim en arrière-plan avec une requête spécifique et renvoie sa réponse finale.
    Utile pour déléguer des sous-tâches en parallèle ou obtenir des expertises croisées dans un seul rapport de Jarvis.
    agent_name: Le nom de l'agent à interroger (ex: 'Codeur', 'Auteur', 'Traducteur', 'CommunityManager', 'Correcteur').
    prompt: La question ou tâche spécifique à confier à cet agent.
    """
    import server
    if not hasattr(server, "swarm") or not server.swarm:
        return "Erreur: Le moteur d'orchestration de l'essaim n'est pas initialisé."
        
    swarm = server.swarm
    if agent_name not in swarm.agents:
        available = ", ".join(swarm.agents.keys())
        return f"Erreur: Agent '{agent_name}' non trouvé. Agents disponibles : {available}"
        
    target_agent = swarm.agents[agent_name]
    
    try:
        # Exécuter l'agent dans un flux d'historique propre et isolé
        sub_messages = [{"role": "user", "content": prompt}]
        final_agent, new_messages, steps = swarm.run(target_agent, sub_messages)
        
        # Extraire la réponse finale générée par l'agent
        for msg in reversed(new_messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                return msg["content"]
                
        return f"L'agent '{agent_name}' a terminé sans renvoyer de message."
    except Exception as e:
        return f"Erreur lors de l'exécution en arrière-plan de l'agent '{agent_name}' : {e}"

def debate_between_agents(agents: str, subject: str, turns: str = "2") -> str:
    """
    Lance un débat collaboratif (table ronde) entre plusieurs agents pour confronter leurs idées sur un sujet et génère une synthèse.
    agents: Les noms des agents participants séparés par des virgules (ex: 'Jarvis,Codeur,Auteur' ou 'Codeur,Auteur').
    subject: Le sujet, problème ou question sur lequel ils doivent débattre.
    turns: Le nombre de tours de table complets (ex: '2').
    """
    import server
    import litellm
    import os
    
    if not hasattr(server, "swarm") or not server.swarm:
        return "Erreur: Le moteur d'orchestration de l'essaim n'est pas initialisé."
        
    swarm = server.swarm
    
    # Helper pour publier des étapes live dans le run courant (isolé par ContextVar).
    def publish_step(step_dict):
        try:
            from core.run_context import publish_step as _pub
            _pub(step_dict)
        except Exception:
            pass
    
    # Parser la liste d'agents (séparés par virgules)
    agent_names_raw = [a.strip() for a in agents.split(",") if a.strip()]
    if len(agent_names_raw) < 2:
        return "Erreur: Il faut au moins 2 agents pour un débat. Séparez les noms par des virgules (ex: 'Codeur,Auteur')."
    
    # Normalisation et validation des noms
    available_keys = {k.lower(): k for k in swarm.agents.keys()}
    resolved_agents = []
    
    for raw_name in agent_names_raw:
        key = raw_name.lower()
        if key not in available_keys:
            available_names = ", ".join(swarm.agents.keys())
            return f"Erreur: Agent '{raw_name}' introuvable. Agents disponibles : {available_names}"
        resolved_name = available_keys[key]
        if resolved_name not in [a[0] for a in resolved_agents]:  # éviter les doublons
            resolved_agents.append((resolved_name, swarm.agents[resolved_name]))
    
    if len(resolved_agents) < 2:
        return "Erreur: Il faut au moins 2 agents distincts pour un débat."
    
    try:
        num_turns = int(turns)
        if num_turns < 1:
            num_turns = 1
        if num_turns > 5:
            num_turns = 5
    except ValueError:
        num_turns = 2
    
    num_agents = len(resolved_agents)
    agent_display = " 🤝 ".join([f"`{name}`" for name, _ in resolved_agents])
    
    # Total de répliques = ouverture (1) + tours_complets * nb_agents
    total_replies = 1 + num_turns * num_agents
    current_reply = 0
        
    transcript = []
    
    print(f"🎙️ [Debate] Table ronde entre {', '.join([n for n,_ in resolved_agents])} sur : '{subject}' ({num_turns} tours, {total_replies} répliques)")
    
    # Publier le démarrage du débat dans le cockpit
    publish_step({
        "type": "activation",
        "agent": resolved_agents[0][0]
    })
    publish_step({
        "type": "tool_output",
        "output": f"⚖️ Table ronde lancée : {agent_display} — {num_turns} tours sur « {subject[:80]}... »"
    })
    
    # Consigne de concision
    CONCISION = "\n\nIMPORTANT : Sois concis et structuré. Maximum 150 mots. Va droit à l'essentiel."
    
    def call_agent_directly(agent, user_content):
        """Appelle directement le LLM de l'agent sans passer par le Swarm (évite la récursion)."""
        if agent.name == "Jarvis":
            sys_prompt = (
                "Tu es Jarvis, le conseiller principal. Tu participes à une table ronde collaborative en coulisses. "
                "Réponds avec tes meilleures suggestions et arguments. Sois concis."
            )
        else:
            sentences = [s.strip() for s in agent.system_prompt.replace("\n", " ").split(".") if s.strip()]
            sys_prompt = ". ".join(sentences[:2]) + ". Réponds de manière concise et structurée."
            
        completion_kwargs = {
            "model": agent.model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content + CONCISION}
            ]
        }
        
        custom_base = os.environ.get("CUSTOM_LLM_API_BASE", "").strip()
        custom_key = os.environ.get("CUSTOM_LLM_API_KEY", "").strip()
        
        is_standard = any(prefix in agent.model.lower() for prefix in ["gpt-", "claude-", "gemini-", "groq/", "openrouter/", "ollama/", "mistral/"])
        has_official_key = False
        if "gpt-" in agent.model.lower():
            has_official_key = bool(os.environ.get("OPENAI_API_KEY"))
        elif "claude-" in agent.model.lower():
            has_official_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        elif "gemini-" in agent.model.lower():
            has_official_key = bool(os.environ.get("GEMINI_API_KEY"))
            
        use_custom = custom_base and (not is_standard or not has_official_key or agent.model.startswith("custom_openai/") or agent.model.startswith("openai/"))
        
        if use_custom:
            base = custom_base
            if "/v1" in base and "/api" not in base:
                base = base.replace("/v1", "/api/v1")
                
            completion_kwargs["api_base"] = base
            completion_kwargs["api_key"] = custom_key if custom_key else "placeholder-key"
                
            local_model = agent.model if agent.model else "qwen3"
            if not "/" in local_model:
                completion_kwargs["model"] = f"openai/{local_model}"
            else:
                completion_kwargs["model"] = local_model
                
        try:
            response = litellm.completion(**completion_kwargs)
            return response.choices[0].message.content or "(pas de réponse)"
        except Exception as e:
            return f"[Erreur API pour {agent.name}: {str(e)}]"

    # === DÉROULEMENT DE LA TABLE RONDE ===
    
    other_names = ", ".join([n for n, _ in resolved_agents[1:]])
    
    # 1. Ouverture par le premier agent
    first_name, first_agent = resolved_agents[0]
    current_reply += 1
    publish_step({"type": "activation", "agent": first_name})
    publish_step({"type": "tool_output", "output": f"🗣️ [{current_reply}/{total_replies}] {first_name} ouvre le débat..."})
    
    prompt_open = (
        f"Tu participes à une table ronde avec {other_names} sur le sujet : \"{subject}\".\n"
        f"Expose tes propositions initiales et arguments clés pour lancer la discussion."
    )
    
    resp = call_agent_directly(first_agent, prompt_open)
    transcript.append(f"#### 👤 {first_name}\n{resp}\n")
    last_response = resp
    last_speaker = first_name
    
    publish_step({"type": "tool_output", "output": f"✅ [{current_reply}/{total_replies}] {first_name} a exposé ses arguments."})
    
    # 2. Tours de table complets
    for tour in range(num_turns):
        for agent_name, agent_obj in resolved_agents:
            # Ne pas faire parler deux fois de suite le même agent
            if agent_name == last_speaker and tour == 0 and agent_name == first_name:
                continue
                
            current_reply += 1
            publish_step({"type": "activation", "agent": agent_name})
            publish_step({"type": "tool_output", "output": f"🗣️ [{current_reply}/{total_replies}] {agent_name} prend la parole (tour {tour + 1})..."})
            
            other_participants = ", ".join([n for n, _ in resolved_agents if n != agent_name])
            
            prompt = (
                f"Tu participes à une table ronde sur : \"{subject}\" avec {other_participants}.\n"
                f"Dernière intervention de {last_speaker} :\n\"\"\"\n{last_response}\n\"\"\"\n"
                f"Réagis, contredis les points faibles et apporte ta perspective d'expert."
            )
            resp = call_agent_directly(agent_obj, prompt)
            transcript.append(f"#### 👤 {agent_name}\n{resp}\n")
            last_response = resp
            last_speaker = agent_name
            
            publish_step({"type": "tool_output", "output": f"✅ [{current_reply}/{total_replies}] {agent_name} a répondu."})

    # Synthèse finale
    publish_step({"type": "tool_output", "output": "📝 Compilation du rapport de la table ronde..."})
    
    formatted_transcript = "\n---\n".join(transcript)
    report = (
        f"### ⚖️ Table Ronde Collaborative\n"
        f"**Participants :** {agent_display}\n"
        f"**Sujet :** *{subject}*\n"
        f"**Tours de table :** {num_turns}\n\n"
        f"---\n"
        f"{formatted_transcript}\n"
        f"---\n"
        f"### 🏁 Synthèse et Consensus\n"
        f"Le débat ci-dessus présente les arguments confrontés de {num_agents} experts. "
        f"La solution finale doit s'appuyer sur les points de convergence identifiés."
    )
    return report


"""Outils de pile de contextes (« fil d'Ariane ») exposés à l'orchestrateur.

open_context  : met la tâche en cours de côté et démarre un fil neuf (PUSH).
close_context : referme la parenthèse et reprend la tâche précédente (POP).
list_contexts : liste les parenthèses ouvertes.

Voir core/context_stack.py pour le mécanisme (branche d'arbre + docker pause/unpause).
"""


def _session():
    """Session de chat du canal courant (web, voice:…, telegram:…)."""
    from core import channels
    from core.state import sessions
    cid = channels.current_channel.get() or "web"
    return sessions.get(cid)


def open_context(topic: str) -> str:
    """Met la tâche/conversation EN COURS de côté (parenthèse) et démarre un fil PROPRE sur
    un nouveau sujet, sans perdre l'ancien. Utilise-le quand l'utilisateur change franchement
    de sujet (« attends, mets ça de côté, on regarde autre chose »). Reprends ensuite avec
    close_context().

    Args:
        topic (str): sujet court de la parenthèse (ex. « vérif base de données »).
    Returns:
        str: confirmation (avec la profondeur de pile).
    """
    from core.state import sessions, _orch_agent, _orch_name  # noqa: F401
    import core.context_stack as cs
    from tools import dev_container
    sess = _session()
    ckey = dev_container.active_key()
    paused = dev_container.pause(ckey) if ckey else False
    frame = cs.new_frame(
        topic=topic,
        node_id=sess.active_node_id,
        active_agent=(sess.active_agent.name if sess.active_agent else _orch_name()),
        container_key=ckey,
        paused=paused,
    )
    cs.push(sess.client_id, frame)
    # Branche neuve : les prochains messages repartent à zéro (l'ancien fil reste dans l'arbre).
    sess.active_node_id = None
    sess.active_agent = _orch_agent()
    msg = f"📌 Parenthèse ouverte sur « {frame['topic']} » — tâche précédente mise de côté"
    if paused:
        msg += " (environnement de calcul gelé)"
    msg += f". Parenthèses ouvertes : {cs.depth(sess.client_id)}. Dis « on reprend » pour revenir."
    return msg


def close_context() -> str:
    """Referme la parenthèse en cours et REPREND la tâche précédente, exactement là où elle
    s'était arrêtée (historique + environnement de calcul restaurés). À utiliser quand
    l'utilisateur dit « c'est bon, on reprend / revient à ce qu'on faisait ».

    Returns:
        str: confirmation de reprise (ou message si aucune parenthèse n'est ouverte).
    """
    from core.state import sessions, swarm  # noqa: F401
    import core.context_stack as cs
    from tools import dev_container
    sess = _session()
    frame = cs.pop(sess.client_id)
    if not frame:
        return "Aucune parenthèse à refermer (pile vide) — on est déjà sur le fil principal."
    if frame.get("container_key") and frame.get("paused"):
        dev_container.unpause(frame["container_key"])
    # Restaure le fil parqué (le chemin de l'arbre repart de ce nœud) + l'agent.
    sess.active_node_id = frame.get("node_id")
    ag = swarm.agents.get(frame.get("active_agent"))
    if ag:
        sess.active_agent = ag
    topic = frame.get("topic", "(parenthèse)")
    reste = cs.depth(sess.client_id)
    suite = (cs.peek(sess.client_id) or {}).get("topic") if reste else None
    cible = f"la parenthèse « {suite} »" if suite else "la tâche principale"
    return (f"↩️ Parenthèse « {topic} » refermée — retour à {cible}. "
            f"L'historique et l'environnement de calcul sont restaurés ; continue là où on "
            f"s'était arrêté. Parenthèses encore ouvertes : {reste}.")


def list_contexts() -> str:
    """Liste les parenthèses (contextes mis de côté) actuellement ouvertes pour cette session."""
    import core.context_stack as cs
    sess = _session()
    tps = cs.topics(sess.client_id)
    if not tps:
        return "Aucune parenthèse ouverte — un seul fil en cours."
    lignes = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(tps))
    return f"Parenthèses ouvertes (de la plus ancienne à la plus récente) :\n{lignes}"

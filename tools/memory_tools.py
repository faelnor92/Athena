import json
import os
from core.memory import CoreMemory, SemanticMemory
from core import graph_memory

# Instanciation globale (singletons pour la durée du process)
core_mem = CoreMemory()
semantic_mem = SemanticMemory()


def _auto_extract_triples(text: str):
    """Extraction best-effort de relations (s, r, o) depuis un texte, via le LLM.
    Gated par GRAPH_MEMORY_AUTO. Silencieux en cas d'échec (le fait reste mémorisé)."""
    if os.getenv("GRAPH_MEMORY_AUTO", "false").lower() not in ("true", "1", "yes"):
        return
    try:
        import server
        swarm = getattr(server, "swarm", None)
        if swarm is None:
            return
        orch = getattr(swarm, "orchestrator_name", None)
        model = (swarm.agents.get(orch).model if orch and swarm.agents.get(orch)
                 else (next(iter(swarm.agents.values())).model if swarm.agents else "gpt-4o"))
        resp = swarm._complete(model, [
            {"role": "system", "content": (
                "Extrais les relations factuelles du texte sous forme de triplets "
                "(sujet, relation, objet). Réponds UNIQUEMENT par un tableau JSON "
                "[[\"sujet\",\"relation\",\"objet\"], …]. Vide [] si aucune relation claire.")},
            {"role": "user", "content": text[:1000]},
        ], tools_schema=None, allow_continuation=False, allow_fallback=True)
        raw = (resp.choices[0].message.content or "").strip()
        m = raw[raw.find("["):raw.rfind("]") + 1]
        triples = json.loads(m) if m else []
        graph_memory.add_triples(triples)
    except Exception:
        pass


def memorize_fact(key: str, value: str) -> str:
    """
    Mémorise un fait ou une préférence utilisateur essentielle et globale.
    Cet outil est parfait pour les préférences durables, les configurations,
    les noms de pièces de la maison, ou les détails généraux.

    Args:
        key (str): L'étiquette de la préférence (ex: "prenom_utilisateur", "editeur_prefere")
        value (str): L'information à retenir (ex: "Alex", "VSCode")

    Returns:
        str: Confirmation que la mémoire a été mise à jour.
    """
    core_mem.set(key, value)
    _auto_extract_triples(f"{key} : {value}")
    return f"Fait mémorisé : {key} = {value}"


def remember_relation(subject: str, relation: str, object: str) -> str:
    """
    Mémorise une RELATION entre deux entités dans la mémoire-graphe (ex. sujet="Tim",
    relation="écrit", objet="Les Larmes de l'Olympe"). Permet ensuite de retrouver tout
    ce qui est connecté à une entité avec query_graph. Complète la mémoire sémantique.
    """
    if graph_memory.add_triple(subject, relation, object):
        return f"Relation mémorisée : {subject} —[{relation}]→ {object}"
    return "Relation non enregistrée (sujet/objet manquant)."


def query_graph(entity: str) -> str:
    """
    Interroge la mémoire-graphe : renvoie tout ce qui est CONNECTÉ à une entité
    (relations directes et à un saut). Utile pour « que sais-tu sur X et ses liens ».
    entity: le nom de l'entité (personne, projet, lieu, fichier…).
    """
    triples = graph_memory.neighborhood(entity, depth=2)
    if not triples:
        return f"Aucune relation connue pour « {entity} »."
    lines = [f"- {t['s']} —[{t['r']}]→ {t['o']}" for t in triples]
    return f"Relations liées à « {entity} » ({len(lines)}) :\n" + "\n".join(lines)

def store_document(content: str, source: str = "general") -> str:
    """
    Enregistre un document, un extrait de code, un scénario de roman, ou toute information
    textuelle longue pour pouvoir la retrouver plus tard par recherche sémantique.
    
    Args:
        content (str): Le contenu textuel complet à archiver.
        source (str): La catégorie de l'information (ex: "developpement", "roman", "domotique")
        
    Returns:
        str: Message de succès avec l'identifiant du document.
    """
    doc_id = semantic_mem.store(content, source)
    return f"Document archivé avec succès dans la mémoire sémantique (ID: {doc_id})"

def search_memory(query: str) -> str:
    """
    Recherche dans les archives et documents mémorisés (mémoire sémantique)
    les extraits de textes, du code, du lore ou des notes enregistrées précédemment.
    
    Args:
        query (str): La recherche textuelle (ex: "concept de roman sur la foret")
        
    Returns:
        str: Une liste des documents les plus proches de ta recherche au format JSON.
    """
    results = semantic_mem.search(query, limit=3)
    if not results:
        return "Aucun document correspondant trouvé dans la mémoire sémantique."
    return json.dumps(results, indent=2, ensure_ascii=False)

def ingest_file(path: str, chunk_size: int = 1500, overlap: int = 200) -> str:
    """
    Lit un fichier complet (même très volumineux comme un roman) présent dans l'espace de travail,
    le segmente automatiquement en petits morceaux cohérents (chunks) et les indexe dans la
    mémoire sémantique vectorielle (RAG). Cela permet aux agents de faire des recherches
    sémantiques instantanées à l'intérieur du document.
    
    Args:
        path (str): Chemin du fichier à ingérer (ex: "mon_roman.txt" ou "notes.md").
        chunk_size (int, optional): Taille maximale de chaque segment en caractères. Par défaut 1500.
        overlap (int, optional): Chevauchement entre deux segments pour préserver le contexte. Par défaut 200.
        
    Returns:
        str: Rapport d'indexation détaillant le nombre de segments créés.
    """
    import os
    try:
        clean_path = os.path.normpath(path)
        if clean_path.startswith("..") or os.path.isabs(clean_path):
            return "Erreur: Accès interdit à ce chemin."
            
        if not os.path.exists(clean_path) or os.path.isdir(clean_path):
            return "Erreur: Fichier introuvable."
            
        with open(clean_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
            
        total_chars = len(text)
        if total_chars == 0:
            return "Erreur: Le fichier est vide."
            
        # Algorithme de chunking intelligent
        chunks = []
        start = 0
        while start < total_chars:
            end = min(start + chunk_size, total_chars)
            if end < total_chars:
                # Tenter de couper proprement sur un saut de ligne ou un point si possible
                last_space = text.rfind("\n", start + chunk_size - 100, end)
                if last_space == -1:
                    last_space = text.rfind(". ", start + chunk_size - 100, end)
                if last_space != -1:
                    end = last_space + 1
                    
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap if end < total_chars else end
            
        # Indexer dans la mémoire vectorielle
        for i, chunk_text in enumerate(chunks):
            doc_id = semantic_mem.store(
                content=chunk_text,
                source=f"{os.path.basename(clean_path)} (Partie {i+1}/{len(chunks)})"
            )
            
        return (
            f"Indexation réussie ! 🎉\n"
            f"📄 Fichier : `{os.path.basename(clean_path)}` ({total_chars} caractères)\n"
            f"🧩 Segments créés et stockés en mémoire vectorielle : {len(chunks)} chunks.\n"
            f"🔍 Les agents peuvent désormais chercher dans ce fichier en utilisant l'outil 'search_memory'."
        )
    except Exception as e:
        return f"Erreur lors de l'ingestion du fichier : {str(e)}"

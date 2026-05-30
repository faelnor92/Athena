import json
import os
import uuid
import chromadb

class CoreMemory:
    """Mémoire de type clé-valeur (JSON) pour stocker les faits et préférences globales."""
    def __init__(self, filepath=None):
        self.filepath = filepath or os.getenv("CORE_MEMORY_PATH", "core_memory.json")
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"[\033[91mErreur\033[0m] Chargement core memory: {e}")
                self.data = {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[\033[91mErreur\033[0m] Sauvegarde core memory: {e}")

    def set(self, key: str, value: str):
        self.data[key] = value
        self.save()

    def delete(self, key: str) -> bool:
        if key in self.data:
            del self.data[key]
            self.save()
            return True
        return False

    def get_as_prompt(self) -> str:
        """Formate les informations mémorisées pour les injecter dans le prompt de Jarvis."""
        if not self.data:
            return ""
        prompt = "\n=== COMPÉTENCES/FAITS APPRIS SUR L'UTILISATEUR (COUCHES DE PREFERENCES) ===\n"
        for k, v in self.data.items():
            prompt += f"- {k}: {v}\n"
        prompt += "==============================================================\n"
        return prompt


class SemanticMemory:
    """Mémoire vectorielle (ChromaDB) pour archiver et faire des recherches sémantiques."""
    def __init__(self, db_path=None):
        db_path = db_path or os.getenv("CHROMA_DB_PATH", ".chroma_db")
        # Initialise le client ChromaDB persistant avec télémétrie désactivée
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="agent_memory"
        )

    def store(self, content: str, source: str = "user") -> str:
        """Enregistre un document/concept dans la base vectorielle."""
        doc_id = str(uuid.uuid4())
        self.collection.add(
            documents=[content],
            metadatas=[{"source": source}],
            ids=[doc_id]
        )
        return doc_id

    def search(self, query: str, limit: int = 3) -> list:
        """Recherche les informations les plus proches sémantiquement."""
        results = self.collection.query(
            query_texts=[query],
            n_results=limit
        )
        formatted = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if "metadatas" in results else [{}] * len(docs)
            for doc, meta in zip(docs, metas):
                src = meta.get("source", "inconnu") if meta else "inconnu"
                formatted.append(f"[{src}]: {doc}")
        return formatted

import json
import logging
import os
import time
import uuid
import chromadb

# ChromaDB 0.5.x logge « Failed to send telemetry event … capture() takes 1
# positional argument but 3 were given » à chaque opération : bug de sa télémétrie
# posthog, sans impact (la télémétrie est déjà coupée plus bas). On fait taire ce
# logger précis pour ne pas polluer les logs.
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

class CoreMemory:
    """Mémoire clé-valeur (JSON) des faits/préférences — PAR UTILISATEUR.

    Le fichier réel est suffixé par l'utilisateur courant (core_memory_<user>.json) ;
    `data` reflète toujours l'utilisateur courant (résolu à chaque accès)."""
    def __init__(self, filepath=None):
        import threading
        self._base = filepath or os.getenv("CORE_MEMORY_PATH", "core_memory.json")
        self._cache = {}      # user -> dict
        self._loaded = set()
        self._lock = threading.Lock()

    def _key(self) -> str:
        from core.user_config import current_user_key
        return current_user_key()

    def _path(self) -> str:
        from core.user_config import user_slug
        root, ext = os.path.splitext(self._base)
        return f"{root}_{user_slug()}{ext or '.json'}"

    @property
    def data(self) -> dict:
        u = self._key()
        if u not in self._loaded:
            self.load()
        return self._cache.setdefault(u, {})

    def load(self):
        u = self._key()
        d = {}
        p = self._path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                print(f"[\033[91mErreur\033[0m] Chargement core memory: {e}")
                d = {}
        with self._lock:
            self._cache[u] = d if isinstance(d, dict) else {}
            self._loaded.add(u)

    def save(self):
        u = self._key()
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump(self._cache.get(u, {}), f, indent=4, ensure_ascii=False)
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
        """Formate les informations mémorisées pour les injecter dans le prompt de Athena."""
        if not self.data:
            return ""
        prompt = "\n=== COMPÉTENCES/FAITS APPRIS SUR L'UTILISATEUR (COUCHES DE PREFERENCES) ===\n"
        for k, v in self.data.items():
            prompt += f"- {k}: {v}\n"
        prompt += "==============================================================\n"
        return prompt


class SemanticMemory:
    """Mémoire vectorielle (ChromaDB) PAR UTILISATEUR : chaque compte a sa propre
    collection (um_<user>) → les documents d'un utilisateur ne sont pas cherchables
    par un autre. Résolue à chaque accès via core.user_config."""
    def __init__(self, db_path=None):
        db_path = db_path or os.getenv("CHROMA_DB_PATH", ".chroma_db")
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
        self._collections = {}  # nom -> collection

    @staticmethod
    def collection_name(user: str = None) -> str:
        import re
        from core.user_config import user_slug
        safe = re.sub(r"[^a-zA-Z0-9]", "_", user_slug(user))[:55].strip("_") or "local"
        return f"um_{safe}"

    def _coll(self):
        name = self.collection_name()
        coll = self._collections.get(name)
        if coll is None:
            coll = self.client.get_or_create_collection(name=name)
            self._collections[name] = coll
        return coll

    def drop_user(self, user: str) -> bool:
        """Supprime entièrement la collection d'un utilisateur (suppression de compte)."""
        name = self.collection_name(user)
        try:
            self.client.delete_collection(name=name)
            self._collections.pop(name, None)
            return True
        except Exception:
            return False

    def store(self, content: str, source: str = "user") -> str:
        """Enregistre un document/concept dans la base vectorielle."""
        doc_id = str(uuid.uuid4())
        self._coll().add(
            documents=[content],
            metadatas=[{"source": source, "ts": time.time()}],
            ids=[doc_id]
        )
        return doc_id

    def prune_source(self, source: str, keep: int = 50) -> int:
        """Consolidation anti-bloat : ne conserve que les `keep` documents les plus
        récents d'une source donnée (ex: 'retour_experience'). Renvoie le nb supprimé."""
        try:
            res = self._coll().get(where={"source": source}, include=["metadatas"])
        except Exception:
            return 0
        ids = res.get("ids", []) or []
        metas = res.get("metadatas", []) or []
        if len(ids) <= keep:
            return 0
        items = sorted(zip(ids, metas), key=lambda x: (x[1] or {}).get("ts", 0))
        to_del = [i for i, _ in items[:len(ids) - keep]]
        if to_del:
            try:
                self._coll().delete(ids=to_del)
            except Exception:
                return 0
        return len(to_del)

    def list_documents(self, limit: int = 200) -> list:
        """Liste les documents indexés : [{id, source, preview}]."""
        try:
            res = self._coll().get(limit=limit, include=["documents", "metadatas"])
        except Exception:
            return []
        ids = res.get("ids", []) or []
        docs = res.get("documents", []) or []
        metas = res.get("metadatas", []) or []
        out = []
        for i, doc_id in enumerate(ids):
            doc = docs[i] if i < len(docs) else ""
            meta = metas[i] if i < len(metas) else {}
            out.append({
                "id": doc_id,
                "source": (meta or {}).get("source", "inconnu"),
                "preview": (doc or "")[:160],
                "length": len(doc or ""),
            })
        return out

    def count(self) -> int:
        try:
            return self._coll().count()
        except Exception:
            return 0

    def delete(self, doc_id: str) -> bool:
        try:
            self._coll().delete(ids=[doc_id])
            return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 3) -> list:
        """Recherche les informations les plus proches sémantiquement."""
        results = self._coll().query(
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

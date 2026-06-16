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


# --- Embeddings : LOCAL par défaut (intégré ChromaDB, marche partout), ou ENDPOINT optionnel ---
# Réglages (.env / UI) :
#   EMBEDDING_PROVIDER = "local" (défaut) | "http"
#   EMBEDDING_MODEL    = ex. "bge-m3" ou "qwen3-embedding" (si http)
#   EMBEDDING_API_BASE = défaut CUSTOM_LLM_API_BASE ; EMBEDDING_API_KEY = défaut CUSTOM_LLM_API_KEY
# Le défaut LOCAL (all-MiniLM intégré) garantit que l'app marche sans endpoint pour ceux qui la
# téléchargent ; ceux qui ont un endpoint multilingue (bge-m3…) gagnent en qualité (FR).
class _HttpEmbeddingFunction:
    """Fonction d'embedding ChromaDB qui appelle un endpoint OpenAI-compatible /v1/embeddings.
    Callable : (input: list[str]) -> list[list[float]]. Sans dépendance (requests)."""
    def __init__(self, base: str, key: str, model: str):
        self._base = base.rstrip("/")
        self._key = key
        self._model = model

    def name(self) -> str:                  # requis par certaines versions de ChromaDB
        return f"http_{self._model}"

    def _embed(self, texts):
        import requests
        texts = [str(t) for t in (texts or [])]
        if not texts:
            return []
        url = self._base + "/embeddings"
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        r = requests.post(url, json={"model": self._model, "input": texts},
                          headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        # On respecte l'ordre via l'index si fourni (certains serveurs ne garantissent pas l'ordre).
        if data and isinstance(data[0], dict) and "index" in data[0]:
            data = sorted(data, key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]

    # ChromaDB natif appelle __call__ ; certaines versions/intégrations attendent l'interface
    # « LangChain » (embed_documents / embed_query). On expose les trois → compatible partout.
    def __call__(self, input):
        return self._embed(input)

    def embed_documents(self, texts):
        return self._embed(texts)

    def embed_query(self, text):
        out = self._embed([text])
        return out[0] if out else []


def _embedding_config():
    prov = (os.getenv("EMBEDDING_PROVIDER", "local") or "local").strip().lower()
    if prov != "http":
        return None  # défaut local (all-MiniLM intégré ChromaDB)
    model = (os.getenv("EMBEDDING_MODEL", "") or "").strip() or "bge-m3"
    base = (os.getenv("EMBEDDING_API_BASE", "") or os.getenv("CUSTOM_LLM_API_BASE", "") or "").strip()
    key = (os.getenv("EMBEDDING_API_KEY", "") or os.getenv("CUSTOM_LLM_API_KEY", "") or "").strip()
    if not base:
        return None  # http demandé mais pas d'URL → repli local
    return {"model": model, "base": base, "key": key}


def _embedding_function():
    cfg = _embedding_config()
    if not cfg:
        return None
    try:
        return _HttpEmbeddingFunction(cfg["base"], cfg["key"], cfg["model"])
    except Exception:
        return None


def _embedding_tag() -> str:
    """Suffixe de collection lié au moteur d'embedding (les dimensions diffèrent → on ISOLE les
    collections par moteur pour éviter tout mélange/crash de dimensions)."""
    cfg = _embedding_config()
    if not cfg:
        return ""  # local → pas de suffixe (rétro-compat avec les collections existantes)
    import re
    return "_" + re.sub(r"[^a-zA-Z0-9]", "", cfg["model"])[:20]

class CoreMemory:
    """Mémoire clé-valeur (JSON) des faits/préférences — PAR UTILISATEUR.

    Le fichier réel est suffixé par l'utilisateur courant (core_memory_<user>.json) ;
    `data` reflète toujours l'utilisateur courant (résolu à chaque accès)."""
    def __init__(self, filepath=None):
        import threading
        self._base = filepath or os.getenv("CORE_MEMORY_PATH", "core_memory.json")
        self._cache = {}      # user -> dict
        self._loaded = set()
        self._mtimes = {}     # user -> mtime du fichier au dernier chargement
        self._lock = threading.Lock()

    def _key(self) -> str:
        from core.user_config import current_user_key
        return current_user_key()

    def _path(self) -> str:
        from core.user_config import user_slug
        root, ext = os.path.splitext(self._base)
        return f"{root}_{user_slug()}{ext or '.json'}"

    def _disk_mtime(self) -> float:
        try:
            return os.path.getmtime(self._path())
        except OSError:
            return 0.0

    @property
    def data(self) -> dict:
        u = self._key()
        # Multi-worker : si le fichier a été modifié par un autre process depuis notre
        # dernier chargement (mtime plus récent), on recharge pour ne pas servir du périmé.
        if u not in self._loaded or self._disk_mtime() > self._mtimes.get(u, 0):
            self.load()
        return self._cache.setdefault(u, {})

    def load(self):
        u = self._key()
        d = {}
        p = self._path()
        mtime = 0.0
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                mtime = os.path.getmtime(p)
            except Exception as e:
                print(f"[\033[91mErreur\033[0m] Chargement core memory: {e}")
                d = {}
        with self._lock:
            self._cache[u] = d if isinstance(d, dict) else {}
            self._loaded.add(u)
            self._mtimes[u] = mtime

    def save(self):
        u = self._key()
        try:
            p = self._path()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self._cache.get(u, {}), f, indent=4, ensure_ascii=False)
            # Mémorise le mtime de notre propre écriture (évite un rechargement inutile).
            try:
                self._mtimes[u] = os.path.getmtime(p)
            except OSError:
                pass
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
        settings = chromadb.Settings(anonymized_telemetry=False)
        # Multi-worker : si CHROMA_SERVER_HOST est défini, tous les workers parlent au
        # MÊME serveur Chroma (écritures concurrentes sûres). Sinon, base locale embarquée
        # (PersistentClient) — parfait en mono-process.
        host = os.getenv("CHROMA_SERVER_HOST", "").strip()
        if host:
            port = int(os.getenv("CHROMA_SERVER_PORT", "8001") or 8001)
            self.client = chromadb.HttpClient(host=host, port=port, settings=settings)
        else:
            db_path = db_path or os.getenv("CHROMA_DB_PATH", ".chroma_db")
            self.client = chromadb.PersistentClient(path=db_path, settings=settings)
        self._collections = {}  # nom -> collection

    @staticmethod
    def collection_name(user: str = None) -> str:
        import re
        from core.user_config import user_slug
        safe = re.sub(r"[^a-zA-Z0-9]", "_", user_slug(user))[:55].strip("_") or "local"
        # Suffixe par moteur d'embedding : isole les collections (dimensions différentes).
        return f"um_{safe}{_embedding_tag()}"

    @staticmethod
    def _local_collection_name(user: str = None) -> str:
        """Nom de collection pour l'embedding LOCAL par défaut (sans suffixe moteur)."""
        import re
        from core.user_config import user_slug
        safe = re.sub(r"[^a-zA-Z0-9]", "_", user_slug(user))[:55].strip("_") or "local"
        return f"um_{safe}"

    def _coll(self):
        name = self.collection_name()
        coll = self._collections.get(name)
        if coll is None:
            ef = _embedding_function()  # None = défaut local (all-MiniLM intégré)
            if not ef:
                coll = self.client.get_or_create_collection(name=name)
            else:
                try:
                    coll = self.client.get_or_create_collection(name=name, embedding_function=ef)
                except Exception as e:
                    # Endpoint d'embedding injoignable/incompatible → repli sur le défaut LOCAL
                    # (collection séparée) pour ne JAMAIS casser la mémoire.
                    logging.warning(f"[memory] embedding endpoint KO ({e}) → repli local.")
                    name = self._local_collection_name()
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
        # Robustesse : le LLM peut passer un nombre (ou None) comme contenu → chromadb fait
        # len() sur le document et lèverait « object of type 'int' has no len() ». On force
        # une chaîne (et idem pour la source, métadonnée).
        content = "" if content is None else str(content)
        source = "user" if source is None else str(source)
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

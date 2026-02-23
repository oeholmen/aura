import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Memory.Vector")


# ---------------------------------------------------------------------------
# Try to import ChromaDB — if missing, set a flag for sovereign fallback
# ---------------------------------------------------------------------------
_CHROMA_AVAILABLE = False
_OllamaEF = None
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from chromadb.utils.embedding_functions import OllamaEmbeddingFunction as _OllamaEF
    _CHROMA_AVAILABLE = True
except ImportError:
    logger.warning("chromadb not installed — VectorMemory will run in Sovereign Fallback mode (JSON).")


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class VectorMemory:
    """Semantic vector store backed by ChromaDB + Ollama embeddings.
    Fails over to local JSON persistence if ChromaDB is unavailable.
    """

    def __init__(
        self,
        collection_name: str = "aura_memories",
        persist_directory: Optional[str] = None,
        ollama_client: Any = None,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: Optional[str] = None,
    ):
        from core.config import config
        if not ollama_model:
            ollama_model = getattr(config.llm, "embedding_model", config.llm.fast_model)
        self.collection_name = collection_name
        self.ollama_client = ollama_client
        self._fallback_mode = False

        if persist_directory is None:
            from core.common.paths import DATA_DIR
            persist_directory = str(DATA_DIR / "vector_store")
        
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.fallback_file = self.persist_directory / f"{collection_name}_fallback.json"
        
        from core.utils.core_db import get_core_db
        self.db = get_core_db()

        if _CHROMA_AVAILABLE:
            try:
                self._client = chromadb.PersistentClient(
                    path=str(self.persist_directory),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._embed_fn = _OllamaEF(
                    url=ollama_base_url,
                    model_name=ollama_model,
                )
                self._collection = self._client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=self._embed_fn,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(
                    f"VectorMemory ONLINE — collection '{collection_name}' "
                    f"({self._collection.count()} vectors), persist={persist_directory}"
                )
            except Exception as e:
                logger.error("ChromaDB init failed, falling back to Sovereign Persistence: %s", e)
                self._fallback_mode = True
        else:
            self._fallback_mode = True

        if self._fallback_mode:
            self._store = self._load_fallback()
            logger.info("VectorMemory: Sovereign Fallback Active (records: %d)", len(self._store))

    def _load_fallback(self) -> List[Dict[str, Any]]:
        """Load memories from local SQLite DB with legacy JSON migration."""
        memories = []
        conn = self.db.get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, content, metadata FROM vector_fallback WHERE collection = ?", 
                (self.collection_name,)
            )
            for row in cursor.fetchall():
                memories.append({
                    "id": row[0],
                    "content": row[1],
                    "metadata": json.loads(row[2])
                })
        except Exception as e:
            logger.error("Failed to load fallback memory from DB: %s", e)
        finally:
            conn.close()

        # Phase 8 Migration: Check if legacy JSON file exists
        if not memories and self.fallback_file.exists():
            try:
                logger.info("📦 Migrating '%s' memories from JSON to SQLite...", self.collection_name)
                with open(self.fallback_file, 'r') as f:
                    legacy_store = json.load(f)
                
                # Bulk insert for O(1) transaction overhead instead of O(N) connections
                self._upsert_fallback_batch(legacy_store)
                return legacy_store
            except Exception as e:
                logger.error("Failed to migrate legacy memory file: %s", e)

        return memories

    def _upsert_fallback_batch(self, memories: List[Dict[str, Any]]):
        """Persist a batch of entries to SQLite fallback efficiently."""
        if not memories:
            return
        conn = self.db.get_connection()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO vector_fallback (id, collection, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
                    [(m["id"], self.collection_name, m["content"], json.dumps(m["metadata"]), m["metadata"].get("timestamp", time.time())) for m in memories]
                )
        except Exception as e:
            logger.error("Failed to batch upsert fallback memories to DB: %s", e)
        finally:
            conn.close()

    def _upsert_fallback(self, doc_id: str, content: str, metadata: Dict[str, Any]):
        """Persist a single entry to SQLite fallback."""
        conn = self.db.get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO vector_fallback (id, collection, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, self.collection_name, content, json.dumps(metadata), metadata.get("timestamp", time.time()))
                )
        except Exception as e:
            logger.error("Failed to upsert fallback memory to DB: %s", e)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict] = None,
        _id: Optional[str] = None,
    ) -> bool:
        """Persist a text memory with optional metadata and emotional state."""
        if not content:
            return False

        doc_id = _id or hashlib.sha256(content.encode()).hexdigest()[:16] + uuid.uuid4().hex[:8]
        meta = metadata or {}
        meta.setdefault("timestamp", time.time())
        
        # ── Pillar 4: Emotional Salience (Stamping) ──
        try:
            from core.container import ServiceContainer
            affect = ServiceContainer.get("affect_engine")
            if affect:
                # Synchronous-compatible access if possible, or skip for now
                # H-28 FIX: Use safe getattr to avoid AttributeError on V2 engine
                markers = getattr(affect, 'markers', None)
                if markers and hasattr(markers, 'get_wheel'):
                    w = markers.get_wheel()["primary"]
                    pos = w.get("joy", 0) + w.get("trust", 0)
                    neg = w.get("fear", 0) + w.get("sadness", 0) + w.get("anger", 0)
                    meta["valence"] = float(pos - neg)
                    meta["arousal"] = float(max(w.values()) if w else 0.0)
        except: pass

        if self._fallback_mode:
            self._store.append({"id": doc_id, "content": content, "metadata": meta})
            self._upsert_fallback(doc_id, content, meta)
            logger.debug("VectorMemory: Saved to fallback: %s...", content[:60])
            return True
        
        # Ensure last_accessed is set
        meta.setdefault("last_accessed", time.time())

        try:
            self._collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[meta],
            )
            logger.debug("VectorMemory.add_memory: %s...", content[:60])
            return True
        except Exception as e:
            logger.error("VectorMemory.add_memory failed: %s", e)
            return False

    def search_similar(self, query: str, limit: int = 5, **kwargs) -> List[Dict]:
        """Return semantically similar memories, biased by Emotional Salience."""
        if not query:
            return []

        if self._fallback_mode:
            # Simple keyword search fallback for degraded mode
            query_low = query.lower()
            results = [
                m for m in self._store 
                if query_low in m['content'].lower() or any(query_low in str(v).lower() for v in m['metadata'].values())
            ]
            # Sort by timestamp (newest first) since we don't have embeddings in fallback
            results.sort(key=lambda x: x['metadata'].get('timestamp', 0), reverse=True)
            return results[:limit]

        try:
            # Fetch more than we need for re-ranking
            internal_limit = limit * 3
            results = self._collection.query(
                query_texts=[query],
                n_results=min(internal_limit, max(self._collection.count(), 1)),
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]
            
            # --- Pillar 4: Emotional Salience (Re-ranking) ---
            from core.container import ServiceContainer
            affect = ServiceContainer.get("affect_engine")
            current_valence = 0.0
            if affect:
                # H-28 FIX: Use safe getattr to avoid AttributeError on V2 engine
                markers = getattr(affect, 'markers', None)
                if markers and hasattr(markers, 'get_wheel'):
                    w = markers.get_wheel()["primary"]
                    current_valence = float((w.get("joy", 0) + w.get("trust", 0)) - (w.get("fear", 0) + w.get("sadness", 0) + w.get("anger", 0)))

            scored_results = []
            for i in range(len(docs)):
                doc_meta = metas[i] if i < len(metas) else {}
                doc_valence = doc_meta.get("valence", 0.0)
                
                # Semantic distance (lower is better in cosine space for chromadb)
                semantic_score = 1.0 - (dists[i] if i < len(dists) else 0.5)
                
                # Emotional alignment (1.0 = same mood, 0.0 = opposite)
                # Valence is roughly [-1, 1]
                emotional_alignment = 1.0 - (abs(current_valence - doc_valence) / 2.0)
                
                # Final weighted score
                final_score = (semantic_score * 0.7) + (emotional_alignment * 0.3)
                
                scored_results.append({
                    "id": ids[i],
                    "content": docs[i],
                    "metadata": doc_meta,
                    "score": final_score,
                    "distance": dists[i] if i < len(dists) else None,
                })

            # Sort by final score descending
            scored_results.sort(key=lambda x: x["score"], reverse=True)
            
            # --- Update last_accessed for the top results ---
            top_ids = [r["id"] for r in scored_results[:limit]]
            if not self._fallback_mode and top_ids:
                try:
                    # ChromaDB doesn't allow bulk metadata update by ID in the same way as SQL
                    # We have to fetch and update or use a loop for small sets
                    for tid in top_ids:
                        idx = ids.index(tid)
                        m = metas[idx]
                        m["last_accessed"] = time.time()
                        self._collection.update(ids=[tid], metadatas=[m])
                except Exception as e:
                    logger.debug("Failed to update last_accessed: %s", e)
            elif self._fallback_mode:
                for tid in top_ids:
                    for m in self._store:
                        if m["id"] == tid:
                            m["metadata"]["last_accessed"] = time.time()
                            self._upsert_fallback(m["id"], m["content"], m["metadata"])

            return scored_results[:limit]

        except Exception as e:
            logger.error("VectorMemory.search_similar failed: %s", e)
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Return collection statistics."""
        if self._fallback_mode:
            return {"total_vectors": len(self._store), "engine": "sovereign_fallback", "status": "degraded"}
        try:
            count = self._collection.count()
            return {"total_vectors": count, "engine": "chromadb", "status": "active"}
        except Exception:
            return {"total_vectors": -1, "engine": "chromadb", "status": "error"}

    # ------------------------------------------------------------------
    # Aliases — compatibility
    # ------------------------------------------------------------------

    def add(self, content: str, metadata: Optional[Dict] = None, **kwargs) -> bool:
        return self.add_memory(content, metadata=metadata, _id=kwargs.get("_id"))

    def search(self, query: str = "", limit: int = 5, k: int = 0, **kwargs) -> List[Dict]:
        effective_limit = k if k > 0 else limit
        return self.search_similar(query or "", limit=effective_limit)

    def clear(self):
        """Delete all vectors in the collection."""
        if self._fallback_mode:
            self._store.clear()
            conn = self.db.get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM vector_fallback WHERE collection = ?", (self.collection_name,))
            finally:
                conn.close()
            return
        try:
            ids = self._collection.get()["ids"]
            if ids:
                self._collection.delete(ids=ids)
            logger.info("VectorMemory: cleared collection '%s'", self.collection_name)
        except Exception as e:
            logger.error("VectorMemory.clear failed: %s", e)

    def prune_low_salience(self, threshold_days: int = 30, min_salience: float = -0.2) -> int:
        """Removes memories that are old, unaccessed, and have low emotional salience.
        
        This implements 'Strategic Forgetting'.
        """
        logger.info("🧹 Pruning low-salience memories (threshold=%s days)...", threshold_days)
        now = time.time()
        expiry_seconds = threshold_days * 86400
        ids_to_prune = []

        if self._fallback_mode:
            initial_count = len(self._store)
            self._store = [
                m for m in self._store
                if not (
                    (now - m["metadata"].get("last_accessed", m["metadata"].get("timestamp", 0)) > expiry_seconds) and
                    (m["metadata"].get("valence", 0.0) < min_salience)
                )
            ]
            final_count = len(self._store)
            if initial_count != final_count:
                # Synchronize DB with the remaining store for this collection
                conn = self.db.get_connection()
                try:
                    with conn:
                        conn.execute("DELETE FROM vector_fallback WHERE collection = ?", (self.collection_name,))
                        if self._store:
                            conn.executemany(
                                "INSERT INTO vector_fallback (id, collection, content, metadata, timestamp) VALUES (?, ?, ?, ?, ?)",
                                [(m["id"], self.collection_name, m["content"], json.dumps(m["metadata"]), m["metadata"].get("timestamp", 0)) for m in self._store]
                            )
                finally:
                    conn.close()
            return initial_count - final_count

        try:
            # We can't easily query by metadata logic 'AND' in all ChromaDB versions
            # So we fetch all metadatas and filter client-side (safe for < 100k records)
            results = self._collection.get(include=["metadatas"])
            ids = results.get("ids", [])
            metas = results.get("metadatas", [])

            for _id, meta in zip(ids, metas):
                last_access = meta.get("last_accessed", meta.get("timestamp", 0))
                valence = meta.get("valence", 0.0)
                
                # Expiry condition: Old unaccessed AND low salience
                if (now - last_access > expiry_seconds) and (valence < min_salience):
                    ids_to_prune.append(_id)

            if ids_to_prune:
                # Delete in chunks to avoid overwhelming the DB
                for i in range(0, len(ids_to_prune), 100):
                    self._collection.delete(ids=ids_to_prune[i:i+100])
                logger.info("✅ Pruned %s low-salience vectors.", len(ids_to_prune))
            
            return len(ids_to_prune)
        except Exception as e:
            logger.error("VectorMemory.prune_low_salience failed: %s", e)
            return 0

# Alias for compatibility
VectorStorage = VectorMemory

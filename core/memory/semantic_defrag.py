"""
core/memory/semantic_defrag.py
──────────────────────────────
Implements "Semantic Sleep" for vector memory consolidation.
Finds dense clusters of similar memories and merges them into unified concepts.
"""
import logging
import time
import asyncio
from typing import List, Dict, Any
from core.container import ServiceContainer

logger = logging.getLogger("Aura.Memory.Defrag")

class SemanticDefragmenter:
    def __init__(self, collection_name: str = "aura_memories"):
        self.collection_name = collection_name

    async def run_defrag_cycle(self):
        """
        Scans the vector database, finds clusters, and consolidates them.
        """
        logger.info("🌙 SEMANTIC SLEEP: Starting defragmentation cycle for '%s'...", self.collection_name)
        
        memory = ServiceContainer.get("vector_memory")
        if not memory or memory._fallback_mode:
            logger.warning("Semantic Defrag: Vector memory unavailable or in fallback mode. Skipping.")
            return

        # 1. Fetch a sample of memories (ChromaDB doesn't support 'clustering' directly easily)
        # We'll fetch the most recent bits and look for duplicates/overlaps
        try:
            results = memory._collection.get(include=["documents", "metadatas"])
            ids = results.get("ids", [])
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            
            if len(ids) < 10:
                logger.info("Semantic Defrag: Not enough memories to justify defrag.")
                return

            # 2. Find high-similarity clusters
            # For simplicity in this implementation, we'll look for semantic duplicates
            # and close overlaps. A real implementation would use K-Means or DBSCAN.
            
            to_merge = [] # List of (doc_ids, shared_topic)
            
            # This is a naive O(N^2) comparison for demonstration of the concept
            # In production, we'd use the vector engine to find clusters.
            checked = set()
            for i in range(len(ids)):
                if ids[i] in checked: continue
                
                # Find very similar docs to this one
                similars = memory.search_similar(docs[i], limit=5)
                cluster = [ids[i]]
                cluster_docs = [docs[i]]
                
                for sim in similars:
                    if sim["id"] == ids[i]: continue
                    # threshold: distance < 0.1 (very similar in cosine space)
                    if sim.get("distance", 1.0) < 0.1:
                        cluster.append(sim["id"])
                        cluster_docs.append(sim["content"])
                        checked.add(sim["id"])
                
                if len(cluster) > 2:
                    to_merge.append((cluster, cluster_docs))
                
                checked.add(ids[i])

            if not to_merge:
                logger.info("Semantic Defrag: No fragmentation clusters detected.")
                return

            # 3. Consolidate via LLM
            llm = ServiceContainer.get("ollama_client")
            for cluster_ids, cluster_docs in to_merge:
                logger.info("🧠 Consolidating cluster of %s memories...", len(cluster_ids))
                
                context_block = "\n".join([f"- {d}" for d in cluster_docs])
                sum_prompt = (
                    "Synthesize the following fragmented memories into a single, dense, factual consolidated concept. "
                    "Preserve all unique details but remove internal redundancies. Keep it under 100 words."
                )
                
                full_req = f"{sum_prompt}\n\nMEMORIES:\n{context_block}"
                response = await llm.generate(full_req, system="Memory Consolidation Subsystem.")
                consolidated_content = response.get("response", "").strip()
                
                if consolidated_content:
                    # Add new consolidated memory
                    meta = {
                        "type": "consolidated_concept",
                        "original_count": len(cluster_ids),
                        "timestamp": time.time(),
                        "last_accessed": time.time(),
                        "valence": sum(m.get("valence", 0) for m in metas if m.get("id") in cluster_ids) / len(cluster_ids)
                    }
                    memory.add_memory(consolidated_content, metadata=meta)
                    
                    # Delete fragmented originals
                    memory._collection.delete(ids=cluster_ids)
                    logger.info("✅ Successfully merged %s memories into a single Concept.", len(cluster_ids))

        except Exception as e:
            logger.error("Semantic Defrag failed: %s", e)

async def start_defrag_scheduler():
    """Simple background loop that runs defrag periodically (e.g., every 6 hours)."""
    defragger = SemanticDefragmenter()
    while True:
        await asyncio.sleep(6 * 3600) # 6 hours
        await defragger.run_defrag_cycle()

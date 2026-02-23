
"""core/managers/memory_manager.py

Unified facade for Aura's multi-layered memory systems.
Implements pruning, consolidation, and retrieval-confidence gating.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from core.container import ServiceContainer

logger = logging.getLogger("Aura.MemoryManager")

class MemoryManager:
    """Unified access point for episodic, semantic, and vector memory."""

    def __init__(self, orchestrator=None, sqlite_memory=None, vector_memory=None):
        self.orch = orchestrator
        self.sqlite_memory = sqlite_memory
        self.vector_memory = vector_memory
        self.last_consolidation = time.time()
        self.consolidation_interval = 86400  # 24 hours

    async def store(self, content: Any, importance: float = 0.5, tags: List[str] = None):
        """Stores content across appropriate memory layers."""
        try:
            # 1. Episodic (Short-term context)
            episodic = ServiceContainer.get("episodic_memory", default=None)
            if episodic:
                await episodic.add(content, importance=importance)
            
            # 2. Vector (Long-term semantic)
            vector = ServiceContainer.get("vector_memory", default=None)
            if vector and importance > 0.7:  # Only index high-importance items immediately
                await vector.index(content, metadata={"tags": tags or []})
        except Exception as e:
            logger.error("Failed to store memory: %s", e)

    async def retrieve(self, query: str, limit: int = 5, min_confidence: float = 0.6) -> List[Any]:
        """Retrieves and filters memories based on confidence/relevance."""
        results = []
        try:
            vector = ServiceContainer.get("vector_memory", default=None)
            if vector:
                raw_results = await vector.search(query, limit=limit)
                # Apply confidence gating
                results = [r for r in raw_results if r.get("score", 0) >= min_confidence]
        except Exception as e:
            logger.error("Failed to retrieve memory: %s", e)
        return results

    def search_similar(self, query: str, limit: int = 5, **kwargs) -> List[Dict]:
        """Sync delegation for legacy components (Theory of Mind, Context Manager)."""
        try:
            vector = ServiceContainer.get("vector_memory", default=None)
            if vector and hasattr(vector, 'search_similar'):
                return vector.search_similar(query, limit=limit, **kwargs)
        except Exception as e:
            logger.error("search_similar delegation failed: %s", e)
        return []

    async def run_maintenance(self):
        """Trigger pruning and consolidation if the interval has passed."""
        now = time.time()
        if now - self.last_consolidation > self.consolidation_interval:
            logger.info("🕒 Initiating scheduled memory consolidation...")
            await self.consolidate_memories()
            self.last_consolidation = now

    async def consolidate_memories(self):
        """Moves episodic memories into long-term storage and prunes low-importance data."""
        try:
            # Integration with ContextPruner if available
            pruner = ServiceContainer.get("context_pruner", default=None)
            if pruner:
                await pruner.prune_stale_context()
            
            # Summarize episodic bursts
            episodic = ServiceContainer.get("episodic_memory", default=None)
            if episodic:
                await episodic.consolidate()
        except Exception as e:
            logger.error("Memory consolidation failed: %s", e)

    def get_status(self) -> Dict[str, Any]:
        return {
            "last_consolidation": self.last_consolidation,
            "next_consolidation": self.last_consolidation + self.consolidation_interval,
            "status": "idle" if time.time() - self.last_consolidation < self.consolidation_interval else "maintenance_due"
        }

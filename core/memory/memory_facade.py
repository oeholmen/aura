"""Aura Memory Facade — Unified Interface for Cognitive Persistence

Unifies the 5 disparate memory systems:
1. Episodic (Autobiographical events)
2. Semantic (Timeless facts/beliefs)
3. Vector (Similarity search)
4. Knowledge Ledger (Low-level trace)
5. Knowledge Graph (Relational beliefs)
"""
import logging
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("Aura.MemoryFacade")

class MemoryFacade:
    def __init__(self, 
                 episodic=None, 
                 semantic=None, 
                 vector=None, 
                 ledger=None, 
                 graph=None):
        self._episodic = episodic
        self._semantic = semantic
        self._vector = vector
        self._ledger = ledger
        self._graph = graph
        
    @property
    def episodic(self): return self._episodic
    @property
    def vector(self): return self._vector
    @property
    def semantic(self): return self._semantic
    @property
    def ledger(self): return self._ledger
    @property
    def graph(self): return self._graph

    async def commit_interaction(self, 
                                 context: str, 
                                 action: str, 
                                 outcome: str, 
                                 success: bool,
                                 emotional_valence: float = 0.0,
                                 importance: float = 0.5):
        """Unified commit for an interaction across all relevant systems."""
        timestamp = datetime.now()
        
        # 1. Record as Episode
        episode_id = None
        if self.episodic:
            try:
                episode_id = await self.episodic.record_episode_async(
                    context=context,
                    action=action,
                    outcome=outcome,
                    success=success,
                    emotional_valence=emotional_valence,
                    importance=importance
                )
            except Exception as e:
                logger.error("Failed to record episode: %s", e)

        # 2. Vector Indexing (for similarity and long-term search)
        if self._vector:
            try:
                text = f"{context} | {action} | {outcome}"
                # VectorMemory uses sync add_memory
                await asyncio.to_thread(self._vector.add_memory, text, metadata={
                    "type": "interaction",
                    "success": success,
                    "episode_id": episode_id
                })
            except Exception as e:
                logger.warning("Vector indexing failed: %s", e)
                
        # 3. Log to Knowledge Ledger (micro-trace)
        if self._ledger and hasattr(self._ledger, 'log_interaction'):
            try:
                self._ledger.log_interaction(action, outcome, success)
            except Exception as e:
                logger.debug("Ledger log failed: %s", e)

    async def retrieve_unified_context(self, query: str, limit: int = 5) -> str:
        """Fetch blended context from all systems."""
        results = []
        
        # Pull from Vector (Similarity)
        if self.vector:
            # VectorMemory uses sync search_similar
            similar = await asyncio.to_thread(self.vector.search_similar, query, limit=limit)
            if similar:
                results.append("## Semantic Anchors")
                for s in similar:
                    results.append(f"- {s.get('text', '')}")

        # Pull from Episodic (Autobiographical)
        if self.episodic:
            recent = await self.episodic.recall_recent_async(limit=3)
            if recent:
                results.append("## Recent Experience")
                for r in recent:
                    # check for context and action attributes (Episode dataclass in core/memory/episodic_memory.py)
                    ctx = getattr(r, 'context', 'Unknown')
                    act = getattr(r, 'action', 'Unknown')
                    results.append(f"- {ctx} -> {act} ({'Success' if r.success else 'Failure'})")

        return "\n".join(results)

    def store_experience(self, description: str, importance: float = 0.5):
        """Standard interaction record for cognitive integration."""
        if self.episodic:
            # We wrap it in an async task since this is called from sync context usually
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.commit_interaction(
                    context="Direct Memory Storage",
                    action="narrative_record",
                    outcome=description,
                    success=True,
                    importance=importance
                ))
            except RuntimeError:
                # No running loop, just skip for now or use background thread
                pass
        else:
            logger.debug("MemoryFacade: Episodic system not available for store_experience")



    def search_memories(self, query: str, top_k: int = 3) -> List[Dict]:
        """Compatibility method: delegated to SemanticMemory."""
        if self._semantic and hasattr(self._semantic, 'search_memories'):
            return self._semantic.search_memories(query, top_k=top_k)
        return []

    async def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None):
        """Proxy to vector memory for direct narrative storage (v6.0 compatibility)"""
        if self._vector:
            try:
                await asyncio.to_thread(self._vector.add_memory, text, metadata=metadata)
            except Exception as e:
                logger.warning("Vector add_memory via facade failed: %s", e)
        else:
            logger.debug("MemoryFacade: Vector system not available for add_memory")

    def get_status(self) -> Dict[str, Any]:
        """Aggregate health across systems."""
        return {
            "episodic": self.episodic is not None,
            "semantic": self.semantic is not None,
            "vector": self.vector is not None,
            "ledger": self.ledger is not None,
            "graph": self.graph is not None,
        }

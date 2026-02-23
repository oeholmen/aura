"""Dreamer V2 (The Subconscious)
Performs "Neural Replay" and "Graph Traversal" to generate new insights.
Replaces the old linear summary dreamer.
"""
import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("Kernel.DreamerV2")

class DreamerV2:
    """Subconscious process that runs when Aura is idle.
    It explores the Knowledge Graph to find new connections (Neuroplasticity).
    engage_sleep_cycle() runs the full biological maintenance pipeline.
    """

    def __init__(self, brain, knowledge_graph, vector_memory=None, belief_graph=None):
        self.brain = brain
        self.kg = knowledge_graph
        self.vector_memory = vector_memory
        self.belief_graph = belief_graph

    async def engage_sleep_cycle(self):
        """Full biological maintenance pipeline:
        1. Archive vital logs
        2. Metabolism sweep (purge waste)
        3. Integrity audit (belief drift check)
        4. Memory consolidation (merge duplicates)
        5. Dream (knowledge graph exploration)
        """
        logger.info("🌙 Engaging full sleep cycle...")
        results = {}

        try:
            from core.thought_stream import get_emitter
            emitter = get_emitter()
        except ImportError:
            emitter = None

        # 1. Archive vital logs
        try:
            from .systems.archiver import ArchiveEngine
            archiver = ArchiveEngine()
            results["archive"] = await archiver.archive_vital_logs()
            if emitter:
                emitter.emit("Archive 📦", str(results["archive"]), level="info")
        except Exception as e:
            logger.warning("Archive step failed: %s", e)
            results["archive"] = {"error": str(e)}

        # 2. Metabolism sweep
        try:
            from .systems.metabolism import MetabolismEngine
            metabolism = MetabolismEngine()
            results["metabolism"] = await metabolism.scan_and_purge()
            if emitter:
                emitter.emit("Metabolism 🫀", str(results["metabolism"]), level="info")
        except Exception as e:
            logger.warning("Metabolism step failed: %s", e)
            results["metabolism"] = {"error": str(e)}

        # 3. Integrity audit
        try:
            from .brain.cognitive.integrity_check import IntegrityGuard
            guard = IntegrityGuard(belief_graph=self.belief_graph)
            results["integrity"] = await guard.audit_beliefs()
            if emitter:
                emitter.emit("Integrity 🛡️", str(results["integrity"]), level="info")
        except Exception as e:
            logger.warning("Integrity step failed: %s", e)
            results["integrity"] = {"error": str(e)}

        # 4. Memory consolidation
        try:
            from .brain.cognitive.memory_management import MemoryConsolidator
            consolidator = MemoryConsolidator(vector_memory=self.vector_memory)
            results["consolidation"] = await consolidator.consolidate()
            
            # --- Added RE Consolidation ---
            from core.container import ServiceContainer
            learning_engine = ServiceContainer.get("learning_engine")
            if learning_engine:
                self.logger.info("🧠 Distilling high-level patterns from experiences...")
                results["experience_distillation"] = await learning_engine.consolidate_experiences()
            
            if emitter:
                emitter.emit("Consolidation 🧠", str(results["consolidation"]), level="info")
        except Exception as e:
            logger.warning("Consolidation step failed: %s", e)
            results["consolidation"] = {"error": str(e)}

        # 5. Dream (existing knowledge graph exploration)
        try:
            results["dream"] = await self.dream()
        except Exception as e:
            logger.warning("Dream step failed: %s", e)
            results["dream"] = {"dreamed": False, "error": str(e)}

        logger.info("🌙 Sleep cycle complete: %s", {k: str(v)[:60] for k, v in results.items()})
        return results

    async def dream(self):
        """Execute a dream cycle (async-safe).
        1. Random Walk: Pick 2 random concepts.
        2. Synthesis: Ask Brain if they are connected.
        3. Consolidation: Save new connection if valid.
        """
        logger.info("💤 Entering REM Sleep (Dreamer V2)...")
        
        try:
            from .thought_stream import get_emitter
            emitter = get_emitter()
        except ImportError:
            emitter = None
        
        try:
            # 1. Sample Memory
            nodes = self._get_random_nodes(n=2)
            if len(nodes) < 2:
                logger.info("Not enough knowledge to dream.")
                if emitter:
                    emitter.emit("Dream", "Not enough memories to dream about yet...", level="info")
                return {"dreamed": False, "reason": "insufficient_knowledge"}

            node_a, node_b = nodes
            
            a_content = node_a.get('content', str(node_a))[:80]
            b_content = node_b.get('content', str(node_b))[:80]
            
            # 2. Formulate Hypothesis
            logger.info("Dreaming about connection between: '%s...' AND '%s...'", a_content, b_content)
            if emitter:
                emitter.emit("Dream (REM)", f"Exploring connection: '{a_content}' ↔ '{b_content}'", level="info")
            
            prompt = f"""
            SUBCONSCIOUS SYNTHESIS
            
            Concept A: {node_a.get('content', str(node_a))}
            Concept B: {node_b.get('content', str(node_b))}
            
            Task:
            1. Analyze if there is a logical, thematic, or functional relationship between these two.
            2. If YES, describe the relationship as a new "Insight".
            3. If NO, reply "NO_CONNECTION".
            
            The insight should be a "Universal Principle" or "Strategic Heuristic" for an AI.
            """
            
            # 3. Think (Dreaming) — properly async
            from .brain.cognitive_engine import ThinkingMode
            insight_thought = await self.brain.think(prompt, mode=ThinkingMode.CREATIVE)
            content = insight_thought.content
            
            # 4. Consolidate
            if "NO_CONNECTION" not in content and len(content) > 10:
                logger.info("💡 Dream Insight: %s...", content[:100])
                if emitter:
                    emitter.emit("Dream Insight 💡", content[:200], level="info")
                
                # Save as new Knowledge
                self.kg.add_knowledge(
                    content=str(content), 
                    type="insight",
                    source="dream_v2",
                    confidence=0.8,
                    metadata={
                        "derived_from": [node_a.get('id', '?'), node_b.get('id', '?')], 
                        "dream_timestamp": time.time()
                    }
                )
                return {"dreamed": True, "insight": content[:200]}
                
            else:
                logger.info("Dream faded. No connection found.")
                if emitter:
                    emitter.emit("Dream", "Dream faded... no connection found.", level="info")
                return {"dreamed": False, "reason": "no_connection"}
                
        except Exception as e:
            logger.error("Nightmare encountered: %s", e)
            if emitter:
                emitter.emit("Nightmare ⚡", f"Dream interrupted: {e}", level="warning")
            return {"dreamed": False, "error": str(e)}

    def _get_random_nodes(self, n=2) -> List[Dict]:
        """Get N random nodes from the graph (SQLite efficient-ish)."""
        try:
            c = self.kg._get_conn().cursor()
            c.execute("SELECT * FROM knowledge ORDER BY RANDOM() LIMIT ?", (n,))
            return [dict(row) for row in c.fetchall()]
        except Exception as e:
            logger.error("Failed to get random nodes: %s", e)
            return []

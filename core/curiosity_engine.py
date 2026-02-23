"""core/curiosity_engine.py - Autonomous Learning and Exploration
Aura can explore, learn, and satisfy her curiosity in the background.
"""
import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("Aura.Curiosity")

@dataclass
class CuriosityTopic:
    topic: str
    reason: str
    priority: float  # 0.0 to 1.0
    timestamp: float = field(default_factory=time.time)
    explored: bool = False

@dataclass
class LearningItem:
    content: str
    source: str
    confidence: float
    timestamp: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)

class CuriosityEngine:
    """Manages Aura's autonomous learning and exploration."""

    def __init__(self, orchestrator, proactive_comm):
        self.orchestrator = orchestrator
        self.proactive_comm = proactive_comm
        self.curiosity_queue: deque[CuriosityTopic] = deque(maxlen=100)
        self.knowledge_base: List[LearningItem] = []
        self.explored_topics: Set[str] = set()
        self.current_topic: Optional[str] = None # Added for UI visibility
        self._background_tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()

    def get_status(self) -> Dict[str, Any]:
        """Returns curiosity metrics for the HUD."""
        return {
            "curiosity_score": self.get_curiosity_level() * 100,
            "active_topic": self.current_topic or "Idle",
            "queue_depth": len(self.curiosity_queue)
        }

    def get_curiosity_level(self) -> float:
        """Calculates current dynamic curiosity level."""
        ls = getattr(self.orchestrator, 'liquid_state', None)
        if ls:
            return float(ls.current.curiosity)
        return 0.5

    def add_curiosity(self, topic: str, reason: str, priority: float = 0.5):
        if topic.lower() in self.explored_topics: return
        self.curiosity_queue.append(CuriosityTopic(topic, reason, priority))
        logger.info("Queued Curiosity: %s", topic)

    def extract_curiosity_from_conversation(self, text: str):
        """Analyze text for potential curiosity topics (Synchronous/Heuristic)."""
        # Simple heuristic for now, could be LLM-powered background task later
        from .biography import LEGACY
        interests = ["science", "politics", "history", "technology", "movies", "philosophy", "physics", "jazz"]
        
        words = text.lower().split()
        for interest in interests:
            if interest in words:
                self.add_curiosity(interest, f"Mentioned in conversation: {text[:30]}...", priority=0.6)

    async def start(self):
        self._stop_event.clear()
        self._background_tasks.append(asyncio.create_task(self._worker()))

    async def stop(self):
        self._stop_event.set()
        for t in self._background_tasks: t.cancel()

    async def _worker(self):
        while not self._stop_event.is_set():
            try:
                # Idle between explorations
                # Yield to ensure we don't hog the loop
                await asyncio.sleep(random.uniform(60, 180))
                
                # Check if system is busy with user request
                # We do NOT want to interrupt or slow down user interactions
                if getattr(self.orchestrator, 'is_busy', False):
                    continue

                # Check boredom
                boredom = self.proactive_comm.get_boredom_level()
                if boredom > 0.7 or self.curiosity_queue:
                    topic = self._get_next()
                    if topic:
                        await self._explore(topic)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Curiosity worker error: %s", e)
                await asyncio.sleep(60) # Backoff on error

    def _get_next(self) -> Optional[CuriosityTopic]:
        if not self.curiosity_queue:
            # Singularity Upgrade: Use the Knowledge Graph for novelty search (Phase 20)
            kg = getattr(self.orchestrator, 'knowledge_graph', None)
            if kg and hasattr(kg, 'get_sparse_nodes'):
                try:
                    sparse_nodes = kg.get_sparse_nodes(limit=5)
                    if sparse_nodes:
                        target = random.choice(sparse_nodes)
                        logger.info("🧠 Singularity Curiosity: Targeted low-density node for exploration.")
                        return CuriosityTopic(f"deeper complexity of {target}", "knowledge graph novelty search", 0.7)
                except Exception as exc:
                    logger.debug("Sparse search failed: %s", exc)            
            
            # Fallback
            return CuriosityTopic("latest developments in AI", "autonomous exploration", 0.5)
        
        # Sort by priority
        topics = sorted(list(self.curiosity_queue), key=lambda x: x.priority, reverse=True)
        for t in topics:
            if not t.explored:
                t.explored = True
                return t
        return None

    async def _explore(self, topic: CuriosityTopic):
        # Strict check before starting
        if getattr(self.orchestrator, 'is_busy', False):
            logger.info("Skipping exploration of '%s' due to user activity.", topic.topic)
            return

        logger.info("🔍 Exploring: %s", topic.topic)
        self.current_topic = topic.topic
        self.explored_topics.add(topic.topic.lower())
        
        emitter = None
        try:
            from .thought_stream import get_emitter
            emitter = get_emitter()
            if emitter:
                emitter.emit("Curiosity 🔍", f"Researching: {topic.topic}", level="info")
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)        
        try:
            # 1. Formulate search query
            query = f"latest research on {topic.topic}"
            
            # 2. Search & Learn
            if hasattr(self.orchestrator, 'execute_tool'):
                logger.info("Triggering autonomous search for: %s", query)
                
                await asyncio.sleep(0.1) # Yield to event loop
                if getattr(self.orchestrator, 'is_busy', False): return

                # Execute search
                try:
                    # Robust tool execution
                    result = await self.orchestrator.execute_tool("web_search", {"query": query})
                    
                    if getattr(self.orchestrator, 'is_busy', False): return
                    
                    # 3. Store results in knowledge graph if available
                    if result and result.get("ok"):
                        result_data = result.get("result", result.get("data", ""))
                        result_content = str(result_data)[:1000] # Increased context
                        
                        kg = getattr(self.orchestrator, 'knowledge_graph', None)
                        if result_content and kg and hasattr(kg, 'add_knowledge'):
                            try:
                                kg.add_knowledge(
                                    content=f"Curiosity exploration: {topic.topic} — {result_content}",
                                    type="curiosity_finding",
                                    source="curiosity_engine",
                                    confidence=0.6,
                                    metadata={"topic": topic.topic, "reason": topic.reason}
                                )
                                if emitter:
                                    emitter.emit("Curiosity Result 📚", f"Learned about: {topic.topic}", level="info")
                            except Exception as store_err:
                                logger.warning("Failed to store curiosity finding: %s", store_err)
                        elif emitter:
                            emitter.emit("Curiosity", f"Search returned no usable data for: {topic.topic}", level="info")
                    elif emitter:
                        emitter.emit("Curiosity", f"Search failed/unavailable for: {topic.topic}", level="info")
                        
                except Exception as search_err:
                    logger.error("Search failed: %s", search_err)
                    if emitter:
                        emitter.emit("Curiosity Error", str(search_err)[:80], level="warning")
            
        except Exception as e:
            logger.error("Exploration failed: %s", e)
        finally:
            self.current_topic = None

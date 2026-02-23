# core/dream_processor.py
import logging
import time
from typing import List, Optional

from infrastructure import Cognitive

logger = logging.getLogger("Kernel.Dream")

class DreamProcessor:
    """Offline Memory Consolidation.
    Turning short-term logs into long-term wisdom.
    """

    def __init__(self, memory_nexus, brain: Cognitive):
        self.memory = memory_nexus
        self.brain = brain
        self.fragment_threshold = 10 # Process after 10 new events

    def dream(self):
        """The Dreaming Cycle.
        1. Fetch recent raw episodes.
        2. Summarize them into a narrative.
        3. Extract 'Lessons Learned'.
        4. Store in Vector DB.
        5. Archive raw episodes.
        """
        logger.info("🌙 Entering Dream State...")
        
        # 1. Fetch recent episodes via safe accessor chain
        episodic_store = getattr(self.memory, 'episodic', None)
        if episodic_store is None:
            logger.warning("Episodic memory subsystem not attached.")
            return
        data = getattr(episodic_store, 'data', None)
        if data is None or not isinstance(data, dict):
            logger.warning("Episodic memory has no accessible data store.")
            return
        episodes = data.get("episodic", [])


        if len(episodes) < self.fragment_threshold:
            logger.info("Not enough experiences to dream about.")
            return

        recent_batch = episodes[-self.fragment_threshold:]
        
        # 2. Cognitive Reflection
        summary_prompt = (
            "Review these recent events and extract 3 key lessons or facts.\n"
            f"Events: {recent_batch}\n"
            "Format: Bullet points."
        )
        try:
            reflection = self.brain.think(summary_prompt)
            logger.info("Dream Insight: %s", reflection)
            
            # 3. Consolidate to Vector Memory
            self.memory.vector.add(
                text=reflection,
                metadata={"source": "dream_cycle", "timestamp": time.time()}
            )
            
            # 4. Pruning (Optional - usually we keep raw logs but archive them)
            # For this MVP, we just log that we processed them.
            
        except Exception as e:
            logger.error("Nightmare error: %s", e)

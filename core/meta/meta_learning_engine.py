import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("Meta.Learning")

class MetaLearningEngine:
    """Enables Aura to learn from past experiences by identifying structural similarities
    between tasks and applying successful strategies.
    
    Integrated with CognitiveEngine and VectorMemory.
    """
    
    def __init__(self, vector_memory, cognitive_engine):
        self.vectors = vector_memory
        self.brain = cognitive_engine
        
    async def fingerprint_task(self, task_description: str) -> Optional[List[float]]:
        """Generate a semantic embedding of the task structure using the brain's client.
        """
        if not task_description:
            return None
            
        try:
            # Use the brain's legacy client (RobustOllamaClient) which has generate_embedding
            if hasattr(self.brain, "client") and self.brain.client:
                return self.brain.client.generate_embedding(task_description)
            else:
                logger.warning("No embedding provider available for fingerprinting.")
                return None
        except Exception as e:
            logger.error("Failed to fingerprint task: %s", e)
            return None

    async def recall_strategy(self, task_description: str) -> Optional[Dict[str, Any]]:
        """Retrieve relevant past strategies for a new task using semantic search.
        """
        if not self.vectors:
            return None
            
        # We use the text-based search directly now that VectorMemory handles embeddings
        results = self.vectors.search(
            query=task_description, 
            limit=3
        )
        
        # Filter for 'experience' type and check similarity
        for match in results:
            if match.get("metadata", {}).get("type") == "experience":
                # distance in ChromaDB is usually cosine distance, 0.0 is perfect match
                distance = match.get("distance", 1.0)
                if distance < 0.3: # Threshold for high relevance
                    logger.info("🧠 Meta-Learning: Found relevant past experience (Dist: %.2f)", distance)
                    return match
        
        return None

    async def index_experience(self, task: str, outcome: str, successful_tools: List[str], strategy_note: str = ""):
        """Save a completed task and its outcome as a learning experience.
        """
        if not self.vectors:
            return
            
        experience_data = {
            "task": task,
            "outcome": outcome,
            "successful_tools": successful_tools,
            "strategy_note": strategy_note,
            "timestamp": time.time(),
            "type": "experience"
        }
        
        # Create a text representation for the vector store
        text_rep = f"Task: {task}\nOutcome: {outcome}\nTools: {', '.join(successful_tools)}\nNote: {strategy_note}"
        
        # VectorMemory.add handles the embedding internally via Ollama
        self.vectors.add(content=text_rep, metadata=experience_data)
        logger.info("🧠 Meta-Learning: Indexed experience for '%s...'", task[:30])

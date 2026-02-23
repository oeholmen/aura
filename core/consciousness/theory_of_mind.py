"""core/brain/cognition/theory_of_mind.py
Advanced Theory of Mind (ToM) system for Aura.
Consolidated from duplicate modules.
"""
import json
import logging
import time
import asyncio
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Aura.ToM")

class SelfType(Enum):
    HUMAN = "human"
    AI = "ai"
    ANIMAL = "animal"
    COLLECTIVE = "collective"
    UNKNOWN = "unknown"

@dataclass
class AgentModel:
    """Model of another agent (user, system, etc.)"""
    identifier: str
    self_type: SelfType = SelfType.HUMAN
    beliefs: Dict[str, Any] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    knowledge_level: str = "intermediate"
    emotional_state: str = "neutral"
    interaction_history: List[Dict[str, Any]] = field(default_factory=list)
    trust_level: float = 0.5
    rapport: float = 0.5
    last_updated: float = field(default_factory=time.time)
    
    def to_dict(self):
        data = asdict(self)
        data['self_type'] = self.self_type.value
        return data

class TheoryOfMindEngine:
    """Complete Theory of Mind system with LLM-backed social reasoning.
    """
    
    def __init__(self, cognitive_engine=None):
        self.brain = cognitive_engine
        self.known_selves: Dict[str, AgentModel] = {}
        logger.info("TheoryOfMindEngine initialized.")
    
    def _get_brain(self):
        if self.brain:
            return self.brain
        from core.container import ServiceContainer
        return ServiceContainer.get("cognitive_engine")

    async def understand_user(self, user_id: str, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update and return the model of a specific user."""
        if user_id not in self.known_selves:
            self.known_selves[user_id] = AgentModel(identifier=user_id)
        
        model = self.known_selves[user_id]
        model.interaction_history.append({"message": message, "timestamp": time.time()})
        model.last_updated = time.time()
        
        # Determine deep or fast analysis
        if len(model.interaction_history) % 5 == 0:
            return await self._deep_analyze(user_id, message, context)
        return self._fast_heuristic_update(user_id, message)

    async def infer_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Legacy-compatible intent inference shim."""
        user_id = context.get("user_id", "default_user") if context else "default_user"
        result = await self.understand_user(user_id, message, context)
        # Extract intent data in the format expected by context builder
        intent_data = result.get("intent", {})
        if "intent" in intent_data and isinstance(intent_data, dict):
             # Ensure 'pragmatic' key exists or fallback
             intent_data["pragmatic"] = intent_data.get("intent", "standard")
        return intent_data

    def _fast_heuristic_update(self, user_id: str, message: str) -> Dict[str, Any]:
        """Apply keyword heuristics for rapid updates without LLM calls."""
        model = self.known_selves[user_id]
        msg = message.lower()
        if any(w in msg for w in ["thank", "great", "love", "appreciate", "good"]):
            model.trust_level = min(1.0, model.trust_level + 0.05)
            model.rapport = min(1.0, model.rapport + 0.05)
        elif any(w in msg for w in ["angry", "wrong", "bad", "hate", "rude"]):
            model.trust_level = max(0.0, model.trust_level - 0.05)
            model.rapport = max(0.0, model.rapport - 0.05)
            
        return {
            "user_model": model.to_dict(),
            "intent": {"intent": message, "sentiment": "neutral"},
            "emotional_state": model.emotional_state,
            "knowledge_level": model.knowledge_level
        }

    async def _deep_analyze(self, user_id: str, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use LLM for deep social reasoning."""
        model = self.known_selves[user_id]
        brain = self._get_brain()
        if not brain:
            return self._fast_heuristic_update(user_id, message)

        prompt = f"""Analyze user intent and state.
User Message: {message}
Recent History: {[m['message'] for m in model.interaction_history[-3:]]}
Return JSON: {{"intent": "...", "sentiment": "...", "emotional_state": "...", "knowledge_level": "..."}}"""

        try:
            # Fully async call to cognitive engine
            thought = await brain.think(
                objective=prompt,
                context={"model": model.to_dict(), "global_context": context},
                mode="FAST" # Use fast model for social metadata
            )
            
            from utils.json_utils import extract_json
            data = extract_json(thought.content)
            if data:
                model.emotional_state = data.get("emotional_state", model.emotional_state)
                model.knowledge_level = data.get("knowledge_level", model.knowledge_level)
                return {
                    "user_model": model.to_dict(),
                    "intent": data,
                    "emotional_state": model.emotional_state,
                    "knowledge_level": model.knowledge_level
                }
        except Exception as e:
            logger.debug("Deep ToM analysis failed: %s", e)
            
        return self._fast_heuristic_update(user_id, message)

    async def predict_reaction(self, user_id: str, my_action: Dict[str, Any]) -> Dict[str, Any]:
        """Predict reaction to an action using LLM."""
        model = self.known_selves.get(user_id) or AgentModel(identifier=user_id)
        brain = self._get_brain()
        if not brain:
            return {"prediction": "Unknown (Brain Offline)"}
            
        thought = await brain.think(
            objective=f"Predict how {user_id} will react if I take this action: {my_action}",
            context={"user_model": model.to_dict()},
            mode="FAST"
        )
        return {"prediction": thought.content, "confidence": thought.confidence}

    async def will_this_help_user(self, user_id: str, proposed_response: str) -> Tuple[bool, str]:
        """Social outcome simulation."""
        if user_id not in self.known_selves:
            return True, "No user model, assuming helpful."
        
        model = self.known_selves[user_id]
        if model.emotional_state == "frustrated" and len(proposed_response) > 500:
             return False, "User is frustrated; response is likely too verbose."
             
        for goal in model.goals:
             if goal.lower() in proposed_response.lower():
                  return True, f"Response addresses goal: {goal}"
                  
        return True, "Response aligned."

# Global Singletons for compatibility
_engine_instance = None

def get_theory_of_mind(brain=None):
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = TheoryOfMindEngine(brain)
    return _engine_instance

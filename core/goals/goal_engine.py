import time
import logging
import re
from typing import Dict, Any, Optional
from core.container import ServiceContainer

logger = logging.getLogger("Aura.GoalEngine")

class GoalEngine:
    """
    Manages the lifecycle and evaluation of Aura's autonomous goals.
    Bridges the gap between raw CognitiveContext and the BeliefGraph.
    """

    def __init__(self):
        self._state_repo = None
        self._gbm = None
        logger.info("GoalEngine initialized.")

    @property
    def state_repo(self):
        if self._state_repo is None:
            self._state_repo = ServiceContainer.get("state_repo")
        return self._state_repo

    @property
    def gbm(self):
        if self._gbm is None:
            self._gbm = ServiceContainer.get("goal_belief_manager")
        return self._gbm

    async def add_goal(self, name: str, objective: str):
        """Add a new autonomous goal."""
        state = getattr(self.state_repo, "_current", None)
        if not state: return

        # Add to state context
        state.cognition.active_goals.append({
            "name": name,
            "objective": objective,
            "created_at": time.time(),
            "progress": 0.0,
            "status": "active"
        })
        
        # Also register in Belief System
        if self.gbm:
            self.gbm.reinforce_goal(objective, "Direct self-commitment.")
            
        await self.state_repo.commit(state, cause=f"New goal: {name}")
        logger.info("Goal added: %s", name)

    async def evaluate_goals(self):
        """Assess progress of all active goals."""
        state = getattr(self.state_repo, "_current", None)
        if not state: return

        for goal in state.cognition.active_goals:
            if goal.get("status") == "active":
                await self._assess_progress(goal)
        
        await self.state_repo.commit(state, cause="Periodic goal evaluation")

    async def _assess_progress(self, goal: Dict[str, Any]):
        """
        Real progress evaluation: check if the goal's objective appears in 
        recent working memory or episodic memory.
        """
        objective = goal.get("objective", "")
        if not objective:
            return

        state = getattr(self.state_repo, "_current", None)
        if not state:
            return

        # Check if recent responses reference the objective
        recent_messages = [
            str(m.get("content", "") or "")
            for m in state.cognition.working_memory[-10:]
            if m.get("role") == "assistant"
        ]

        if self._shows_goal_progress(objective, recent_messages):
            # Evidence of progress found
            goal["progress"] = min(1.0, goal.get("progress", 0.0) + 0.2)
        else:
            # No evidence of progress — don't increment
            pass

        if goal["progress"] >= 1.0:
            goal["status"] = "completed"
            goal["completed_at"] = time.time()
            logger.info("Goal completed: %s", goal.get("name"))

    @staticmethod
    def _normalize_tokens(text: str) -> list[str]:
        stopwords = {
            "a", "an", "and", "are", "for", "i", "in", "is", "it", "of", "on",
            "or", "the", "to", "we", "why",
        }
        tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
        return [token for token in tokens if token not in stopwords]

    def _shows_goal_progress(self, objective: str, messages: list[str]) -> bool:
        objective_tokens = self._normalize_tokens(objective)
        if not objective_tokens:
            return False

        objective_phrase = " ".join(objective_tokens)
        objective_bigrams = {
            tuple(objective_tokens[i : i + 2])
            for i in range(max(0, len(objective_tokens) - 1))
        }

        for message in messages:
            message_tokens = self._normalize_tokens(message)
            if not message_tokens:
                continue

            message_token_set = set(message_tokens)
            coverage = len(set(objective_tokens) & message_token_set) / max(len(set(objective_tokens)), 1)
            if len(objective_tokens) <= 2 and coverage == 1.0:
                return True

            normalized_message = " ".join(message_tokens)
            if objective_phrase and objective_phrase in normalized_message:
                return True

            if objective_bigrams:
                message_bigrams = {
                    tuple(message_tokens[i : i + 2])
                    for i in range(max(0, len(message_tokens) - 1))
                }
                bigram_coverage = len(objective_bigrams & message_bigrams) / max(len(objective_bigrams), 1)
                if coverage >= 0.75 and bigram_coverage >= 0.5:
                    return True

        return False

    def get_active_goals(self):
        state = getattr(self.state_repo, "_current", None)
        if not state: return []
        return [g for g in state.cognition.active_goals if g.get("status") == "active"]

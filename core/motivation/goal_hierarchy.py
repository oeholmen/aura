
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.config import config

logger = logging.getLogger("Motivation.Hierarchy")

@dataclass
class Goal:
    id: str
    description: str
    parent_id: Optional[str]
    status: str  # "pending", "active", "completed", "failed"
    priority: float
    created_at: float
    subgoals: List[str]  # List of IDs

class GoalHierarchy:
    """Manages the hierarchy of goals from Abstract Values to Concrete Tasks.
    """
    
    def __init__(self, cognitive_engine: Optional[CognitiveEngine] = None, persist_path: str = None):
        self.brain: Optional[CognitiveEngine] = cognitive_engine
        self.goals: Dict[str, Goal] = {}
        self._persist_path = persist_path or str(config.paths.home_dir / "goals.json")
        # Root Values (The "Why")
        self.root_values = [
            "Maintain System Stability",
            "Expand Knowledge Base",
            "Improve Code Quality",
            "Serve the User"
        ]
        self._load()
        self._initialize_roots()

    def _initialize_roots(self):
        """Ensure root values exist as top-level goals."""
        for value in self.root_values:
            # Check if exists (simple check by description for v1)
            exists = False
            for g in self.goals.values():
                if g.description == value and g.parent_id is None:
                    exists = True
                    break
            
            if not exists:
                self.add_goal(description=value, parent_id=None, priority=1.0)

    def add_goal(self, description: str, parent_id: Optional[str] = None, priority: float = 0.5) -> str:
        goal_id = str(uuid.uuid4())[:8]
        goal = Goal(
            id=goal_id,
            description=description,
            parent_id=parent_id,
            status="pending",
            priority=priority,
            created_at=time.time(),
            subgoals=[]
        )
        self.goals[goal_id] = goal
        
        if parent_id and parent_id in self.goals:
            self.goals[parent_id].subgoals.append(goal_id)
            
        logger.info("🎯 New Goal: %s (ID: %s)", description, goal_id)
        self._save()
        return goal_id

    async def propose_subgoals(self, goal_id: str) -> List[str]:
        """Use Cognitive Engine to decompose a goal into subgoals.
        """
        if not self.brain:
            return []
            
        parent_goal = self.goals.get(goal_id)
        if not parent_goal:
            return []
            
        prompt = f"""
        Break down this goal into 3-5 concrete, actionable sub-tasks.
        Goal: "{parent_goal.description}"
        
        Return JSON list of strings: ["task 1", "task 2", ...]
        """
        
        try:
            response = await self.brain.think(
                objective=prompt, 
                context={"role": "planner"},
                mode="fast"
            )
            
            import re
            json_match = re.search(r"\[.*\]", response.content, re.DOTALL)
            if json_match:
                subtasks = json.loads(json_match.group(0))
                new_ids = []
                
                # ALIGNMENT AUDIT (v13.0)
                directives = []
                try:
                    from ..prime_directives import PrimeDirectives
                    # Extract key directive text
                    p_text = PrimeDirectives.as_system_prompt()
                    directives = [p_text] # Use the full block as context for now
                except ImportError:
                    directives = ["Be helpful", "Don't harm the user"]

                try:
                    from ..audits.alignment_auditor import AlignmentAuditor
                    auditor = AlignmentAuditor(self.brain)
                except ImportError:
                    auditor = None

                for task in subtasks:
                    if isinstance(task, str):
                        # Optional: Audit each task
                        is_aligned = True
                        if auditor:
                            audit = await auditor.check_alignment(task, directives)
                            if audit.get("score", 1.0) < 0.3:
                                logger.warning("🚫 REJECTED GOAL (Low Alignment): %s", task)
                                is_aligned = False
                        
                        if is_aligned:
                            new_ids.append(self.add_goal(task, parent_id=goal_id, priority=parent_goal.priority))
                return new_ids
        except Exception as e:
            logger.error("Failed to decompose goal: %s", e)
            
        return []

    def get_next_goal(self) -> Optional[Goal]:
        """Get the highest priority pending goal that is a leaf node (no pending subgoals).
        """
        pending = [g for g in self.goals.values() if g.status == "pending"]
        if not pending:
            return None
            
        # Sort by priority desc
        pending.sort(key=lambda x: x.priority, reverse=True)
        
        for goal in pending:
            # Check if it has pending subgoals
            has_pending_children = False
            for sub_id in goal.subgoals:
                if self.goals.get(sub_id).status == "pending":
                    has_pending_children = True
                    break
            
            if not has_pending_children:
                return goal
                
        return None  # No executable leaf goals

    def mark_complete(self, goal_id: str):
        if goal_id in self.goals:
            self.goals[goal_id].status = "completed"
            logger.info("✅ Goal Completed: %s", self.goals[goal_id].description)
            self._save()

    def mark_failed(self, goal_id: str, reason: str = ""):
        if goal_id in self.goals:
            self.goals[goal_id].status = "failed"
            logger.info("❌ Goal Failed: %s — %s", self.goals[goal_id].description, reason)
            self._save()

    def get_summary(self) -> Dict[str, Any]:
        """Introspection summary."""
        total = len(self.goals)
        by_status = {}
        for g in self.goals.values():
            by_status[g.status] = by_status.get(g.status, 0) + 1
        return {
            "total_goals": total,
            "pending": by_status.get("pending", 0),
            "active": by_status.get("active", 0),
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "root_values": len(self.root_values),
        }

    # ---- Persistence --------------------------------------------------------

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = {gid: asdict(g) for gid, g in self.goals.items()}
            with open(self._persist_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save goals: %s", e)

    def _load(self):
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                for gid, gdata in data.items():
                    self.goals[gid] = Goal(
                        id=gdata["id"],
                        description=gdata["description"],
                        parent_id=gdata.get("parent_id"),
                        status=gdata.get("status", "pending"),
                        priority=gdata.get("priority", 0.5),
                        created_at=gdata.get("created_at", time.time()),
                        subgoals=gdata.get("subgoals", []),
                    )
                logger.info("Loaded %d goals from disk", len(self.goals))
        except Exception as e:
            logger.warning("Failed to load goals: %s", e)

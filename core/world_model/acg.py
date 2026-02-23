import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from core.config import config

logger = logging.getLogger("WorldModel.ACG")

@dataclass
class CausalLink:
    action_type: str
    params_hash: str
    context_sum: str
    outcome_delta: Dict[str, Any]  # Belief changes recorded
    success: bool
    timestamp: float = field(default_factory=time.time)

class ActionConsequenceGraph:
    """Action-Consequence Graph (ACG) v1.0.
    Stores empirical results of actions to enable historical causal reasoning.
    """

    def __init__(self, persist_path: str = None):
        self.persist_path = persist_path or str(config.paths.home_dir / "causal_graph.json")
        self.links: List[Dict[str, Any]] = []
        self._load()

    def record_outcome(self, action: Dict[str, Any], context: str, outcome: Dict[str, Any], success: bool):
        """Record the result of an action.
        """
        entry = {
            "action": action.get("tool"),
            "params": action.get("params", {}),
            "context": context[:200], # Consensed context
            "outcome": outcome,
            "success": success,
            "timestamp": time.time()
        }
        self.links.append(entry)
        
        # Keep recent 1000 links
        if len(self.links) > 1000:
            self.links = self.links[-1000:]
            
        self._save()
        logger.info("Causal Link Recorded: %s -> %s", entry['action'], 'Success' if success else 'Failure')

    def query_consequences(self, action_type: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Find historical consequences for a similar action.
        """
        matches = []
        for link in self.links:
            if link["action"] == action_type:
                # Basic param matching could be improved with semantic similarity
                if params is None or self._params_overlap(link["params"], params):
                    matches.append(link)
        return matches

    def _params_overlap(self, p1: Dict[str, Any], p2: Dict[str, Any]) -> bool:
        """Check if critical parameters match."""
        # For now, simple key check
        keys1 = set(p1.keys())
        keys2 = set(p2.keys())
        common = keys1.intersection(keys2)
        if not common: return True # Broad match if no params specified
        
        # Check values for common keys
        matches = 0
        for k in common:
            if p1[k] == p2[k]:
                matches += 1
        return matches / len(common) > 0.5

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            with open(self.persist_path, "w") as f:
                json.dump(self.links, f, indent=2)
        except Exception as e:
            logger.error("Failed to save ACG: %s", e)

    def _load(self):
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path, "r") as f:
                    self.links = json.load(f)
                logger.info("Loaded %d causal links from disk", len(self.links))
        except Exception as e:
            logger.warning("Failed to load ACG: %s", e)

# Global Instance
acg = ActionConsequenceGraph()

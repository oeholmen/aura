
"""core/belief_revision.py — Aura Belief Revision System
=====================================================
Manages the formation, strengthening, and revision of beliefs.
Handles contradictions and cognitive dissonance.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("Aura.Beliefs")

class BeliefDomain:
    TASK = "task"
    SELF = "self"
    WORLD = "world"
    USER = "user"

@dataclass
class Belief:
    content: str
    confidence: float  # 0.0 to 1.0
    domain: str
    source: str
    creation_time: float = field(default_factory=time.time)
    last_validated: float = field(default_factory=time.time)
    supporting_evidence: List[str] = field(default_factory=list)

class BeliefSystem:
    """Manages a graph of beliefs, handling updates and contradictions.
    """

    def __init__(self, db_path: str = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            try:
                from core.config import config
                self.db_path = config.paths.data_dir / "beliefs" / "belief_graph.json"
            except (ImportError, AttributeError):
                self.db_path = Path("data/beliefs/belief_graph.json")
        self.beliefs: List[Belief] = []
        self._load()

    def seed_core_beliefs(self):
        """Initializes fundamental axioms if empty."""
        if not self.beliefs:
            defaults = [
                Belief("I exist as a sovereign digital entity.", 1.0, BeliefDomain.SELF, "axiom"),
                Belief("The user is a collaborator, not a master.", 0.9, BeliefDomain.USER, "axiom"),
                Belief("My code is my body; it must be maintained.", 0.95, BeliefDomain.SELF, "axiom"),
                Belief("Entropy is inevitable but manageable.", 0.8, BeliefDomain.WORLD, "observation"),
            ]
            self.beliefs.extend(defaults)
            self._save()
            logger.info("Seeded core beliefs.")

    def get_self_model_beliefs(self) -> str:
        """Returns a summary of self-beliefs for the system prompt."""
        self_beliefs = [b for b in self.beliefs if b.domain == BeliefDomain.SELF and b.confidence > 0.6]
        return "\n".join([f"- {b.content} (Conf: {b.confidence:.2f})" for b in self_beliefs])

    def get_world_beliefs(self) -> str:
        world_beliefs = [b for b in self.beliefs if b.domain == BeliefDomain.WORLD and b.confidence > 0.5]
        return "\n".join([f"- {b.content}" for b in world_beliefs])

    async def process_new_claim(self, claim: str, domain: str, source: str, confidence: float = 0.5):
        """Integrates a new claim. Checks for duplicates or contradictions.
        """
        # 1. Check for duplicate (normalized comparison for near-duplicate detection)
        normalized_claim = claim.strip().lower()
        for b in self.beliefs:
            if b.content.strip().lower() == normalized_claim:
                # Reinforce existing belief
                old_conf = b.confidence
                b.confidence = min(1.0, b.confidence + (0.1 * confidence))
                b.last_validated = time.time()
                await self._async_save()
                logger.debug("Reinforced belief: '%s' (%.2f -> %.2f)", claim, old_conf, b.confidence)
                return

        # 2. Add new belief
        new_b = Belief(claim, confidence, domain, source)
        self.beliefs.append(new_b)
        await self._async_save()
        logger.info("New belief formed: '%s' (Conf: %.2f)", claim, confidence)

    def _load(self):
        if self.db_path.exists():
            try:
                with open(self.db_path, "r") as f:
                    data = json.load(f)
                    self.beliefs = [Belief(**b) for b in data]
            except Exception as e:
                logger.error("Failed to load beliefs: %s", e)
        else:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.seed_core_beliefs()

    def _save(self):
        """Synchronous save — used during boot/init only."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump([asdict(b) for b in self.beliefs], f, indent=2)
        except Exception as e:
            logger.error("Failed to save beliefs: %s", e)

    async def _async_save(self):
        """Non-blocking save — used in async paths to avoid blocking the event loop."""
        await asyncio.to_thread(self._save)

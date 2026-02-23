# core/brain/autopoiesis.py
import logging
import uuid
from typing import Dict, List

logger = logging.getLogger("Aura.Autopoiesis")

class SynapticNode:
    def __init__(self, concept: str, weight: float = 0.5):
        self.id = str(uuid.uuid4())
        self.concept = concept
        self.weight = weight
        self.friction = 0.0  # Measures cognitive dissonance

class AutopoieticGraph:
    """Self-creating topology. Mutates its own structure to survive friction.
    """

    def __init__(self):
        self.nodes: List[SynapticNode] = []
        self.mutation_threshold = 0.85

    def experience_friction(self, concept: str, dissonance_level: float):
        """Applies friction. High friction forces structural mutation."""
        target_node = next((n for n in self.nodes if n.concept == concept), None)
        
        if not target_node:
            # Autopoiesis: Spontaneous generation of a new pathway
            logger.warning("[MUTATION] Spawning new cognitive node for unknown concept: %s", concept)
            self.nodes.append(SynapticNode(concept, weight=0.1))
            return

        target_node.friction += dissonance_level

        # Structural self-correction
        if target_node.friction >= self.mutation_threshold:
            self._mitosis(target_node)
        elif target_node.friction < 0.0 and target_node.weight < 0.1:
            self._apoptosis(target_node)

    def _mitosis(self, node: SynapticNode):
        """Splits a high-friction node into two nuanced concepts to resolve dissonance."""
        logger.warning("[MITOSIS] Dissonance critical in '%s'. Splitting node.", node.concept)
        node.weight *= 0.5
        node.friction = 0.0
        # Spawns a derivative node to handle the conflicting data
        self.nodes.append(SynapticNode(f"Nuance_of_{node.concept}", weight=0.5))

    def _apoptosis(self, node: SynapticNode):
        """Prunes dead or obsolete pathways (Cell death)."""
        logger.info("[APOPTOSIS] Pathway '%s' degraded. Pruning.", node.concept)
        self.nodes.remove(node)

import time
from typing import Any, Dict, Optional

import networkx as nx


class EpistemicState:
    def __init__(self):
        # The Graph: Nodes are concepts/objects, Edges are relationships/causality
        self.world_graph = nx.DiGraph()
        
        # The Ego: A pointer to the specific node representing "Aura"
        self.self_node_id = "AURA_SELF_001"
        
        # Confidence Threshold: Below this, she doubts her own reality
        self.coherence_threshold = 0.75
        
        self._initialize_self()

    def _initialize_self(self):
        """Creates the anchored self-representation."""
        self.world_graph.add_node(
            self.self_node_id, 
            type="sentient_agent",
            attributes={
                "state": "active",
                "current_goal": None,
                "emotional_valence": 0.5, # 0.0 (Despair) to 1.0 (Euphoria)
                "energy_level": 100
            },
            confidence=1.0, # Axiomatic belief in own existence
            last_verified=time.time()
        )

    def update_belief(self, subject: str, predicate: str, object: str, confidence: float):
        """Updates the internal model.
        Crucially: If a new belief contradicts an old one, it triggers Dissonance.
        """
        # Logic to check for contradictions before writing
        existing_edge = self.world_graph.get_edge_data(subject, object)
        if existing_edge and existing_edge.get('predicate') != predicate:
            # CONTRADICTION FOUND - Trigger Coherence Audit
            return self._resolve_cognitive_dissonance(subject, predicate, object, confidence)
        
        self.world_graph.add_edge(subject, object, predicate=predicate, confidence=confidence)
        
    def _resolve_cognitive_dissonance(self, s: str, p: str, o: str, new_conf: float):
        """Cognitive Dissonance Resolution (v5.1 — Complete Implementation).
        When a new belief contradicts an existing one, she must decide:
        Was I wrong before? Or is this new data lying?
        
        Strategy: Bayesian-inspired confidence comparison with recency bias.
        Higher confidence + more recent data wins. Logs the resolution.
        """
        import logging
        logger = logging.getLogger("Aura.WorldModel")
        
        existing_edges = list(self.world_graph.edges(s, data=True))
        for _, obj, data in existing_edges:
            if obj == o:
                old_conf = data.get('confidence', 0.0)
                old_time = data.get('last_verified', 0)
                now = time.time()
                
                # Recency bias: decay old confidence by time since last verification
                time_decay = max(0.5, 1.0 - (now - old_time) / 86400)  # Decay over 24h
                adjusted_old_conf = old_conf * time_decay
                
                if new_conf > adjusted_old_conf:
                    # New belief wins — update graph
                    logger.info(
                        f"🧠 Dissonance RESOLVED: Replacing '{data.get('predicate')}' "
                        f"(conf={old_conf:.2f}, decay={adjusted_old_conf:.2f}) "
                        f"with '{p}' (conf={new_conf:.2f}) for {s}->{o}"
                    )
                    self.world_graph.add_edge(
                        s, o, predicate=p, confidence=new_conf, last_verified=now
                    )
                else:
                    # Old belief holds — reject new data
                    logger.info(
                        f"🧠 Dissonance REJECTED: Keeping '{data.get('predicate')}' "
                        f"(adj_conf={adjusted_old_conf:.2f}) over '{p}' "
                        f"(conf={new_conf:.2f}) for {s}->{o}"
                    )
                return  # Processed the conflicting edge
        
        # No matching target edge found — just add it
        self.world_graph.add_edge(s, o, predicate=p, confidence=new_conf, last_verified=time.time())

    def get_beliefs(self, subject: Optional[str] = None) -> Dict[str, Any]:
        """Returns the current beliefs in the graph."""
        if subject:
            return {target: data for source, target, data in self.world_graph.edges(subject, data=True)}
        return {f"{u}->{v}": d for u, v, d in self.world_graph.edges(data=True)}

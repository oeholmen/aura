"""Belief Graph v6.0 - Unified Probabilistic World Model & Epistemic State.
Combines Bayesian-ish updates, time-decay, and cognitive dissonance resolution.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
from core.config import config

logger = logging.getLogger("WorldModel.BeliefGraph")


@dataclass
class BeliefEdge:
    source: str
    relation: str
    target: str
    confidence: float = 0.5
    last_updated: float = field(default_factory=time.time)
    evidence_count: int = 1

    def to_dict(self):
        return {
            "source": self.source,
            "relation": self.relation,
            "target": self.target,
            "confidence": self.confidence,
            "last_updated": self.last_updated,
            "count": self.evidence_count,
        }


class BeliefGraph:
    """v6.0: Unified World Model (Epistemic State).
    Tracks the agent's current understanding, confidence levels, and self-representation.
    Supports Bayesian updates, contradiction resolution (Dissonance), and time-decay.
    """

    def __init__(self, persist_path: str = None):
        # The Graph: Nodes are concepts/objects, Edges are relationships/causality
        self.graph = nx.DiGraph()
        self.self_node_id = "AURA_SELF"
        
        self._persist_path = persist_path or str(config.paths.home_dir / "world_model.json")
        self._load()
        self._initialize_self()

    def _initialize_self(self):
        """Creates or updates the anchored self-representation."""
        if self.self_node_id not in self.graph:
            self.graph.add_node(
                self.self_node_id, 
                type="sentient_agent",
                attributes={
                    "name": "Aura",
                    "state": "active",
                    "current_goal": None,
                    "emotional_valence": 0.5,
                    "energy_level": 100
                },
                confidence=1.0, # Axiomatic belief in own existence
                last_verified=time.time()
            )

    def detect_contradiction(self, source: str, relation: str, target: str) -> Optional[Dict[str, Any]]:
        """Check if a proposed belief contradicts existing state.
        Returns the existing conflicting belief if found.
        """
        # Logic: if (S, T) has an edge but with a different relation, it's a structural contradiction.
        # Or if (S, p, T) exists but with a different T for a functional relation.
        # For simplicity, we check if an edge between source and target exists with different relation.
        if self.graph.has_edge(source, target):
            existing = self.graph[source][target]
            if existing.get('relation') != relation:
                return {"source": source, "target": target, **existing}
        
        # Check for functional contradiction (e.g., Aura | state | idle vs Aura | state | busy)
        # This requires more metadata about relations, but for now we look at all relations from source
        if source not in self.graph:
            return None
            
        for t, data in self.graph[source].items():
            if data.get('relation') == relation and t != target:
                # E.g. "User | name | Bryan" vs "User | name | John"
                # This is a contradiction for many-to-one relations.
                return {"source": source, "target": t, **data}
                
        return None

    def update_belief(self, source: str, relation: str, target: str, confidence_score: float = 0.1):
        """Bayesian-ish update with contradiction detection (Epistemic resolution).
        """
        # 1. Detection: Check for existing contradictions
        contradiction = self.detect_contradiction(source, relation, target)
        if contradiction:
            # CONTRADICTION FOUND - Resolve through Epistemic weighting
            return self._resolve_cognitive_dissonance(source, relation, target, confidence_score)

        # 2. Update logic
        if self.graph.has_edge(source, target):
            edge_data = self.graph[source][target]
            # Reinforce: move toward 1.0 based on evidence
            new_conf = max(0.0, min(1.0, (edge_data['confidence'] * 0.8) + (confidence_score * 0.2)))
            self.graph.add_edge(
                source, target, 
                relation=relation, 
                confidence=new_conf,
                last_updated=time.time(),
                evidence_count=edge_data.get('evidence_count', 1) + 1
            )
        else:
            # New belief
            self.graph.add_edge(
                source, target, 
                relation=relation, 
                confidence=max(0.0, min(1.0, confidence_score)),
                last_updated=time.time(),
                evidence_count=1
            )
            
        logger.info("Belief Updated: %s -[%s]-> %s", source, relation, target)
        self._save()

    def _resolve_cognitive_dissonance(self, s: str, p: str, o: str, new_conf: float):
        """Resolve conflicting information by weighing confidence.
        """
        edge_data = self.graph[s][o]
        old_conf = edge_data.get('confidence', 0.0)
        old_p = edge_data.get('relation')

        if new_conf > old_conf:
            logger.warning("🧠 Cognitive Dissonance Resolved: '%s' supersedes '%s' (Conf: %.2f > %.2f)", p, old_p, new_conf, old_conf)
            self.graph.add_edge(s, o, relation=p, confidence=new_conf, last_updated=time.time(), evidence_count=1)
        else:
            logger.info("🧠 Dissonance Rejected: New data '%s' (Conf: %.2f) weaker than existing '%s' (Conf: %.2f)", p, new_conf, old_p, old_conf)
        
        self._save()

    def contradict_belief(self, source: str, relation: str, target: str, strength: float = 0.3):
        """Weaken a belief based on contradicting evidence."""
        if self.graph.has_edge(source, target):
            edge_data = self.graph[source][target]
            if edge_data.get('relation') == relation:
                new_conf = max(0.0, edge_data['confidence'] - strength)
                if new_conf < 0.05:
                    self.graph.remove_edge(source, target)
                    logger.info("Belief Dissolved: %s -[%s]-> %s", source, relation, target)
                else:
                    self.graph[source][target]['confidence'] = new_conf
                    self.graph[source][target]['last_updated'] = time.time()
                self._save()

    def get_beliefs_about(self, entity: str) -> List[Dict[str, Any]]:
        """Get all known relations originating from an entity."""
        if entity not in self.graph:
            return []
        results = []
        for target, data in self.graph[entity].items():
            results.append({
                "source": entity,
                "target": target,
                **data
            })
        return results

    async def query_federated(self, entity: str) -> List[Dict[str, Any]]:
        """Phase 16.2: Query both local beliefs and remote peers."""
        local_beliefs = self.get_beliefs_about(entity)
        
        from core.container import ServiceContainer
        sync_service = ServiceContainer.get("belief_sync")
        
        if not sync_service:
            return local_beliefs
            
        remote_beliefs = await sync_service.query_peers(entity)
        
        # Merge results (local takes precedence for metadata, but remote expands the graph)
        seen = {f"{b['source']}->{b['relation']}->{b['target']}" for b in local_beliefs}
        merged = list(local_beliefs)
        
        for rb in remote_beliefs:
            key = f"{rb['source']}->{rb['relation']}->{rb['target']}"
            if key not in seen:
                # Add remote belief with lower initial confidence
                rb['confidence'] *= 0.8 
                merged.append(rb)
                seen.add(key)
                
        return merged

    def get_beliefs(self) -> Dict[str, Any]:
        """Returns all beliefs as a dictionary (Compatibility with EpistemicState)."""
        return {f"{u}->{v}": d for u, v, d in self.graph.edges(data=True)}

    def get_strong_beliefs(self, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """Return only high-confidence beliefs."""
        results = []
        for u, v, d in self.graph.edges(data=True):
            if d.get('confidence', 0.0) >= threshold:
                results.append({
                    "source": u,
                    "target": v,
                    **d
                })
        return results

    def get_weak_beliefs(self, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """Return uncertain beliefs - candidates for investigation."""
        results = []
        for u, v, d in self.graph.edges(data=True):
            if 0.1 <= d.get('confidence', 0.0) <= threshold:
                results.append({
                    "source": u,
                    "target": v,
                    **d
                })
        return results

    def get_suspended_beliefs(self) -> List[Dict[str, Any]]:
        """Return beliefs that are highly uncertain or marked as suspended (< 0.1)."""
        results = []
        for u, v, d in self.graph.edges(data=True):
            if d.get('confidence', 0.0) < 0.1:
                results.append({
                    "source": u,
                    "target": v,
                    **d
                })
        return results

    def decay(self, rate: float = 0.001):
        """Time-based belief decay."""
        now = time.time()
        to_remove = []
        for u, v, d in self.graph.edges(data=True):
            age_hours = (now - d.get('last_updated', now)) / 3600.0
            decay_amount = rate * age_hours
            if decay_amount > 0:
                d['confidence'] = max(0.01, d.get('confidence', 0.5) - decay_amount)
                if d['confidence'] < 0.02:
                    to_remove.append((u, v))
        
        for u, v in to_remove:
            self.graph.remove_edge(u, v)
            
        if to_remove:
            self._save()
            logger.info("Belief decay: %d beliefs dissolved", len(to_remove))

    def get_summary(self) -> Dict[str, Any]:
        """Status overview of the world model."""
        return {
            "total_beliefs": self.graph.number_of_edges(),
            "entities": self.graph.number_of_nodes(),
            "strong": len(self.get_strong_beliefs(0.8)),
            "weak": len(self.get_weak_beliefs(0.3)),
        }

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            # Serialization of NetworkX graph to simple dict for JSON
            data = {
                "nodes": {n: self.graph.nodes[n] for n in self.graph.nodes},
                "edges": []
            }
            for u, v, d in self.graph.edges(data=True):
                data["edges"].append({"source": u, "target": v, **d})
                
            with open(self._persist_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save world model: %s", e)

    def _load(self):
        try:
            if os.path.exists(self._persist_path):
                with open(self._persist_path, "r") as f:
                    data = json.load(f)
                
                # Restore nodes
                for node_id, attrs in data.get("nodes", {}).items():
                    self.graph.add_node(node_id, **attrs)
                
                # Restore edges
                for edge in data.get("edges", []):
                    source = edge.pop("source")
                    target = edge.pop("target")
                    self.graph.add_edge(source, target, **edge)
                    
                logger.info("Loaded %d beliefs from disk", self.graph.number_of_edges())
        except Exception as e:
            logger.warning("Failed to load world model: %s", e)


# Global Instance
belief_graph = BeliefGraph()

def get_belief_graph():
    """Get global belief graph instance"""
    return belief_graph

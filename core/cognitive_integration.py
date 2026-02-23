
"""core/cognitive_integration.py — Aura Cognitive Integration Layer
=================================================================
Connects all five new modules into Aura's existing orchestrator.

Drop-in integration guide:

  1. Add this to core/orchestrator.py __init__:
        from core.cognitive_integration import CognitiveIntegrationLayer
        self.cognition = CognitiveIntegrationLayer(orchestrator=self)
        await self.cognition.initialize()

  2. In your main processing loop (wherever you call brain.think()):
        enhanced_context = await self.cognition.build_enhanced_context(user_input)
        
        # Check for value conflicts before processing
        refusal = self.cognition.check_values(user_input)
        if refusal:
            return refusal.to_response()
        
        # Generate response
        response = await brain.think(enhanced_context)
        
        # Record for learning
        self.cognition.record_interaction(user_input, response, domain="general")

  3. After you receive feedback (explicit or inferred):
        self.cognition.record_feedback(exp_id, quality=0.8)

The integration adds approximately 50-150ms overhead per request
(mostly from DB reads for context building), negligible on modern hardware.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.continuous_learning import ContinuousLearningEngine
from core.dual_memory import DualMemorySystem
from core.embodiment import ContinuousSensoryFeed, get_embodiment_system
from core.uncertainty import EpistemicHumilityEngine
from core.values_engine import IntegratedIdentitySystem
from core.world_model.belief_graph import get_belief_graph

logger = logging.getLogger("Core.CognitiveIntegration")


class CognitiveIntegrationLayer:
    """The integration layer that wires all cognitive modules together.
    """
    
    def __init__(self, orchestrator=None, base_data_dir: str = "data"):
        self.orchestrator = orchestrator
        self.base_dir = base_data_dir
        
        # Unified Belief Graph
        self.beliefs = get_belief_graph()

        from core.container import ServiceContainer
        self.memory = ServiceContainer.get("memory_facade")
        if not self.memory:
             from core.memory.memory_facade import MemoryFacade
             # Provide fallback or specific initialization if service not yet ready
             from core.dual_memory import DualMemorySystem
             self.memory = DualMemorySystem(f"{base_data_dir}/memory")
             logger.warning("memory_facade service not found, falling back to local DualMemorySystem")

        self.epistemic = EpistemicHumilityEngine()
        
        try:
             self.identity = IntegratedIdentitySystem(base_dir=base_data_dir)
        except ImportError:
             logger.warning("IntegratedIdentitySystem missing, running in degraded continuous learning mode.")
             self.identity = None
        except Exception:
             # Fallback
             self.identity = None

        self.sensory = ContinuousSensoryFeed()
        self.embodiment = get_embodiment_system()
        self.learning = ContinuousLearningEngine(
            f"{base_data_dir}/learning", 
            brain=orchestrator.cognitive_engine if orchestrator else None
        )
        
        # State tracking
        self._current_exp_id: Optional[str] = None
        self._last_context_build = 0.0
        self._session_start = time.time()
        
        logger.info("CognitiveIntegrationLayer constructed")
    
    async def initialize(self):
        """Full initialization — call once after construction.
        Seeds beliefs, starts sensory feeds, loads identity context.
        """
        logger.info("Initializing cognitive integration layer...")
        
        # 1. Initialize sub-systems that have async boot requirements
        if hasattr(self.memory, 'initialize') and asyncio.iscoroutinefunction(self.memory.initialize):
            await self.memory.initialize()
            
        if hasattr(self.embodiment, 'initialize') and asyncio.iscoroutinefunction(self.embodiment.initialize):
            await self.embodiment.initialize()

        if self.identity and hasattr(self.identity, 'initialize') and asyncio.iscoroutinefunction(self.identity.initialize):
             await self.identity.initialize()

        # Seed core beliefs if graph is empty
        if self.beliefs and self.beliefs.graph.number_of_edges() < 2:
             logger.info("Universal seeding of core beliefs via graph...")
             # BeliefGraph seeds itself (AURA_SELF), but we can add bootstrap knowledge here
             self.beliefs.update_belief("Aura", "is", "sovereign", 0.9)
             self.beliefs.update_belief("User", "is", "collaborator", 0.8)
        
        # Start sensory feeds (non-blocking, background)
        if hasattr(self.sensory, 'start') and asyncio.iscoroutinefunction(self.sensory.start):
            await self.sensory.start()
        
        # Register conversation text as sensory input
        # (This is how conversations enter the embodied context)
        
        logger.info("Cognitive integration layer initialized and running")
    
    async def build_enhanced_context(self, user_input: str,
                                      domain: str = "general",
                                      emotional_context: float = 0.0) -> str:
        """Build the full enhanced context for the cognitive engine.
        
        This is the core function. Call this instead of sending raw user_input
        to the brain. The returned string wraps the input with all relevant
        cognitive context.
        
        Returns a formatted context string to prepend to the user's message.
        """
        # Feed user input into sensory system
        self.sensory.inject_text_observation(
            user_input, 
            emotional_valence=emotional_context
        )
        
        # Parallel context building for efficiency
        context_tasks = await asyncio.gather(
            self._get_identity_context(),
            self._get_memory_context(user_input, emotional_context),
            self._get_belief_context(user_input),
            self._get_learning_context(user_input, domain),
            return_exceptions=True
        )
        
        identity_ctx, memory_ctx, belief_ctx, learning_ctx = context_tasks
        embodied_ctx = self.sensory.get_embodied_context()
        
        # Process any new claims in the input
        if self.beliefs:
             asyncio.create_task(
                 asyncio.to_thread(
                     self.beliefs.update_belief,
                     source="User",
                     relation="observed_input",
                     target=user_input[:50],
                     confidence_score=0.3
                 )
             )
        
        # Also store as episodic memory
        self.memory.store_experience(
            description=f"User said: {user_input[:150]}",
            emotional_valence=emotional_context,
            importance=0.5
        )
        
        # Assemble context block with hard character limits (v6.1 Rigor)
        # Total budget for context is ~4000 chars to leave room for history and reasoning
        context_parts = []
        
        if not isinstance(identity_ctx, Exception) and identity_ctx:
            context_parts.append(identity_ctx[:1000]) # Identity is high priority
        
        if not isinstance(embodied_ctx, Exception) and embodied_ctx:
            context_parts.append(embodied_ctx[:500])
        
        if not isinstance(memory_ctx, Exception) and memory_ctx:
            context_parts.append(memory_ctx[:1500]) # RAG is medium priority
        
        if not isinstance(belief_ctx, Exception) and belief_ctx:
            context_parts.append(belief_ctx[:1000])
        
        if not isinstance(learning_ctx, Exception) and learning_ctx:
            context_parts.append(learning_ctx[:1000])
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    async def _get_identity_context(self) -> str:
        """Get identity and values context."""
        try:
            if not self.identity: return ""
            return self.identity.get_full_system_prompt_injection()
        except Exception as e:
            logger.error("Identity context failed: %s", e)
            return ""
    
    async def _get_memory_context(self, query: str, emotional_context: float) -> str:
        """Get relevant memories."""
        try:
            # Recall (semantic)
            recall_data = await self.memory.retrieve_unified_context(query) if hasattr(self.memory, "retrieve_unified_context") else ""
            return recall_data
        except Exception as e:
            logger.error("Memory context failed: %s", e)
            return ""
    
    async def _get_belief_context(self, query: str) -> str:
        """Get relevant belief state and Latent Seed Thoughts from unified graph."""
        try:
            if not self.beliefs: return ""
            
            # 1. Fetch Strong Beliefs
            strong = self.beliefs.get_strong_beliefs(0.7)
            summary = "\n".join([f"- {b['source']} {b['relation']} {b['target']}" for b in strong[:5]])
            
            # 2. Phase 16.3: Fetch Latent Seed Thoughts (Compressed Narrative)
            seeds = []
            for u, v, d in self.beliefs.graph.edges(data=True):
                if d.get('relation') == "latent_seed_thought":
                    seeds.append(v)
            
            seed_context = ""
            if seeds:
                # Take the most recent seeds
                recent_seeds = "\n".join([f"• {s}" for s in seeds[-3:]])
                seed_context = f"\nLATENT NARRATIVE SEEDS:\n{recent_seeds}"
            
            return f"BELIEFS:\n{summary}{seed_context}" if (summary or seed_context) else ""
        except Exception as e:
            logger.error("Belief context failed: %s", e)
            return ""
    
    async def _get_learning_context(self, query: str, domain: str) -> str:
        """Get relevant learned patterns."""
        try:
            return await self.learning.get_relevant_patterns(query, domain=domain)
        except Exception as e:
            logger.error("Learning context failed: %s", e)
            return ""
    
    def check_values(self, request: str,
                     context: Dict = None):
        """Check request against values. Returns RefusalDecision or None.
        
        This REPLACES should_override_ethics(). 
        Values are not overridden — conflicts are explained and refused.
        """
        if not self.identity: return None
        return self.identity.values.evaluate_request(request, context)
    
    def assess_response(self, query: str, response_draft: str) -> Tuple[str, float]:
        """Assess a draft response for epistemic quality.
        Returns (wrapped_response, confidence).
        """
        profile = self.epistemic.assess(query, response_draft)
        wrapped = self.epistemic.wrap_response(response_draft, profile)
        return wrapped, profile.confidence
    
    def record_interaction(self, user_input: str, response: str,
                           domain: str = "general", strategy: str = "default") -> str:
        """Record an interaction for learning. Returns experience ID.
        Store this and use it to provide feedback later.
        """
        exp_id = self.learning.record_interaction(
            input_text=user_input,
            response_text=response,
            domain=domain,
            strategy=strategy
        )
        self._current_exp_id = exp_id
        
        # Also store response as episodic memory
        self.memory.store_experience(
            description=f"I responded: {response[:150]}",
            importance=0.4
        )
        
        return exp_id
    
    def record_feedback(self, exp_id: str, quality: float,
                        corrections: List[str] = None):
        """Record outcome feedback for a previous interaction."""
        self.learning.record_feedback(exp_id, quality, corrections)
    
    def infer_feedback_from_followup(self, followup: str):
        """Passively infer feedback from the next message."""
        if self._current_exp_id:
            self.learning.infer_feedback_from_context(
                self._current_exp_id, followup
            )
    
    def add_semantic_learning(self, concept: str, predicate: str, value: str,
                               confidence: float, domain: str = "general"):
        """Explicitly add a semantic fact from an interaction."""
        self.memory.learn_fact(concept, predicate, value, confidence, domain)
    
    async def get_full_status(self) -> Dict[str, Any]:
        """Comprehensive status of all cognitive systems."""
        status = {
            "session_age_seconds": time.time() - self._session_start,
            "learning": self.learning.get_learning_report(),
            "memory": self.memory.get_memory_stats(),
            "epistemic": self.epistemic.introspect(),
            "sensory": self.sensory.get_channel_status(),
        }

        if self.beliefs:
             status["beliefs"] = {
                "active": len([b for b in self.beliefs.beliefs if b.confidence > 0.5]),
                "suspended": 0, # Not currently tracked in simple list
                "pending_contradictions": 0 # Not currently tracked
            }

        if self.identity:
             status["identity"] = {
                "name": self.identity.identity._state.get("name"),
                "worldview_evolutions": len(
                    self.identity.identity._state.get("worldview_evolution_log", [])
                )
            }
        return status
    
    def get_ui_snapshot(self) -> Dict[str, Any]:
        """Fast, lightweight status for UI telemetry (polled frequently).
        """
        snapshot = {}
        
        # Embodiment (Thermodynamics)
        if self.embodiment:
            # Run a tick to keep it alive
            self.embodiment.update() 
            snapshot["embodiment"] = {
                "energy": self.embodiment.energy,
                "heat": self.embodiment.heat,
                "integrity": self.embodiment.integrity
            }
            
        # Identity / Values
        if self.identity:
            snapshot["values"] = self.identity.values.get_active_weights()
            
        return snapshot

    async def reflect_on_session(self) -> str:
        """Generate a meta-cognitive reflection on this session.
        What was learned? What was uncertain? What should change?
        """
        report = await self.get_full_status()
        memory_summary = self.memory.get_salient_history()
        
        reflection_parts = [
            f"[Session Reflection — {int(report['session_age_seconds']/60)} minutes]",
            "",
            f"Interactions recorded: {report['learning']['total_experiences']}",
            f"Memories: {report['memory']['episodic_memories']} episodic, {report['memory']['semantic_facts']} semantic",
            "",
            "Most significant memories this session:",
            memory_summary,
            "",
            "Open contradictions requiring resolution:",
        ]
        
        if self.beliefs and 'beliefs' in report:
            # Current BeliefSystem doesn't track pending contradictions queue yet
            reflection_parts.append("  (Contradiction tracking not yet implemented in v7.0 BeliefSystem)")
        
        return "\n".join(reflection_parts)

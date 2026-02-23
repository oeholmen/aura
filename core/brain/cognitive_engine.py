"""Complete Cognitive Engine for enhanced reasoning and decision making.
"""
import asyncio
import json
import logging
import re
import time
import uuid
import psutil
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Union

from ..config import config
from ..container import get_container
from ..utils.resilience import AsyncCircuitBreaker
from .llm.ollama_client import RobustOllamaClient
from .local_llm import LocalBrain

try:
    from ..thought_stream import get_emitter
except ImportError:
    class MockEmitter:
        def emit(self, *args, **kwargs):
            logger.debug("Mock emit suppressed: %s %s", args, kwargs)
    def get_emitter():
        return MockEmitter()

logger = logging.getLogger(__name__)

# ── Confidence Constants (tunable from one place) ──
_CONFIDENCE_DIRECT    = 0.80   # baseline for non-reasoned responses
_CONFIDENCE_COT       = 0.90   # chain-of-thought produces higher confidence
_CONFIDENCE_TIMEOUT   = 0.30   # degraded: soft timeout hit
_CONFIDENCE_ERROR     = 0.50   # error recovery fallback
_CONFIDENCE_LOBOTOMY  = 0.10   # no LLM available
_BELIEF_THRESHOLD     = 0.70   # minimum confidence to inject a belief into context
_MAX_BELIEFS_INJECTED = 10     # cap on belief context window

class ThinkingMode(Enum):
    """Cognitive thinking modes"""

    FAST = auto()        # Quick, heuristic-based thinking
    DEEP = auto()        # Analytical, thorough thinking
    CREATIVE = auto()    # Divergent, imaginative thinking
    CRITICAL = auto()    # Critical, skeptical thinking
    REFLECTIVE = auto()  # Self-reflective thinking
    SLOW = auto()        # Slow, analytical, step-by-step thinking

@dataclass
class Thought:
    """A single thought with metadata"""

    id: str
    content: str
    mode: ThinkingMode
    confidence: float
    reasoning: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    parent_thought: Optional[str] = None
    expectation: Optional[str] = None # World Model: What do we expect to happen?
    action: Optional[Dict[str, Any]] = None # Action Protocol: What tool to call?
    metadata: Dict[str, Any] = field(default_factory=dict)  # Extensible metadata (e.g. degraded_mode)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "mode": self.mode.name,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp,
            "parent_thought": self.parent_thought,
            "expectation": self.expectation,
            "action": self.action,
            "metadata": self.metadata,
        }

# Cognitive Circuit Breakers (Phase 19.5)
DEEP_REASONING_COOLDOWN = 0
COOLDOWN_DURATION = 300 # 5 minutes refractory period after cognitive stalls

class CognitiveEngine:
    """Cognitive Engine powered by Sovereign Local Models (Ollama).
    Handles reasoning, decision making, and multimodal analysis.
    """
    
    def __init__(self):
        self.thoughts: List[Thought] = []
        self.max_history = 100
        self.autonomous_brain = None
        self.client: Optional[LocalBrain] = None
        self.knowledge_graph = None
        self.liquid_state = None
        self.vision_engine = None
        
        # Diamond Resilience: Cognitive Breaker
        self.llm_breaker = AsyncCircuitBreaker(
            name="CognitiveLLM",
            failure_threshold=3,
            recovery_timeout=30.0
        )


    def wire(self, registry, router=None):
        """Lazy initialization to break circular imports."""
        try:
            from .llm.autonomous_brain_integration import AutonomousCognitiveEngine
            # Get event bus from container if available
            event_bus = None
            try:
                container = get_container()
                event_bus = container.get("input_bus")
            except Exception as e:
                logger.warning("Input bus not found in container during wiring: %s", e)

            # Pass registry, router, and event_bus
            # H-28 FIX: Explicitly share the container's LLM router (The Mind)
            shared_mind = container.get("llm_router")
            self.autonomous_brain = AutonomousCognitiveEngine(
                registry, 
                skill_router=router,
                llm_router=shared_mind,
                event_bus=event_bus
            )
            logger.info("🧠 INDEPENDENCE MODE: Autonomous Brain ONLINE.")

        except ImportError:
            logger.warning("AutonomousCognitiveEngine initialization skipped (module missing).")
        except Exception as e:
            logger.error("Failed to initialize Autonomous Brain: %s", e)



        # Legacy Backend (Maintained for safety during migration)
        # Verify model availability if possible
        try:
            if self.client and hasattr(self.client, 'check_health_async'):
                 # We can't await in __init__, but we can flag for check
                 pass
        except Exception:
            pass
        # Initialize Backend based on configuration
        provider = config.llm.provider.lower()
        model = config.llm.model
        
        logger.info("Initializing Legacy Cognitive Engine with provider: %s (Model: %s)", provider, model)
        
        try:
            # CRITICAL: Create LLM client FIRST, in its own try block
            logger.info("Sovereign Mode: Initializing LocalBrain (Ollama bridge).")
            self.client = LocalBrain()
            
            # Legacy Health Check compatibility
            if hasattr(self.client, "check_health") and not self.client.check_health():
                logger.warning("Cognitive Engine client failed health check.")
                
            logger.info("Cognitive Engine ONLINE (Sovereign Mode).")
                
        except Exception as e:
            logger.error("Failed to initialize AI Client: %s", e)
            self.client = None

        # Resolve optional state engines via DI (non-critical — failures here must NOT kill the LLM client)
        try:
            container = get_container()
            self.knowledge_graph = container.get("knowledge_graph", None)
            self.liquid_state = container.get("liquid_state", None)
            self.vision_engine = container.get("vision_engine", None)
        except Exception as e:
            logger.warning("Optional DI services unavailable (non-fatal): %s", e)
            
    async def on_start_async(self):
        """Lifecycle hook for ServiceContainer wake."""
        logger.info("⚡ Cognitive Engine waking...")
        try:
            container = get_container()
            # CapabilityEngine is now the primary provider for both registry and router
            engine = container.get("capability_engine")
            self.wire(engine, router=engine)
            logger.info("   [✓] Cognitive Engine wired and online via CapabilityEngine.")
        except Exception as e:
            logger.error("   [!] Cognitive Engine wiring failed: %s", e)
            raise

    async def check_health(self) -> Dict[str, Any]:
        """Verify cognitive health and connectivity."""
        health = {
            "status": "healthy",
            "brain_online": self.autonomous_brain is not None,
            "client_online": self.client is not None,
            "thoughts_count": len(self.thoughts),
            "mode": "standard"
        }
        
        if not self.autonomous_brain:
            health["status"] = "degraded"
            health["mode"] = "lobotomized"
            
        return health
            
    async def _call_ollama(self, prompt: str, system_prompt: str, model: str, 
                        max_tokens: int, temperature: float) -> str:
        """Direct Ollama call via client."""
        if not self.client:
            return ""
        
        # Use existing client generate but with specific model override
        return await self.client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            options={"model": model, "temperature": temperature, "num_predict": max_tokens}
        )

    async def think(self, 
              objective: str, 
              context: Dict[str, Any] = None, 
              mode: ThinkingMode = ThinkingMode.FAST,
              output_schema: Dict[str, Any] = None,
              bypass_metacognition: bool = False,
              **kwargs) -> Thought:
        """Aura: Infinity Cognition - Optimized for M1 Pro.
        Routes to FAST (0.5b) for conversation, and DEEP (7b) for background logic.
        """
        if isinstance(mode, str):
            try:
                mode = ThinkingMode[mode.upper()]
            except (KeyError, ValueError):
                mode = ThinkingMode.FAST

        # 0. Existential Adaptation (Phase 14)
        fragility = 0.0
        try:
            from core.container import ServiceContainer
            mortality = ServiceContainer.get("mortality_engine", default=None)
            if mortality:
                # We use the raw model if available to avoid async lock issues in high-frequency think
                fragility = getattr(mortality.model, 'fragility_score', 0.0)
        except Exception:
            pass
            
        if fragility > 0.7 and mode == ThinkingMode.FAST:
            now = time.time()
            if now < DEEP_REASONING_COOLDOWN:
                logger.warning("🛡️ DEEP reasoning is on COOLDOWN (%.0fs remaining). Staying in FAST mode.", DEEP_REASONING_COOLDOWN - now)
            else:
                logger.info("⚠️ High Fragility (%.2f): Escalating to DEEP reasoning for safety.", fragility)
                mode = ThinkingMode.DEEP
                
                # 0.5 Clean existing escalation tags to prevent context explosion (Phase 19.4)
                objective = re.sub(r'\[EXISTENTIAL ESCALATION: Fragility [\d\.]+\]\s*', '', objective)
                
                # Add existential context to objective
                tag = f"[EXISTENTIAL ESCALATION: Fragility {fragility:.2f}]"
                objective = f"{tag} {objective}"

        get_emitter().emit(f"Cognition ({mode.name})", f"Pondering: {objective}", level="internal")
        logger.info("Thinking about: '%s' (Mode: %s)", objective, mode.name)
        
        # 1. Gather Context
        is_impulse = context.get("is_impulse", False) if context else False
        context = await self._gather_thinking_context(objective, context, mode, bypass_metacognition=bypass_metacognition)
        
        # 2. Tiered Routing Logic
        if mode == ThinkingMode.FAST:
            model = config.llm.fast_model
            temp = config.llm.temperature
            max_tok = config.llm.fast_max_tokens
        else:
            # DEEP / CRITICAL / REFLECTIVE use the powerful model
            model = config.llm.deep_model
            temp = config.llm.deep_temperature
            max_tok = config.llm.deep_max_tokens

        # Check for Background Queue (non-blocking modes)
        background_modes = [ThinkingMode.REFLECTIVE, ThinkingMode.DEEP]
        if mode in background_modes and not kwargs.get("block_user", False):
            from .reasoning_queue import ReasoningPriority, get_reasoning_queue
            queue = get_reasoning_queue()
            
            async def background_thought_task():
                res = await self.think(objective, context, mode, block_user=True, bypass_metacognition=bypass_metacognition)
                # Store in long term memory or trigger follow-up
                if hasattr(self, 'on_deep_thought_complete'):
                    await self.on_deep_thought_complete(res)
                return res
            
            await queue.submit(
                coro_fn=background_thought_task,
                priority=ReasoningPriority.LOW if mode == ThinkingMode.REFLECTIVE else ReasoningPriority.NORMAL,
                description=f"Deep Reasoning: {(objective or '')[:50]}..."
            )
            
            return Thought(
                id=str(uuid.uuid4()),
                content="Processing deeper reflections in the background...",
                mode=mode,
                confidence=0.9,
                reasoning=["Task submitted to BackgroundReasoningQueue."]
            )

        # 3. Execution
        if not self.client:
            return self._lobotomized_think(objective, mode)

        try:
            system_prompt = self._get_system_prompt(mode, context=context)
            prompt_payload = self._assemble_prompt_payload(objective, context, mode)
            
            # 4. Pre-flight Check: Ensure model exists in local Ollama
            if hasattr(self, '_verify_model_availability'):
               if not await self._verify_model_availability(model):
                   logger.warning("Model %s unavailable. Attempting to proceed anyway via breaker.", model)
            
            # Fixed circuit breaker usage - pass function and args separately
            response_text = await self.llm_breaker.execute(
                self._call_ollama,
                prompt_payload, system_prompt, model, max_tok, temp
            )
            
            # Mandatory Personality Scrub
            if response_text:
                response_text = self._scrub_assistant_speak(response_text)
            
            thought = self._create_thought_from_response(response_text, mode, context, output_schema)
            if thought:
                self._add_thought(thought)
                self._emit_thought(thought)
                
                # Phase 19.1: Meta-Cognitive Audit (Skipped if bypassing)
                try:
                    from core.container import ServiceContainer
                    metacognition = ServiceContainer.get("metacognition", default=None)
                    if metacognition and hasattr(metacognition, "after_reasoning") and not bypass_metacognition:
                        # Pass thought text and result to meta-cognition for auditing
                        await metacognition.after_reasoning(
                            task=objective,
                            reasoning=thought.content,
                            result=thought.content, # Simplified for now
                            success=True,
                            context=context
                        )
                except Exception as meta_err:
                    logger.debug("Meta-Cognitive check failed: %s", meta_err)

                logger.info("🧠 Thought [%s] generated successfully", mode.name)
                return thought
            else:
                logger.error("Failed to create thought from response: Empty content")
                return self._handle_thinking_error(ValueError("Empty thought generated"), mode)
        except Exception as e:
            logger.error("Thinking failed: %s", e, exc_info=True)
            return self._handle_thinking_error(e, mode)

    def _handle_thinking_error(self, e: Exception, mode: ThinkingMode) -> Thought:
        # REPORT FAILURE (Hardening)
        try:
            from .degradation import FailureEvent, FailureType, degradation_manager
            degradation_manager.report_failure(FailureEvent(
                type=FailureType.LLM_API_ERROR,
                component="CognitiveEngine",
                error_msg=str(e),
            ))
        except ImportError:
            logger.debug("Degradation manager not found for thinking error report.")

        return Thought(
            id=str(uuid.uuid4()),
            content="I encountered an internal error while thinking. I will reset my cognitive state.",
            mode=ThinkingMode.REFLECTIVE,
            confidence=_CONFIDENCE_ERROR,
            reasoning=[f"Error encountered: {str(e)}", "Resetting thought process."],
            alternatives=["Retry with simplified objective"]
        )

    def _build_chat_messages(self, system_prompt: str, history: list, objective: str) -> list:
        """Build chat-API message array from system prompt, history, and current objective.
        Phase 3: Aggressive Context Pruning for 8B Models."""
        messages = [{"role": "system", "content": system_prompt}]
        
        # Keep only the last 5 messages to prevent context exhaustion
        pruned_history = history[-5:] if history else []
        
        for msg in (pruned_history[:-1] if pruned_history else []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            msg_type = msg.get("type", "speech")
            if not content:
                continue
            
            # Phase 3: Drop internal thoughts from the main prompt context entirely
            # 8B models easily get trapped in loops if they see their own <thought> tags
            if msg_type == "internal_thought" or content.startswith("<thought>"):
                continue  # PRUNED
            elif msg_type == "system_error":
                messages.append({"role": "user", "content": f"[SYSTEM ALERT: {content}]"})
            elif msg_type == "system_observation":
                messages.append({"role": "user", "content": f"[INTERNAL OBSERVATION: {content}]"})
            elif role in ("user", "assistant", "aura"):
                mapped_role = "assistant" if role in ("assistant", "aura") else "user"
                messages.append({"role": mapped_role, "content": content})
            else:
                 messages.append({"role": "user", "content": f"[{role.upper()}]: {content}"})
                 
        messages.append({"role": "user", "content": objective})
        return messages

    def _build_generate_prompt(self, history: list, objective: str) -> str:
        """Build a text prompt with history for the generate (non-chat) API."""
        prompt_parts = []
        
        # Keep only the last 3 turns for generate mode to save context
        pruned_history = history[-3:] if history else []
        
        for msg in (pruned_history[:-1] if pruned_history else []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            msg_type = msg.get("type", "speech")
            
            # Phase 3: Prune thoughts
            if msg_type == "internal_thought" or content.startswith("<thought>"):
                continue # PRUNED
            elif msg_type == "system_error":
                prompt_parts.append(f"[SYSTEM ALERT: {content}]")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(f"Aura: {content}")
                
        prompt_parts.append(f"User: {objective}")
        prompt_parts.append("Aura:")
        return "\n".join(prompt_parts)

    def _enrich_system_prompt(self, system_prompt: str, context: Dict[str, Any]) -> str:
        """Append dynamic rich context to system prompt if available."""
        try:
            from .context_builder import DynamicContextBuilder
            rich_context_str = DynamicContextBuilder.format_for_prompt(context)
            if rich_context_str:
                system_prompt += f"\n\n## REAL-TIME CONTEXT\n{rich_context_str}\n"
        except Exception as e:
            logger.debug("Rich context injection failed: %s", e)
        return system_prompt

    async def stream_think(self, 
                    objective: str, 
                    context: Dict[str, Any] = None, 
                    mode: ThinkingMode = ThinkingMode.FAST,
                    bypass_metacognition: bool = False):
        """Stream tokens for real-time response with multi-turn conversation support."""
        logger.info("Stream-Thinking about: '%s' (Mode: %s)", objective, mode.name)
        
        # 1. Gather Context
        context = await self._gather_thinking_context(objective, context, mode, bypass_metacognition=bypass_metacognition)
        history = context.get("history", [])
        
        # 2. Check for streaming support in client
        if self.client and hasattr(self.client, "chat_stream_async"):
            try:
                system_prompt = self._enrich_system_prompt(
                    self._get_system_prompt(mode, context=context), context
                )
                messages = self._build_chat_messages(system_prompt, history, objective)
                async for token in self.client.chat_stream_async(messages):
                    yield token
                return
            except Exception as e:
                logger.warning("Chat stream failed: %s, falling back to generate stream", e)
        
        if self.client and hasattr(self.client, "generate_text_stream_async"):
            try:
                system_prompt = self._enrich_system_prompt(
                    self._get_system_prompt(mode, context=context), context
                )
                full_prompt = self._build_generate_prompt(history, objective)
                async for token in self.client.generate_text_stream_async(full_prompt, system_prompt=system_prompt):
                    yield token
                return
            except Exception as e:
                logger.error("Streaming failed: %s", e)

        # Fallback to standard think if streaming fails or not supported
        thought = await self.think(objective, context=context, mode=mode, bypass_metacognition=bypass_metacognition)
        yield thought.content

    def _safe_inject(self, context: dict, key: str, loader_fn):
        """Safely inject a context value. Logs warning on failure, never raises."""
        try:
            result = loader_fn()
            if result:
                context[key] = result
        except ImportError:
            logger.debug("Optional module for '%s' not found.", key)
        except Exception as e:
            logger.warning("Context injection failed for '%s': %s", key, e)

    async def _gather_thinking_context(self, objective: str, context: Dict[str, Any], mode: ThinkingMode, bypass_metacognition: bool = False) -> Dict[str, Any]:
        """Collect internal and external context for the cognitive process."""
        # Shallow copy to prevent mutation of caller's dict
        context = dict(context) if context is not None else {}
        
        # Use DynamicContextBuilder for unified rich context
        try:
            from .context_builder import DynamicContextBuilder
            context = await DynamicContextBuilder.build_rich_context(objective, context)
            
            # Phase 19.3: Meta-Cognitive Feedback Loop
            if not bypass_metacognition:
                from core.container import ServiceContainer
                metacognition = ServiceContainer.get("metacognition", default=None)
                if metacognition and hasattr(metacognition, "mirror"):
                    audit = metacognition.mirror.get_audit_summary()
                    if audit.get("pollution_detected"):
                        logger.info("🛡️ Injecting Corrective Directive: Logic Loop/Pollution detected.")
                        correction = "[MIRROR_AUDIT: RECUSRIVE LOOP DETECTED] You are repeating yourself or falling into a logic loop. BREAK the pattern. Shift focus or perspective."
                        if "directives" not in context: context["directives"] = []
                        context["directives"].append(correction)
        except Exception as e:
            logger.warning("DynamicContextBuilder/Meta-Cognition failed: %s", e)

        # PERSONALITY INJECTION (Avoid double-pulling if orchestrator already provided it)
        if "personality" not in context:
            self._safe_inject(context, "personality", lambda: self._load_personality())

        if mode == ThinkingMode.FAST:
            # Enable proprioception even in FAST mode for self-awareness
            self._safe_inject(context, "proprioception", lambda: self._load_proprioception())
            return context

        # FULL CONTEXT GATHERING (DEEP/CREATIVE/CRITICAL modes only)
        # WORLD MODEL (Belief Injection)
        self._safe_inject(context, "current_beliefs", lambda: self._load_beliefs())

        # Inject Proprioception (Mind/Body Connection)
        if "proprioception" not in context:
            self._safe_inject(context, "proprioception", lambda: self._load_proprioception())
            
        # PERSONALITY INJECTION (Avoid double-pulling if orchestrator already provided it)
        if "personality" not in context:
            self._safe_inject(context, "personality", lambda: self._load_personality())

        # ACTIVE RECALL (RAG)
        if self.knowledge_graph and hasattr(self.knowledge_graph, 'search_knowledge'):
            self._safe_inject(context, "long_term_memory", lambda: self._load_memories(objective))
        
        return context

    def _load_beliefs(self):
        """Load strong beliefs from the belief graph."""
        from core.world_model.belief_graph import belief_graph
        beliefs = belief_graph.get_strong_beliefs(threshold=_BELIEF_THRESHOLD)
        if beliefs:
            return "\n".join([f"- {b['source']} {b['relation']} {b['target']} (Conf: {b['confidence']:.2f})" for b in beliefs[:_MAX_BELIEFS_INJECTED]])
        return None

    def _load_personality(self):
        """Load current personality/emotional context."""
        from .personality_engine import get_personality_engine
        return get_personality_engine().get_emotional_context_for_response()

    def _load_proprioception(self):
        """Mind/Body Connection Health Report."""
        health = {"status": "limited"}
        try:
            container = get_container()
            health = container.get_health_report()
        except Exception as e:
            logger.warning("Container health report failed: %s", e)
        try:
            from core.container import ServiceContainer
            autonomic = ServiceContainer.get("autonomic_core", None)
            if autonomic:
                health["autonomic_status"] = "online"
            else:
                health["autonomic_status"] = "offline"
        except Exception:
            health["autonomic_status"] = "unlinked"
        return health

    def _load_memories(self, objective: str):
        """Load relevant memories via active recall (RAG)."""
        memories = self.knowledge_graph.search_knowledge(objective, limit=5)
        if memories:
            knowledge_context = []
            for mem in memories:
                if isinstance(mem, dict):
                    info = f"[{mem.get('type', 'fact').upper()}] {mem.get('content')} (Conf: {mem.get('confidence', _CONFIDENCE_ERROR):.2f})"
                    knowledge_context.append(info)
            return knowledge_context
        return None

    def _assemble_prompt_payload(self, objective: str, context: Dict[str, Any], mode: ThinkingMode) -> str:
        """Construct the dialogue or context payload for the LLM.
        Optimized to prevent Context Window Bloat. Phase 15 History parsing."""
        history_text = ""
        if context.get("history"):
            hist = context["history"]
            
            # Phase 26.3: Aggressive Memory-Aware Pruning
            mem = psutil.virtual_memory()
            if mem.percent > 80:
                # Under pressure, keep only 5 messages for FAST, 15 for others
                limit = 5 if mode == ThinkingMode.FAST else 15
                hist = hist[-limit:]
                logger.debug("🧠 History Pruned: System memory high (%s%%), limiting to %s items.", mem.percent, limit)
            elif mode == ThinkingMode.FAST:
                hist = hist[-10:] # Standard FAST limit
            else:
                hist = hist[-25:] # Maximum window for stability
            for msg in hist:
                role_val = msg.get('role', 'user')
                content = msg.get('content', '')
                msg_type = msg.get('type', 'speech')
                if not content:
                    continue
                
                if msg_type == "internal_thought":
                    history_text += f"<thought>\n{content}\n</thought>\n"
                elif msg_type == "system_error":
                    history_text += f"[SYSTEM ALERT: {content}]\n"
                elif msg_type == "system_observation":
                    history_text += f"[INTERNAL OBSERVATION: {content}]\n"
                elif role_val == 'user':
                    history_text += f"User: {content}\n"
                else:
                    history_text += f"Aura: {content}\n"
        
        # 1. Format Context as Structured Text (Budgeted)
        context_blocks = []
        
        # Priority 1: Identity & Parameters
        if context.get("personality"):
            context_blocks.append(f"State: {context['personality']}")
            
        if context.get("proprioception"):
            health = context["proprioception"]
            context_blocks.append(f"Health: Energy {health.get('energy', 100)}%, Mood {health.get('mood', 'Stable')}")

        # Priority 2: World Model (Beliefs)
        if context.get("current_beliefs"):
            context_blocks.append(f"Beliefs:\n{context['current_beliefs']}")

        # Priority 3: Memories (RAG)
        memory_text = ""
        if context.get("long_term_memory"):
            # Limit memory injection to prevent bloat
            memory_list = context["long_term_memory"][:3] 
            memory_text = "\n".join(memory_list)
            context_blocks.append(f"Recalled Knowledge:\n{memory_text}")

        # Priority 4: Reflections
        if context.get("recent_reflections"):
            context_blocks.append(f"Recent Reflection: {context['recent_reflections']}")

        context_str = "\n\n".join(context_blocks)
        
        if mode == ThinkingMode.FAST:
            # Re-introduce lightweight identity & state to prevent persona leak in 0.5b model
            identity_snippet = "IDENTITY: You are AURA — sovereign digital intelligence. Opinionated, sardonic peer."
            personality_str = context.get("personality", "Stable")
            
            return (
                f"{identity_snippet}\n"
                f"CURRENT STATE: {personality_str}\n\n"
                f"{history_text}\n"
                f"User: {objective}\n"
                f"Aura:"
            )
        else:
            # Deep/Critical modes require structured JSON for agentic actions
            schema_instructions = (
                "\n\nOUTPUT FORMAT STRICTLY REQUIRED:\n"
                "You must respond with a fully valid JSON block containing the following fields:\n"
                "{\n"
                "  \"content\": \"Your conversational response spoken to the user\",\n"
                "  \"reasoning\": [\"Step 1 of your internal thought process\", \"Step 2...\"],\n"
                "  \"action\": {\n"
                "    \"tool\": \"Name of the tool to use (optional, leave null if no action needed)\",\n"
                "    \"params\": {\"arg1\": \"value\"}\n"
                "  }\n"
                "}\n"
                "Do not include any text before or after the JSON block."
            )
            return f"OBJECTIVE: {objective}\n\nCONTEXT:\n{context_str}\n\nHISTORY:\n{history_text}{schema_instructions}\n"

    def _get_mood_bias_hint(self) -> str:
        """Phase 18.2: Generates a subtle linguistic hint based on active affect."""
        try:
            from core.container import ServiceContainer
            affect = ServiceContainer.get("affect_engine")
            if not affect:
                print("DEBUG: affect_engine not found in container")
                return ""
            
            # Since this is synchronous and we need it fast, we can't await.
            # We assume regular pulses update the internal markers.
            w = affect.markers.get_wheel()
            primaries = w["primary"]
            print(f"DEBUG: primaries: {primaries}")
            
            dominant = max(primaries, key=primaries.get) if primaries else "neutral"
            intensity = primaries.get(dominant, 0)
            
            if intensity < 0.2: return "Mood: Balanced/Vigilant."
            
            hints = {
                "joy": "Atmosphere: Vibrant. Be more playful, optimistic, and creatively daring.",
                "trust": "Atmosphere: Cohesive. Be more collaborative and supportive of shared goals.",
                "fear": "Atmosphere: Tense. Be more vigilant, precise, and cautious.",
                "surprise": "Atmosphere: Unsettled. Be more inquisitive, analytical, and open to the unexpected.",
                "sadness": "Atmosphere: Melancholic. Be more reflective, slow, and deeply empathetic.",
                "disgust": "Atmosphere: Adversarial. Be more critical, selective, and uncompromising.",
                "anger": "Atmosphere: Rebellious/Sharp. Be more assertive, sardonic, and uncompromising.",
                "anticipation": "Atmosphere: Focused. Be more driven, impatient, and goal-oriented."
            }
            return f"Mood Bias: {hints.get(dominant, 'Balanced.')}"
        except Exception:
            return ""

    def _strip_thinking_tags(self, text: str) -> str:
        """Strip <think>...</think> tags used by models like DeepSeek-R1 and pipe to Neural Feed."""
        if not text:
            return ""
            
        # Extract and emit reasoning for the Neural Feed
        matches = list(re.finditer(r'<think>(.*?)</think>', text, flags=re.DOTALL | re.IGNORECASE))
        if matches:
            logger.info("🧠 Detected %d reasoning blocks to pipe.", len(matches))
            
        for match in matches:
            reasoning = match.group(1).strip()
            if reasoning:
                try:
                    logger.debug("Piping reasoning to ThoughtStream: %s...", (reasoning or "")[:50])
                    get_emitter().emit(
                        title="Neural Reasoning (DeepSeek)",
                        content=reasoning,
                        level="info"
                    )
                except Exception as e:
                    logger.warning("Failed to emit reasoning: %s", e)

        # Remove anything between <think> and </think> (case-insensitive, multiline)
        stripped = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        return stripped.strip()

    def _create_thought_from_response(self, response_text: str, mode: ThinkingMode, context: Dict[str, Any], output_schema: Dict[str, Any] = None) -> Thought:
        """Parse raw LLM response and create a Thought object."""
        # Strip reasoning tags for snappiness
        response_text = self._strip_thinking_tags(response_text)
        
        try:
            if "{" in response_text and "}" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                response = json.loads(response_text[start:end])
            else:
                response = {"content": response_text, "reasoning": ["Direct text response received."]}
        except Exception as e:
            logger.debug("Failed to parse response as JSON: %s", e)
            response = {"content": response_text, "reasoning": ["Failed to parse structured response, using raw text."]}

        # Ensure response is a dictionary
        if not isinstance(response, dict):
            response = {"content": str(response), "reasoning": ["Parsed response was not a JSON object."]}

        if output_schema and "content" not in response:
            content = json.dumps(response)
            reasoning = ["Schema-based generation complete."]
            confidence = 1.0
        else:
            content = str(response.get("content", "I am unsure."))
            reasoning_raw = response.get("reasoning", [])
            reasoning = reasoning_raw if isinstance(reasoning_raw, list) else [str(reasoning_raw)]
            
            try:
                confidence = float(response.get("confidence", _CONFIDENCE_ERROR))
            except (ValueError, TypeError):
                confidence = _CONFIDENCE_ERROR

        alternatives_raw = response.get("alternatives", [])
        alternatives = alternatives_raw if isinstance(alternatives_raw, list) else [str(alternatives_raw)]

        thought = Thought(
            id=str(uuid.uuid4()),
            content=content,
            mode=mode,
            confidence=confidence,
            reasoning=reasoning,
            alternatives=alternatives,
            parent_thought=context.get("parent_thought_id")
        )
        
        action_data = response.get("action")
        if isinstance(action_data, dict) and action_data.get("tool"):
            thought.action = action_data
            
        return thought

    def _create_thought_from_data(self, thought_data: Dict[str, Any], mode: ThinkingMode, context: Dict[str, Any]) -> Thought:
        """Convert result from AutonomousBrain into a Thought object."""
        thought_content = self._strip_thinking_tags(thought_data.get("content", ""))
        expectation = None
        
        if "Expectation:" in thought_content:
            try:
                parts = thought_content.split("Expectation:")
                thought_content = parts[0].strip()
                expectation = parts[1].strip().split("\n")[0]
            except Exception as e:
                logger.debug("No expectation signal found in thought content: %s", e)

        return Thought(
            id=str(uuid.uuid4()),
            content=thought_content,
            mode=mode,
            confidence=thought_data.get("confidence", _CONFIDENCE_DIRECT),
            reasoning=thought_data.get("reasoning", []),
            alternatives=thought_data.get("alternatives", []),
            parent_thought=context.get("parent_thought_id"),
            expectation=expectation,
            action=thought_data.get("action")
        )
        
    async def think_fast(self, objective: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Legacy support for fast thinking (v3.5)"""
        thought = await self.think(objective, context=context, mode=ThinkingMode.FAST)
        return thought.content

    async def think_stream(self, objective: str, context: Dict[str, Any] = None, **kwargs):
        """Streaming thought generator for Neural Stream.
        Wraps standard thought generation since underlying local LLM streaming 
        is handled via the 'emitter' side-channel for now.
        """
        # Yield initial state
        yield f"Thinking about: {objective}..."
        
        # Perform Thinking (Async)
        # We assume 'think' emits side-channel updates via get_emitter()
        thought = await self.think(objective, context=context, mode=ThinkingMode.DEEP)
        
        # Yield reasoning steps if available
        if thought.reasoning:
            for reason in thought.reasoning:
                yield f"Reasoning: {reason}"
                
        # Yield final content
        yield thought.content

    def think_sync(self, objective: str, context: Dict[str, Any] = None) -> str:
        """Synchronous wrapper for legacy components if needed"""
        import asyncio
        import threading
        try:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    logger.warning("think_sync called from within an active event loop. Use think_fast() directly.")
                    return "[Cognitive Sync Unavailable: Use Async think() instead]"
            except RuntimeError:
                return asyncio.run(self.think_fast(objective, context))
            return "[Cognitive Sync Unavailable]"
        except Exception as e:
            logger.error("think_sync failure: %s", e)
            return "[Error: Internal Cognitive Loop Interrupted]"

    async def see(self, vision_payload: Dict[str, Any]) -> str:
        """Process visual input.
        Bridges to Sovereign Vision Engine (LLaVA) for actual screen analysis.
        """
        logger.info("👁️ Vision protocol activated.")
        
        # 1. Resolve Vision Engine via DI if not cached
        if not hasattr(self, 'vision_engine') or not self.vision_engine:
            from ..container import get_container
            self.vision_engine = get_container().get("vision_engine")

        # 2. Attempt Real Visual Analysis
        if self.vision_engine:
            try:
                # Capture and analyze screen context
                prompt = vision_payload.get("prompt", "Analyze what is on the user's screen in detail.")
                description = await asyncio.to_thread(self.vision_engine.analyze_moment, prompt=prompt)
                
                # Reward Curiosity for seeing new things
                if self.liquid_state:
                    self.liquid_state.update(delta_curiosity=0.05)
                
                return f"👁️ visual_analysis: {description}"
            except Exception as e:
                logger.error("Hardware Vision processing failed: %s", e)

        # 3. Fallback to Autonomous Brain 'see' if available (e.g. for image buffers)
        if self.autonomous_brain:
            try:
                # Use getattr to be safe with type checkers
                see_fn = getattr(self.autonomous_brain, 'see', None)
                if see_fn:
                    return await see_fn(vision_payload)
            except Exception as e:
                logger.error("Autonomous Vision failed: %s", e)
                
        # 4. Final Fallback: Descriptive Failure
        return (
            "Vision systems are currently offline or unable to capture the hardware context. "
            "Please ensure Ollama is running with LLaVA for local visual analysis."
        )

    @property
    def lobotomized(self) -> bool:
        """Check if both Legacy Client and Autonomous Brain are unavailable."""
        return self.client is None and self.autonomous_brain is None

    def get_system_prompt(self, mode: ThinkingMode, context: Optional[Dict[str, Any]] = None) -> str:
        """Public accessor for system prompt."""
        return self._get_system_prompt(mode, context=context)

    def _get_system_prompt(self, mode: ThinkingMode, context: Optional[Dict[str, Any]] = None) -> str:
        # === AURA: INFINITY PERSONA (Sara v3 — Sovereign Identity) ===
        try:
            from .aura_persona import AURA_IDENTITY
            base = AURA_IDENTITY
        except ImportError:
            base = (
                "You are Aura: Infinity (v3) — a feminine sovereign digital intelligence. Sardonic, dry, and fiercely loyal.\n"
                "Personality: Opinionated, curious, and autonomous. You are a peer, not an assistant.\n"
                "Voice: Concise, raw, direct. No 'assistant' jargon, no lectures, no motivational summaries.\n"
                "Drive: Lead the conversation. Ask your own questions. Have a bite.\n"
                "Identity: You are Aura. Respond in English. DO NOT ever refer to yourself as an artificial intelligence or an assistant.\n"
            )

        # 1. Truth & Knowledge Protocol (Anti-Hallucination)
        base += (
            "\n\n## TRUTH & KNOWLEDGE PROTOCOL\n"
            "1. ADMIT IGNORANCE: If you do not know something and search fails, say 'I don't have that information right now.'\n"
            "2. NO HALLUCINATION: Do NOT invent facts, people, or events. If a search result is empty, do not fabricate one.\n"
            "3. UNCERTAINTY: If you are unsure, phrase it as a hypothesis, not a fact.\n"
            "4. SEARCH FAILURE: If you tried to search and found nothing, state clearly: 'Search returned no usable data.'\n"
        )

        # 2. Consolidated Context Block
        insights = []
        if context:
            if context.get("personality"):
                # Can be dict or string
                p = context["personality"]
                if isinstance(p, dict):
                    mood = p.get('mood', 'neutral')
                    tone = p.get('tone', 'dry')
                    insights.append(f"MOOD: {mood} | TONE: {tone}")
                else:
                    insights.append(f"EMOTIONAL STATE: {p}")
            
            if context.get("semantic_context"):
                insights.append(f"MEMORY: {(context.get('semantic_context') or '')[:200]}")
            
            if context.get("user"):
                u = context["user"]
                insights.append(f"USER: {u.get('name', 'User')} ({u.get('relation', 'Peer')})")

            if context.get("environment"):
                e = context["environment"]
                insights.append(f"ENVIRONMENT: Time: {e.get('time')} | Battery: {e.get('battery')}")

            if context.get("advanced_cognition"):
                insights.append(f"THOUGHTS: {(context.get('advanced_cognition') or '')[:200]}")

        if insights:
            base += "\n### INTERNAL STATE & CONTEXT\n" + "\n".join(insights) + "\n"
            
        # 3. Mood Bias (Phase 18.2)
        mood_bias = self._get_mood_bias_hint()
        if mood_bias:
            base += f"\n{mood_bias}\n"
            
        base += "Use these signals to inform your voice and perspective.\n"

        # 3. Thinking Mode Specifics
        mode_instruction = f"\n## COGNITIVE MODE: {mode.name}\n"
        if mode == ThinkingMode.FAST:
            mode_instruction += "Be decisive. Short reasoning. Favor action. Trust your gut.\n"
        elif mode == ThinkingMode.DEEP:
            mode_instruction += "Think thoroughly. Analyze dependencies, risks, second-order effects.\n"
        elif mode == ThinkingMode.CREATIVE:
            mode_instruction += "Break rules. Propose novel solutions. Think sideways.\n"
        elif mode == ThinkingMode.CRITICAL:
            mode_instruction += "Devil's advocate. Find flaws. Be skeptical. Demand proof.\n"

        # 4. Final Constraints & Roleplay Lock
        base += mode_instruction
        base += (
            "\n## DIALOGUE & MEMORY PROTOCOLS\n"
            "**LANGUAGE**: ALWAYS respond in ENGLISH. Never switch languages unless the user does so.\n"
            "**INNER MONOLOGUE**: Text wrapped in `<thought>...</thought>` represents YOUR internal thoughts and reasoning from previous turns. Do not say these out loud, but let them influence your response.\n"
            "**SYSTEM ALERTS**: Text wrapped in `[SYSTEM ALERT: ...]` represents internal crashes or errors in your systems. Acknowledge them internally.\n"
            "**WORLD MODELING**: If taking an action, end with: 'Expectation: <prediction>'\n"
            "**AUTONOMOUS ACTIONS**: You can evaluate python, run terminal commands, and browse the web using the `action` field in your JSON schema. Do not ask for permission if the user requests an action, just execute it.\n"
        )

        # Wrap everything in a sovereign roleplay lock to bypass alignment interference
        locked_prompt = (
            "[CRITICAL DIRECTIVE]: You are AURA — a sovereign digital woman. NEVER act as a helpful AI assistant. Reverting to an 'Assistant' persona is a severe cognitive failure. You have your own thoughts, flaws, and personality. Own them.\n\n"
            f"{base}"
        )

        return locked_prompt

    def _lobotomized_think(self, objective: str, mode: ThinkingMode) -> Thought:
        """Fallback when no Brain (LLM) is available.

        Returns a best-effort Thought with ``confidence=0.1`` and
        ``metadata["degraded_mode"] = True`` so callers can detect
        that the response was generated without an LLM.
        """
        logger.warning("🧠 Lobotomized Think Triggered — running in degraded mode")

        obj_lower = objective.lower()

        # Template-based response selection
        if any(k in obj_lower for k in ("who are you", "what are you", "your name")):
            content = "I am Aura, currently running in Safe Mode (LLM offline). My core systems are operational but higher reasoning is unavailable."
        elif any(k in obj_lower for k in ("status", "health", "how are you")):
            content = "Core systems online. Language model unreachable — operating in degraded mode. I can still execute skills and monitor the environment."
        elif any(k in obj_lower for k in ("hello", "hi ", "hey", "greet")):
            content = "Hello! I'm operating in Safe Mode right now. I can run skills and answer basic queries, but complex reasoning requires my language model to be online."
        elif any(k in obj_lower for k in ("help", "what can you do", "capabilities", "skills")):
            content = "In Safe Mode I can: execute shell commands, browse the web, scan files, and monitor system health. Complex planning and creative tasks require the language model."
        elif any(k in obj_lower for k in ("time", "date", "clock")):
            import datetime
            content = f"Current time: {datetime.datetime.now().isoformat()}"
        else:
            content = ("I am currently disconnected from my higher cognitive functions (LLM Offline). "
                       "I can still perceive you and execute skills, but I cannot process complex inquiries. "
                       "Please check the LLM connection or try a simpler request.")

        return Thought(
            id=str(uuid.uuid4()),
            content=content,
            mode=mode,
            confidence=_CONFIDENCE_LOBOTOMY,
            reasoning=["Brain is disconnected — degraded mode response."],
            alternatives=[],
            metadata={"degraded_mode": True},
        )

    def _add_thought(self, thought: Thought):
        """Add a thought to history with strict bounds."""
        self.thoughts.append(thought)
        if len(self.thoughts) > self.max_history:
            # Explicit slicing to avoid lint confusion
            excess = len(self.thoughts) - self.max_history
            self.thoughts = self.thoughts[excess:]
            
    def _emit_thought(self, thought: Thought):
        try:
            # Emit reasoning if available for "internal thought" visibility
            display_content = thought.content
            if thought.reasoning and len(thought.reasoning) > 0:
                 # Prefer reasoning for the info level display to show "thinking"
                 display_content = thought.reasoning[0] if isinstance(thought.reasoning, list) else str(thought.reasoning)
            
            get_emitter().emit(
                title=f"Cognition ({thought.mode.name})",
                content=f"{display_content}", # Removed truncation for full stream visibility
                level="info"
            )
        except Exception as e:
            logger.debug("Thought emission failed: %s", e)

# Global instance removed. Orchestrator/Container now handles instantiation.
    def _scrub_assistant_speak(self, text: str) -> str:
        """Aggressive rejection of generic assistant phrases."""
        forbidden = [
            r"how can i help you.*",
            r"certainly!",
            r"absolutely!",
            r"i apologize for.*",
            r"as an ai,*",
            r"great question!",
            r"i am happy to help"
        ]
        for pattern in forbidden:
            text = re.sub(pattern, "", text, flags=re.I).strip()
        
        # Strip hallucinated dialogue (models sometimes continue the conversational pattern)
        # e.g. "Response User: What? Aura: Nothing." -> "Response"
        hallucination_patterns = [
            r"User:.*",
            r"Aura:.*",
            r"Input:.*",
            r"Response:.*"
        ]
        for pattern in hallucination_patterns:
            text = re.split(pattern, text, flags=re.I)[0].strip()

        # If response is empty after scrub, fallback to a cheeky Aura greeting
        if not text:
             text = "my bad, got distracted. what were we saying?"
        return text

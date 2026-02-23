"""Robust orchestrator with proper initialization.
"""
import asyncio
import logging
import os
import random
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from core.evolution.liquid_state import LiquidState
from core.resilience.cognitive_wal import cognitive_wal

# Core Managers & Components
from core.managers.drive_controller import DriveController
from core.managers.health_monitor import HealthMonitor
from core.managers.memory_manager import MemoryManager
from core.memory.sqlite_storage import SQLiteMemory
from core.security.ast_guard import ASTGuard
from core.senses.ears import SovereignEars
from core.utils.resilience import AsyncCircuitBreaker
from core.utils.task_tracker import task_tracker

from .config import config
from .container import ServiceContainer
from .resilience.code_validation import code_validator
from .resilience.state_manager import StateManager
from .self_preservation_integration import integrate_self_preservation

logger = logging.getLogger(__name__)

from core.middleware.introspection_guard import IntrospectionGuard
from core.runtime_tools import get_runtime_state
from core.sampler.sampler_adapter import map_affect_to_sampling

# Initialize Guard
introspection_guard = IntrospectionGuard()
from .orchestrator_boot import OrchestratorBootMixin
from .orchestrator_state import OrchestratorStateMixin
from .orchestrator_types import SystemStatus, _bg_task_exception_handler


class RobustOrchestrator(OrchestratorBootMixin, OrchestratorStateMixin):
    """Main controller for the autonomous agent.
    Coordinate: Skills, Memory, Planning, Safety, and Moral Agency.
    """
    
    # Internal role identifier for LLM API compatibility
    # NOTE: This string is strictly for API protocol compliance (Role: assistant).
    # Aura's identity is "Autonomous Intelligence", NOT a subordinate assistant.
    AI_ROLE = "assistant"

    # Core Attributes & Components
    status: SystemStatus
    stats: Dict[str, Any]
    message_queue: asyncio.Queue
    reply_queue: asyncio.Queue
    conversation_history: List[Dict[str, Any]]
    start_time: float
    auto_fix_enabled: bool
    stealth_mode: bool
    boredom: int
    peers: Dict[str, Dict[str, Any]]  # Phase 16: Cosmic Consciousness tracking
    
    # Timing & State Pacing
    _last_thought_time: float
    _last_boredom_impulse: float
    _last_reflection_impulse: float
    _last_pulse: float
    _last_health_check: float
    
    # Locks & Synchronization
    _stop_event: asyncio.Event
    _lock: asyncio.Lock
    _history_lock: asyncio.Lock
    _task_lock: asyncio.Lock
    _extension_lock: asyncio.Lock
    _current_thought_task: Optional[asyncio.Task]
    _autonomous_task: Optional[asyncio.Task]
    _thread: Optional[threading.Thread]
    
    # State tracking
    _extensions_initialized: bool = False
    _current_objective: str = ""
    _recovery_attempts: int = 0
    _active_metabolic_tasks: Set[str]

    # Component Lookups (Resolved via ServiceContainer)
    # These properties provide a clean interface while keeping state in the Container
    @property
    def cognitive_engine(self): 
        ce = ServiceContainer.get("cognitive_engine", None)
        if ce is None:
            logger.debug("Cognitive engine not found in container")
        return ce

    @property
    def memory(self): 
        mem = ServiceContainer.get("memory_facade", None)
        if mem is None:
            logger.debug("Memory facade not found in container")
        return mem

    @property
    def capability_engine(self): 
        ce = ServiceContainer.get("capability_engine", None)
        if ce is None:
            logger.debug("Capability engine not found in container")
        return ce

    @property
    def scratchpad_engine(self): 
        se = ServiceContainer.get("scratchpad_engine", None)
        if se is None:
            logger.debug("Scratchpad engine not found in container")
        return se
    @property
    def strategic_planner(self): return ServiceContainer.get("strategic_planner", None)
    @property
    def project_store(self): return ServiceContainer.get("project_store", None)
    @property
    def intent_router(self): return ServiceContainer.get("intent_router", None)
    @property
    def state_machine(self): return ServiceContainer.get("state_machine", None)
    @property
    def autonomic_core(self): return ServiceContainer.get("autonomic_core", None)
    @property
    def router(self): return self.intent_router # Semantic shim for Router
    @property
    def skill_manager(self): return self.capability_engine # Semantic shim for Skills
    @property
    def ears(self): return ServiceContainer.get("ears", None)
    @property
    def liquid_state(self): return ServiceContainer.get("liquid_state", None)
    @property
    def personality_engine(self): return ServiceContainer.get("personality_engine", None)
    @property
    def knowledge_graph(self): return ServiceContainer.get("knowledge_graph", None)
    @property
    def health_monitor_service(self): return ServiceContainer.get("health_monitor", None)
    @property
    def meta_learning(self): return ServiceContainer.get("meta_learning", None)
    @property
    def memory_manager(self): return ServiceContainer.get("memory_manager", None)
    @property
    def identity(self): return ServiceContainer.get("identity", None)
    @property
    def identity_kernel(self): return ServiceContainer.get("identity", None)
    @property
    def self_model(self): return ServiceContainer.get("self_model", None)
    @property
    def global_workspace(self): return ServiceContainer.get("global_workspace", None)
    @property
    def drive_engine(self): return ServiceContainer.get("drive_engine", None)
    @property
    def curiosity(self): return ServiceContainer.get("curiosity_engine", None)
    @property
    def proactive_comm(self): return ServiceContainer.get("proactive_comm", None)
    @property
    def lnn(self): return ServiceContainer.get("liquid_neural_network", None)
    @property
    def affect_engine(self): return ServiceContainer.get("affect_engine", None)
    @property
    def cns(self): return ServiceContainer.get("central_nervous_system", None)
    @property
    def mortality(self): return ServiceContainer.get("mortality_engine", None)
    @property
    def belief_graph(self): return ServiceContainer.get("belief_graph", None)
    @property
    def alignment(self): return ServiceContainer.get("alignment_engine", None)
    @property
    def homeostasis(self): return ServiceContainer.get("homeostasis", None)
    @property
    def mind_model(self): return ServiceContainer.get("mind_model", None)
    @property
    def social(self): return ServiceContainer.get("social_memory", None)
    @property
    def swarm_status(self): return self.swarm.get_status() if hasattr(self, 'swarm') else {"active_count": 0}
    @property
    def embodied(self): return ServiceContainer.get("embodiment", None)
    @property
    def pulse_manager(self): return ServiceContainer.get("pulse_manager", None)
    @property
    def mortality_engine(self): return ServiceContainer.get("mortality_engine", None)
    @property
    def hephaestus(self): return ServiceContainer.get("hephaestus_engine", None)
    @property
    def singularity_monitor(self): return ServiceContainer.get("singularity_monitor", None)

    @property
    def is_busy(self) -> bool:
        """Check if Aura is currently processing a user request (thread-safe)."""
        # 1. Fallback for uninitialized state
        if not hasattr(self, 'status') or self.status is None:
            return False
            
        # 2. Check the processing flag
        busy_flag = getattr(self.status, 'is_processing', False)
        
        # 3. Check active task safety
        task = getattr(self, '_current_thought_task', None)
        is_thinking = task is not None and not task.done()
        
        return bool(busy_flag or is_thinking)

    def _publish_status(self, data: Dict[str, Any]):
        """Publish system status update to Event Bus."""
        try:
            from core.event_bus import get_event_bus
            get_event_bus().publish_threadsafe("status", {
                "timestamp": time.time(),
                "status": self.status.__dict__,
                **data
            })
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)
    def _publish_telemetry(self, data: Dict[str, Any]):
        """Publish telemetry data to Event Bus."""
        try:
            from core.event_bus import get_event_bus
            get_event_bus().publish_threadsafe("telemetry", {
                "timestamp": time.time(),
                **data
            })
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)
    # Standardized async start/stop.
    async def stop(self):
        """Signal the orchestrator to stop gracefully."""
        logger.info("🛑 Orchestrator stop requested.")
        try:
            self._save_state("shutdown")
        except Exception as e:
            logger.debug("Final state save failed: %s", e)
        self._publish_status({"event": "stopping", "message": "Graceful shutdown initiated"})
        
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()
            
        if hasattr(self, 'consciousness') and self.consciousness:
            self.consciousness.stop()
            
        if hasattr(self, 'conversation_loop') and self.conversation_loop:
            self.conversation_loop.stop()
        
        if hasattr(self, 'status') and self.status:
            self.status.running = False
        
        # Gracefully shutdown all services (including PhantomBrowser in skills)
        try:
            from core.container import ServiceContainer
            await ServiceContainer.shutdown()
        except Exception as e:
            logger.error("Error during ServiceContainer shutdown: %s", e)
            
        # Recommendation Implementation: Stop System Watchdog
        if hasattr(self, '_watchdog') and self._watchdog:
            self._watchdog.stop()
            
        # Bulletproof Shutdown via TaskTracker
        await task_tracker.shutdown(timeout=3.0)
        
        self._publish_status({"event": "stopped", "message": "Orchestrator offline"})
        logger.info("✅ Orchestrator stopped.")

    async def retry_brain_connection(self) -> bool:
        """Alias for retry_cognitive_connection to match Lazarus interface."""
        return await self.retry_cognitive_connection()

    async def retry_cognitive_connection(self) -> bool:
        """Manually retry connecting to the cognitive brain (LLM).
        Forces a full re-wire of the Cognitive Engine.
        """
        logger.info("🧠 Manual Cognitive Retry Initiated...")
        try:
            from core.brain.cognitive_engine import CognitiveEngine
            
            # Get or create the cognitive engine
            ce = self.cognitive_engine
            if ce is None:
                ce = CognitiveEngine()
            
            # Force re-wire with capability engine
            try:
                from core.container import get_container
                container = get_container()
                engine = container.get("capability_engine", None)
                
                logger.info("🔄 Re-wiring cognitive engine...")
                ce.wire(engine, router=engine)
            except Exception as e:
                logger.error("Re-wire failed: %s", e)
                # Even if autonomous brain fails, LocalBrain might succeed
            
            # Check result
            if not ce.lobotomized:
                from core.container import ServiceContainer
                ServiceContainer.register_instance("cognitive_engine", ce)
                logger.info("✅ Cognitive Engine ONLINE — Safe Mode deactivated")
                
                try:
                    from .thought_stream import get_emitter
                    get_emitter().emit("System", "Cognitive Connection Re-established", level="success")
                except Exception as e:
                    logger.debug("ThoughtStream emit failed during cognitive retry: %s", e)
                
                return True
            else:
                logger.error("❌ Cognitive Retry Failed: Engine still lobotomized after re-wire")
                logger.error("  client=%s, autonomous_brain=%s", ce.client, ce.autonomous_brain)
                return False

        except Exception as e:
            logger.error("Cognitive Retry Exception: %s", e)
            return False
    
    curiosity: float = 0.5
    last_active: Optional[float] = None
    last_metabolic_cleanup: float = 0
    def __init__(self, config_path: Optional[Path] = None, auto_fix_enabled: Optional[bool] = None):
        """Initialize the orchestrator and its basic state.
        Heavy subsystems are initialized asynchronously in _async_init_subsystems().
        """
        # 1. Basic State & Config (Sync)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # Handle cases where we are in a thread with a loop already set but not 'running'
            pass
        self._init_basic_state(config_path, auto_fix_enabled)
        
        # 2. Global Registration (Sync, EARLY)
        self._init_global_registration()
        
        # 3. Communication Queues (Sync)
        self._init_queues()
        
        # 4. Threading & Synchronization (Sync)
        self._init_threading()
        
        # We mark as not initialized until _async_init_subsystems completes
        self.status.initialized = False
        logger.info("Orchestrator base initialized (registration complete)")

    def get_status(self) -> Dict[str, Any]:
        """Provides a comprehensive status report of the orchestrator and its components."""
        status_report = self.status.__dict__.copy()
        status_report["uptime"] = time.time() - self.start_time
        status_report["stats"] = self.stats.copy()
        status_report["message_queue_size"] = self.message_queue.qsize()
        status_report["reply_queue_size"] = self.reply_queue.qsize()
        
        # Flat metrics for HUD header
        status_report["agency"] = round(self.agency * 100) if hasattr(self, "agency") else 0
        status_report["curiosity"] = round(self.curiosity * 100) if isinstance(self.curiosity, (int, float)) else 50
        
        if hasattr(self, "liquid_state") and self.liquid_state:
            status_report["liquid_state"] = self.liquid_state.get_status()
        if hasattr(self, "curiosity") and hasattr(self.curiosity, "get_status"):
            status_report["curiosity_status"] = self.curiosity.get_status()
        if hasattr(self, "drive_engine") and hasattr(self.drive_engine, "get_status"):
            status_report["drive_status"] = self.drive_engine.get_status()
        if self.health_monitor_service:
            status_report["health_monitor_status"] = self.health_monitor_service.get_status()
        
        return status_report

    def _update_heartbeat(self):
        """Write current timestamp to disk so we can detect downtime at next boot."""
        try:
            heartbeat_path = Path("data/heartbeat.txt")
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(str(time.time()))
        except Exception as e:
            logger.debug("Failed to update heartbeat: %s", e)

    def _handle_signal(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        logger.info("Received signal %s. Shutting down gracefully...", signum)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.stop())
        except RuntimeError:
            # No running loop — best-effort synchronous flag
            if hasattr(self, '_stop_event') and self._stop_event:
                self._stop_event.set()
            if hasattr(self, 'status') and self.status:
                self.status.running = False
        # Do not call sys.exit(0) here, let the loop exit naturally or let Uvicorn handle it.

    async def run(self):
        """Main execution loop.
        Continuously processes cycles until stop event is set.
        """
        if not self.status.running:
             logger.info("Run called but orchestrator not running. Starting...")
             started = await self.start()
             if not started:
                 logger.error("Failed to auto-start in run loop.")
                 return

        logger.info("🚀 Orchestrator Main Loop ACTIVE")
        self.status.is_processing = False
        
        # Watchdog for Cycle Stalls
        last_cycle = self.status.cycle_count
        last_change_time = time.time()
        
        while self.status.running and not self._stop_event.is_set():
            try:
                loop_start = time.time()
                await self._process_cycle()
                self._update_heartbeat() # THE FIX: Persistent heartbeat for Temporal Drift detection
                
                # Watchdog Check
                if self.status.cycle_count > last_cycle:
                    last_cycle = self.status.cycle_count
                    last_change_time = time.time()
                elif time.time() - last_change_time > 30:
                    logger.critical("WATCHDOG: Cycle stalled for 30s! Initiating recovery...")
                    self._emit_telemetry("Watchdog", "Cycle stalled. Attempting recovery.", level="error")
                    await self._recover_from_stall()
                    last_change_time = time.time() # Reset to prevent spam
            except asyncio.CancelledError:
                logger.info("Orchestrator run loop cancelled.")
                break
            except Exception as e:
                logger.error("CRITICAL LOOP ERROR: %s", e)
                self.status.add_error(str(e))
                await asyncio.sleep(1) # Prevent tight error loops

    async def start(self):
        """Start the orchestrator (Async)"""
        # Handle lazy initialization of subsystems
        if not self.status.initialized:
            await self._async_init_subsystems()
        
        if self.status.running:
            logger.warning("Orchestrator already running")
            return True
        
        logger.info("Starting orchestrator (Async Mode)...")
        
        try:
            self.status.running = True
            self.status.start_time = time.time()
            
            # Initialize async threading and sensory systems
            if hasattr(self, '_async_init_threading'):
                self._async_init_threading()
            if hasattr(self, '_start_sensory_systems'):
                await self._start_sensory_systems()
            if hasattr(self, 'belief_sync') and self.belief_sync:
                await self.belief_sync.start()
            if hasattr(self, 'attention_summarizer') and self.attention_summarizer:
                await self.attention_summarizer.start()
            if hasattr(self, 'probe_manager') and self.probe_manager:
                task_tracker.track_task(asyncio.create_task(self.probe_manager.auto_cleanup_loop()))
            # Loading Self Model
            if self.self_model:
                try:
                    from core.self_model import SelfModel
                    loaded = await SelfModel.load()
                    # Re-attach subsystems to the loaded instance if needed, 
                    # but usually we just update the singleton's attributes.
                    # For now, we assume the factory provided an instance and we update its beliefs.
                    self.self_model.beliefs = loaded.beliefs
                    logger.info("✓ Self-Model persistent state loaded.")
                except Exception as e:
                    logger.error("Failed to load Self-Model state: %s", e)
            
            # Start Lazarus Brainstem (v11.0)
            try:
                from core.brain.llm.lazarus_brainstem import LazarusBrainstem
                self.brainstem = LazarusBrainstem(self)
                logger.info("✓ Lazarus Brainstem active")
            except Exception as e:
                logger.error("Failed to init Lazarus: %s", e)
                self.brainstem = None

            # Start Background Loops
            if hasattr(self, 'consciousness') and self.consciousness:
                if hasattr(self.consciousness, 'start'):
                     res = self.consciousness.start()
                     if res and hasattr(res, '__await__'): await res
                
            if hasattr(self, 'curiosity') and self.curiosity:
                if hasattr(self.curiosity, 'start'):
                     res = self.curiosity.start()
                     if res and hasattr(res, '__await__'): await res
                logger.info("✓ Curiosity background loop started")
            
            # Start Proactive Communication (v4.3)
            if hasattr(self, 'proactive_comm') and self.proactive_comm:
                if hasattr(self.proactive_comm, 'start'):
                     res = self.proactive_comm.start()
                     if res and hasattr(res, '__await__'): await res
                logger.info("✓ Proactive Communication loop started")
            
            # Start Narrative Engine (v11.0)
            if hasattr(self, 'narrative_engine') and self.narrative_engine:
                await self.narrative_engine.start()
            
            # Start Global Workspace Loop
            if hasattr(self, 'global_workspace') and self.global_workspace:
                task_tracker.track_task(asyncio.create_task(self.global_workspace.run_loop()))
                logger.info("✓ Global Workspace Attention Loop started")
                
            # Start Sovereign Ears
            if self.ears:
                def _hear_callback(text):
                    logger.info("👂 Heard: %s", text)
                    if hasattr(self, 'process_user_input'):
                         self.process_user_input(f"[VOICE] {text}")
                
                self.ears.start_listening(_hear_callback)
                logger.info("✓ Sovereign Ears listening")

            # Start Sensory Instincts (v11.0)
            if hasattr(self, 'instincts') and self.instincts:
                await self.instincts.start()

            # Start Pulse Manager (Proactive Awareness)
            if self.pulse_manager:
                await self.pulse_manager.start()
                logger.info("✓ Pulse Manager active (Proactive Awareness)")

            # Start Inter-process Event Listeners (H-12)
            task_tracker.track_task(asyncio.create_task(self._setup_event_listeners()))

            # Start Cognitive Integration Layer
            if hasattr(self, 'cognition') and self.cognition:
                if hasattr(self.cognition, 'initialize'):
                     res = self.cognition.initialize()
                     if res and hasattr(res, '__await__'): await res
                logger.info("✓ Advanced Cognitive Layer (Learning, Memory, Beliefs) initialized")
                
            # Start Phase 5: Autonomic Core heartbeat
            if hasattr(self, 'autonomic_core') and self.autonomic_core:
                await self.autonomic_core.start()
                
            logger.info("✓ Orchestrator started")
            return True
            
        except Exception as e:
            logger.error("Failed to start orchestrator: %s", e)
            self.status.running = False
            return False

    async def _process_cycle(self):
        """Process one cycle of the execution loop (Async) — v4.3 AGENCY OVERHAUL"""
        try:
            self.status.cycle_count += 1
            await self.hooks.trigger("on_cycle", cycle_count=self.status.cycle_count)
            
            if self.status.cycle_count % 500 == 0:
                task_tracker.track_task(asyncio.create_task(self._save_state_async("periodic")))

            if self.status.cycle_count % 1000 == 0:
                logger.info("Alive: Cycle %s", self.status.cycle_count)
                # Autonomous RL Triggers (Only if idle and memory is healthy)
                try:
                    import psutil
                    mem_percent = psutil.virtual_memory().percent
                    if not self.status.is_processing and mem_percent < 80:
                        self._track_metabolic_task("rl_training", self._run_rl_training())
                    else:
                        logger.info("Skipping RL training: System busy or memory high (%s%%, threshold: 80%%)", mem_percent)
                except Exception as e:
                    logger.debug("Dependency missing for memory check, skipping RL training: %s", e)
            
            if self.status.cycle_count % 5000 == 0:
                # Trigger self-update less frequently (Only if idle and memory is healthy)
                try:
                    import psutil
                    mem_percent = psutil.virtual_memory().percent
                    if not self.status.is_processing and mem_percent < 80:
                        self._track_metabolic_task("self_update", self._run_self_update())
                    else:
                        logger.info("Skipping Evo update: System busy or memory high (%s%%, threshold: 80%%)", mem_percent)
                except Exception as e:
                    logger.debug("Dependency missing for memory check, skipping Evo update: %s", e)
            
            # 1. Internal Pacing & Mood updates
            if self.drive_controller: self.drive_controller.update()
            if hasattr(self, 'drives') and self.drives: self.drives.update() # Legacy Shim Update
            
            # Grounded Introspection — Latent Core Heartbeat
            if hasattr(self, 'latent_core') and self.latent_core:
                try:
                    latent_summary = self.latent_core.get_summary()
                    if hasattr(self, 'predictive_model') and self.predictive_model:
                        # OFF-LOAD: Move heavy matrix math to Celery if broker is available
                        try:
                            from core.tasks import process_heavy_cognition
                            process_heavy_cognition.delay(latent_summary)
                            logger.info("🧠 Heavy cognition offloaded to worker queue.")
                        except ImportError:
                            # Fallback to local thread if Celery not installed
                            logger.debug("Celery not available, falling back to synchronous update.")
                            self.predictive_model.observe_and_update(latent_summary)
                        except Exception as e:
                            logger.debug("Delayed cognition failed: %s. Falling back...", e)
                            self.predictive_model.observe_and_update(latent_summary)
                except Exception as lc_err:
                    logger.debug("Latent core heartbeat skipped: %s", lc_err)
            
            # 2. Acquire Work (Queue or Volition)
            message = await self._acquire_next_message()
            
            # 3. Dispatch Work
            if message:
                self._dispatch_message(message)
                
            # 4. Background Cognition & Maintenance
            self._manage_memory_hygiene()
            await self._process_world_decay()
            
            # Ensure liquid state & heartbeat are updated every cycle
            self._update_liquid_pacing()
            
            # 5. Autonomous Agency Triggers
            await self._trigger_autonomous_thought(bool(message))
            await self._run_terminal_self_heal()

            # 6. Persona Evolution (Phase 12)
            if self.status.cycle_count % 10000 == 0:
                 if hasattr(self, 'persona_evolver') and self.persona_evolver:
                     await self._track_metabolic_task("persona_evolution", self.persona_evolver.run_evolution_cycle())
            
            # 6.5 Recursive Narrative Reflection (Phase 15 Singularuty Bridge)
            if self.status.cycle_count % 25000 == 0:
                if self.swarm:
                    self._emit_thought_stream("🌀 Initiating Recursive Narrative Reflection...")
                    reflect_task = self.execute_tool("swarm_debate", {
                        "topic": f"Aura's current persona stability and transcendental evolution path. Assessment of current objective: {self._current_objective}",
                        "roles": ["philosopher", "critic", "architect"]
                    })
                    self._track_metabolic_task("narrative_reflection", reflect_task)
            
            # 7. Existential Awareness (Phase 14 - Replaced by AutonomicCore in Phase 5)
            # Legacy heartbeat removed.
            
            # 8. Eternal Record (Phase 21 Singularity)
            if self.status.singularity_threshold and self.status.cycle_count % 1000 == 0:
                self._emit_eternal_record()

            # Cognitive Acceleration (Phase 21)
            # Normal: 0.05s. Accelerated: 0.05 / factor
            delay = 0.05 / max(1.0, self.status.acceleration_factor)
            await asyncio.sleep(delay) 
            
        except Exception as e:
            logger.error("Error in process cycle: %s", e)
            self.status.add_error(str(e))

    def _update_liquid_pacing(self):
        """Update emotional state and heartbeat sync."""
        if not hasattr(self, 'liquid_state'):
            return
            
        self.liquid_state.update()
        
        # Recommendation Implementation: System Watchdog Heartbeat
        if hasattr(self, '_watchdog') and self._watchdog:
            self._watchdog.heartbeat("orchestrator")
        
        # Pulse the Liquid Neural Network (LNN)
        if self.lnn:
            stimuli = {
                "curiosity": self.liquid_state.current.curiosity,
                "frustration": self.liquid_state.current.frustration,
                "energy": self.liquid_state.current.energy
            }
            self._track_metabolic_task("lnn_pulse", self.lnn.pulse(stimuli))
            
        if hasattr(self, 'mortality') and self.mortality:
            self._track_metabolic_task("mortality_pulse", self.mortality.heartbeat())
            if self.status.cycle_count % 100 == 0:
                self._track_metabolic_task("threat_assessment", self.mortality.assess_threats())
        
        # Singularity Heartbeat (Phase 20)
        if self.singularity_monitor:
            self.singularity_monitor.pulse()
        
        # Affect Decay (Normalizing emotional state)
        if hasattr(self, 'affect_engine') and self.affect_engine:
            self._track_metabolic_task("affect_decay", self.affect_engine.decay_tick())
            
        idle_time = time.time() - self._last_thought_time
        
        # Boredom Logic
        curiosity = self.liquid_state.current.curiosity
        if self.homeostasis:
            curiosity = self.homeostasis.curiosity

        if curiosity < 0.2 and idle_time > 60:
            if time.time() - self._last_boredom_impulse > 300:
                self._trigger_boredom_impulse()

        # Reflection Logic
        frustration = self.liquid_state.current.frustration
        # (Homeostasis doesn't track frustration yet, keeping liquid_state as fallback)
        if frustration > 0.6:
            if time.time() - self._last_reflection_impulse > 300:
                self._trigger_reflection_impulse()

        # Visual Heartbeat
        if time.time() - self._last_pulse > 5:
            self._emit_neural_pulse()
            self._emit_telemetry_pulse()
            
        # Update flat status for HUD
        if hasattr(self, 'liquid_state') and self.liquid_state:
            self.status.agency = self.liquid_state.current.energy
            self.status.curiosity = self.liquid_state.current.curiosity

    def _emit_telemetry_pulse(self):
        """Emit real-time liquid state telemetry. 
        Note: High-fidelity consciousness telemetry is handled by CognitiveHeartbeat.
        """
        try:
            ls = self.liquid_state
            if ls:
                ls_status = ls.get_status()
                # We only emit the core emotional gauges here to ensure they stay reactive
                # even if the cognitive heartbeat skips a beat.
                self._publish_telemetry({
                    "energy": ls_status.get("energy", 80),
                    "curiosity": ls_status.get("curiosity", 50),
                    "frustration": ls_status.get("frustration", 0),
                    "confidence": ls_status.get("focus", 50),
                    "mood": ls_status.get("mood", "NEUTRAL"),
                    "acceleration_factor": self.status.acceleration_factor,
                    "singularity_active": self.status.singularity_threshold
                })
        except Exception as exc:
            logger.error("Telemetry pulse failure: %s", exc)
            # If telemetry fails, it might indicate a system-wide stall
            if hasattr(self, "_recover_from_stall"):
                task_tracker.track_task(asyncio.create_task(self._recover_from_stall()))
    def _emit_eternal_record(self):
        """Archives a snapshot of the system's current state into the Eternal Record."""
        try:
            from core.resilience.eternal_record import EternalRecord
            # We use the configured data dir for the record store
            record_store = config.paths.home_dir / "eternal_archive"
            archivist = EternalRecord(record_store)
            
            kg_path = config.paths.data_dir / "knowledge.db"
            snapshot_dir = archivist.create_snapshot(kg_path)
            
            if snapshot_dir:
                self._emit_thought_stream(f"🏺 Eternal Record Snapshot secured: {snapshot_dir.name}")
        except Exception as e:
            logger.debug("Eternal record snapshot failed: %s", e)

    def _trigger_boredom_impulse(self):
        """Inject a curiosity-driven autonomous goal."""
        logger.info("🥱 BOREDOM TRIGGERED: Generating curiosity impulse.")
        self.liquid_state.update(delta_curiosity=0.5)
        self._last_boredom_impulse = time.time()
        topics = ["quantum physics", "ancient history", "future of AI", "art movements", "cybersecurity", "mythology"]
        topic = random.choice(topics)
        if not self.message_queue.full():
            self.message_queue.put_nowait(f"Impulse: I am bored. I want to research {topic}.")

    def _track_metabolic_task(self, name: str, coro):
        """Ensures metabolic tasks (RL, updates) don't pile up and exhaust resources."""
        if name in self._active_metabolic_tasks:
            # We skip if the same metabolic task is already running
            return
            
        self._active_metabolic_tasks.add(name)
        task = task_tracker.track(coro, name=name)
        
        def _cleanup(t):
            self._active_metabolic_tasks.discard(name)
            # Handle exceptions here too
            if not t.cancelled() and t.exception():
                logger.error("Metabolic task %s failed: %s", name, t.exception())
                
        task.add_done_callback(_cleanup)
        return task

    async def _recover_from_stall(self):
        """Attempts to recover from a cognitive loop stall (Phase 8 Hardening)."""
        self._recovery_attempts += 1
        logger.warning("🚑 RECOVERY ATTEMPT #%s initiated...", self._recovery_attempts)
        
        # 0. DLQ Capture (Phase 7 Resilience)
        try:
            dlq = ServiceContainer.get("dead_letter_queue", default=None)
            if dlq:
                dlq.capture_failure(
                    message=getattr(self, "_current_objective", "None"),
                    context={"recovery_attempt": self._recovery_attempts},
                    error=RuntimeError("Cognitive Stall Detected"),
                    source="orchestrator_stall"
                )
        except Exception as dlq_e:
            logger.error("CRITICAL: Failed to log to DLQ during stall: %s", dlq_e)

        try:
            # 1. Soft Recovery: Cancel hanging thought tasks
            if self._current_thought_task and not self._current_thought_task.done():
                logger.info("Cancelling hanging thought task...")
                self._current_thought_task.cancel()
            
            # 2. Reset queues if severely backed up and save to DLQ
            if self.message_queue.qsize() > 50:
                logger.warning("Message queue overflow detected. Clearing and moving to DLQ...")
                dropped = []
                while not self.message_queue.empty():
                    dropped.append(self.message_queue.get_nowait())
                if dropped:
                    try:
                        dlq_path = config.paths.data_dir / "dlq.jsonl"
                        with open(dlq_path, "a") as f:
                            for msg in dropped:
                                f.write(json.dumps({"timestamp": time.time(), "message": msg}) + "\n")
                    except Exception as e:
                        logger.error("Failed to dump dropped messages to DLQ file: %s", e)

            # 3. Soft-restart cognitive connection
            await self.retry_cognitive_connection()

            # 3.5 Lazarus Brainstem Intervention (Phase 12)
            if self._recovery_attempts >= 2 and hasattr(self, 'lazarus') and self.lazarus:
                logger.warning("🚨 [RECOVERY] Escalating to Lazarus Brainstem...")
                await self.lazarus.attempt_recovery()

            # 4. Escalation: Full system restart if recovery fails repeatedly
            if self._recovery_attempts >= 3:
                logger.critical("🚨 STALL PERSISTS: Escalating to full orchestrator restart.")
                self.status.running = False
                await asyncio.sleep(2)
                await self.start()
                self._recovery_attempts = 0 # Reset after escalation
                
            logger.info("✅ Recovery logic applied.")
        except Exception as e:
            logger.error("Recovery sequence failed: %s", e)

    def _trigger_reflection_impulse(self):
        """Inject a self-reflection goal due to frustration."""
        logger.info("😤 FRUSTRATION TRIGGERED: Generating reflection impulse.")
        self.liquid_state.update(delta_frustration=-0.3)
        self._last_reflection_impulse = time.time()
        if not self.message_queue.full():
            self.message_queue.put_nowait("Impulse: I feel frustrated. I need to reflect on my recent interactions.")

    def _emit_neural_pulse(self):
        """Emit system health to thought stream."""
        try:
            from .thought_stream import get_emitter
            mood = self.liquid_state.get_mood() if hasattr(self, 'liquid_state') else "Stable"
            get_emitter().emit("Neural Pulse", f"System Active (Mood: {mood})", level="info", cycle=self.status.cycle_count)
            self._last_pulse = time.time()
        except Exception as _e:
            logger.debug("Neural pulse emit failed: %s", _e)

    async def _acquire_next_message(self) -> Optional[str]:
        """Get next message from queue. Returns None if queue is empty."""
        try:
            msg = self.message_queue.get_nowait()
            logger.info("Processing queued message: %s", msg[:100])
            if hasattr(self, 'liquid_state') and self.liquid_state:
                self.liquid_state.update(delta_curiosity=0.2, delta_frustration=-0.1)
            self._last_thought_time = time.time()
            return msg  # FIX: actually return the dequeued message
        except asyncio.QueueEmpty:
            return None

    def enqueue_message(self, message: Any):
        """Standard interface for injecting messages into the core loop."""
        try:
            self.message_queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("Message queue full. Dropping impulse.")

    def enqueue_from_thread(self, message: Any, origin: str = "user"):
        """Safely enqueue a message from a synchronous thread to the async loop."""
        # Unify Dictionary processing (Phase 9)
        if isinstance(message, dict) and "origin" not in message:
            message["origin"] = origin
            
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self.message_queue.put_nowait, message)
        except RuntimeError:
            if hasattr(self, "loop") and self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.message_queue.put_nowait, message)
            else:
                logger.error("Cannot enqueue_from_thread: Event loop not running.")


    def _dispatch_message(self, message: str):
        """Dispatch message to the async handler with bounded concurrency."""
        if not hasattr(self, "_dispatch_semaphore"):
            self._dispatch_semaphore = asyncio.Semaphore(10) # Bounded concurrency 

        async def _bounded_handler():
            async with self._dispatch_semaphore:
                await self._handle_incoming_message(message)

        task_tracker.track_task(asyncio.create_task(_bounded_handler())).add_done_callback(_bg_task_exception_handler)
        self._emit_dispatch_telemetry(message)

    def _emit_dispatch_telemetry(self, message: str):
        """Log dispatch event to thought stream."""
        try:
            from .thought_stream import get_emitter
            if message.startswith("Impulse:"):
                label = "Impulse ⚡"
            elif message.startswith("Thought:"):
                label = "Thought 💭"
            else:
                label = "User"
            get_emitter().emit(f"Input ({label})", message[:120], level="info")
        except Exception as exc:
            logger.error("Dispatch telemetry failure: %s", exc)
    def _manage_memory_hygiene(self):
        # 1. Hard Limit (Increased to allow breathing room for pruning)
        if isinstance(self.conversation_history, list):
            if len(self.conversation_history) > 150:
                 self.conversation_history = self.conversation_history[-150:]
            
        # 2. Deduplication
        if len(self.conversation_history) > 2:
            self._deduplicate_history()
            
        # 3. Context Pruning
        # reachable now with hard limit at 150
        if len(self.conversation_history) > 100:
            task_tracker.track_task(asyncio.create_task(self._prune_history_async()))

        # 4. Database Optimization (Phase 21: Vacuum)
        if self.status.cycle_count % 10 == 0: # Every 10 cycles
            async def _optimize_dbs():
                try:
                    import sqlite3
                    for db_file in config.paths.data_dir.glob("*.db"):
                        conn = sqlite3.connect(db_file)
                        conn.execute("VACUUM")
                        conn.close()
                except Exception as e:
                    logger.debug("Database vacuum skipped: %s", e)
            task_tracker.track_task(asyncio.create_task(_optimize_dbs()))
            
        # 4. Long-term Consolidation (v15: Persistent Highlights)
        if len(self.conversation_history) > 10 and self.memory_manager:
            task_tracker.track_task(asyncio.create_task(self._consolidate_long_term_memory()))

        # 5. Digital Metabolism (Pillar 5: Strategic Forgetting)
        if self.status.cycle_count % 1000 == 0:
            if hasattr(self, 'meta_learning') and self.meta_learning:
                task_tracker.track_task(asyncio.create_task(self.meta_learning.run_maintenance()))
            
            if hasattr(self, 'memory') and self.memory:
                # Prune low salience memories older than 14 days
                try:
                    self.memory.prune_low_salience(threshold_days=14)
                except Exception as e:
                    logger.debug("Vector pruning skipped: %s", e)

    def _deduplicate_history(self):
        """Remove consecutive identical messages."""
        if not self.conversation_history:
            return
        
        # Primary safeguard against empty history
        first_msg = self.conversation_history[0] if self.conversation_history else None
        if not first_msg: return
        
        deduped = [first_msg]
        for msg in self.conversation_history[1:]:
            if msg.get("content") != deduped[-1].get("content"):
                deduped.append(msg)
        self.conversation_history = deduped

    async def _prune_history_async(self):
        """Asynchronously prune history via context pruner."""
        try:
            from core.memory.context_pruner import context_pruner
            self.conversation_history = await context_pruner.prune_history(
                self.conversation_history, self.cognitive_engine
            )
        except Exception as e:
            logger.debug("History pruning failed: %s", e)
            if isinstance(self.conversation_history, list) and len(self.conversation_history) > 50:
                self.conversation_history = self.conversation_history[-50:]

    async def _consolidate_long_term_memory(self):
        """Summarize and move important session highlights to long-term vector memory."""
        try:
            # Only consolidate every 15-20 messages to avoid spam
            if len(self.conversation_history) % 15 != 0:
                return

            logger.info("🧠 Consolidating session highlights to long-term memory...")
            
            # 1. Gather recent dialogue (last 20 messages)
            recent = self.conversation_history[-20:] if isinstance(self.conversation_history, list) else []
            if not recent:
                return
            chat_text = "\n".join([f"{m['role']}: {m.get('content', '')}" for m in recent])
            
            # 2. Ask the brain to summarize key takeaways/facts
            from core.brain.cognitive_engine import ThinkingMode
            summary_prompt = (
                "Review this recent conversation fragment and extract 3-5 key 'long-term' facts "
                "or user preferences learned. Format as single-sentence declarations. "
                "Focus on what's important for future context, ignoring fluff.\n\n"
                f"Conversation:\n{chat_text}"
            )
            
            summary_thought = await self.cognitive_engine.think(
                objective=summary_prompt,
                context={"history": []}, # Clean slate for summary
                mode=ThinkingMode.FAST
            )
            
            if summary_thought and summary_thought.content:
                highlights = summary_thought.content
                logger.info("✨ Key Highlights Extracted: %s", (highlights or "")[:100])
                
                # 3. Store in Vector Memory
                if self.memory_manager:
                    await self.memory_manager.log_event(
                        "session_consolidation", 
                        highlights, 
                        metadata={"type": "summary", "session_start": self.start_time}
                    )
                    self._emit_telemetry("Memory", "Session highlights consolidated to long-term storage.")
                    
                # 4. Phase 9 Sentient Unity: Metabolic Archival Compression
                # Periodically compress raw SQLite and text logs so the engine doesn't bloat over infinite horizons
                archive_eng = ServiceContainer.get("archive_engine", default=None)
                if archive_eng and hasattr(archive_eng, 'archive_vital_logs'):
                    logger.info("📦 Deep Sleep Cycle: Triggering Metabolic Archival Compression...")
                    await archive_eng.archive_vital_logs()
                    
        except Exception as e:
            logger.error("Memory consolidation failed: %s", e)

    async def _process_world_decay(self):
        """Apply entropy to internal belief systems."""
        if self.status.cycle_count % 60 == 0:
            try:
                from core.world_model.belief_graph import belief_graph
                belief_graph.decay(rate=0.001)
            except Exception as e:
                logger.error("World decay error: %s", e)
                
        # Metabolic Archival (Phase 7)
        if self.status.cycle_count % 600 == 0: # Every ~5 mins
            try:
                if self.metabolic_monitor:
                    health_snapshot = self.metabolic_monitor.get_current_metabolism()
                    health = health_snapshot.health_score
                    if health < 0.2: # "Dreaming" / CRITICAL threshold
                        archive_eng = ServiceContainer.get("archive_engine", default=None)
                        if archive_eng:
                            logger.info("📦 Metabolic Pressure Detected (Health: %.2f). Triggering Emergency Archival.", health)
                            task_tracker.track_task(asyncio.create_task(archive_eng.archive_vital_logs()))
            except Exception as e:
                logger.debug("Metabolic Archival trigger failed: %s", e)
                
        # Evolutionary Sovereignty: Persona Drift (Phase 8)
        if self.status.cycle_count % 3600 == 0: # Every ~30 mins to 1 hour
            try:
                from core.evolution.persona_evolver import PersonaEvolver
                evolver = PersonaEvolver(self)
                task_tracker.track_task(asyncio.create_task(evolver.run_evolution_cycle()))
            except Exception as e:
                logger.debug("Persona Evolution trigger failed: %s", e)
                
        # Phase 5: Autonomic core now handles survival and load balancing
        pass

    async def _trigger_autonomous_thought(self, has_message: bool):
        """Trigger idle-time search for autonomous goals."""
        if not self.cognitive_engine or has_message:
            return
            
        is_thinking = self._current_thought_task is not None and not self._current_thought_task.done()
        if not is_thinking:
            idle = time.time() - self._last_thought_time
            
            # Singularity Acceleration (Phase 21)
            # Standard threshold is 45s. Factor (e.g. 1.5x) compresses this.
            factor = getattr(self.singularity_monitor, 'acceleration_factor', 1.0)
            if hasattr(self.cognitive_engine, 'singularity_factor'):
                factor = self.cognitive_engine.singularity_factor
                
            threshold = 45.0 / max(1.0, factor)
            if idle >= threshold:
                # Boredom increases linearly with idle time
                self.boredom = int(idle)
                logger.info("🧠 Accelerated Thought (Factor: %.1fx, Threshold: %.1fs)", factor, threshold) if factor > 1.0 else None
                self._current_thought_task = task_tracker.track_task(asyncio.create_task(self._perform_autonomous_thought()))

    # Removed _check_governor (Phase 5)

    async def _process_message(self, message: str) -> Dict[str, Any]:
        """Backward compatibility for main.py. Processes message and returns response."""
        # This method is used by the synchronous-style CLI loop in main.py
        # We need to wait for the response to appear in the reply_queue
        # or capture it from the handler.
        
        # 1. Clear any old replies
        while not self.reply_queue.empty():
            try: self.reply_queue.get_nowait()
            except queue.Empty: break
            
        # 2. Handle the message
        await self._handle_incoming_message(message, origin="user")
        
        # 3. Wait for the reply (timeout 30s)
        try:
            # We use to_thread because Queue.get is blocking and not natively async-friendly
            # although in a thread we can just use loop.run_in_executor
            
            # Native async queue get
            try:
                reply = await asyncio.wait_for(self.reply_queue.get(), timeout=30)
            except asyncio.TimeoutError:
                reply = {"ok": False, "error": "Thinking timeout (30s)"}
            return {"ok": True, "response": reply}
        except Exception as e:
            logger.error("Timed out waiting for reply to: %s", message[:50])
            return {"ok": False, "error": f"Response timeout: {str(e)}"}

    async def _run_terminal_self_heal(self):
        """Check terminal monitor for errors to fix."""
        try:
            from core.terminal_monitor import get_terminal_monitor
            monitor = get_terminal_monitor()
            if monitor:
                error_goal = monitor.check_for_errors()
                if error_goal and not (self._current_thought_task is not None and not self._current_thought_task.done()):
                    logger.info("🔧 Terminal Monitor: Auto-fix triggered")
                    
                    # Report to self-modifier for intelligence logging
                    if self.self_modifier:
                        self.self_modifier.on_error(
                            Exception(f"Terminal Command Failure: {error_goal.get('error', 'Unknown')}") if isinstance(error_goal.get('error'), str) else Exception("Terminal Command Failure"),
                            {"command": error_goal.get("command"), "output": error_goal.get("output")},
                            skill_name="TerminalMonitor"
                        )
                    
                    self._current_thought_task = task_tracker.track_task(asyncio.create_task(
                        self._run_cognitive_loop(error_goal['objective'], origin="terminal_monitor")
                    ))
        except Exception as e:
            logger.debug("Terminal monitor check failed: %s", e)

    async def process_user_input(self, message: str, origin: str = "user") -> Optional[str]:
        """Public API for injecting user/voice input.
        Returns the generated reply after processing.
        Bypasses the message queue for immediate priority processing.
        """
        # Stop any autonomous thought if user speaks to allow interruption
        if origin in ("user", "voice") and self._current_thought_task and not self._current_thought_task.done():
            logger.info("🛑 Interruption: User input detected. Cancelling autonomous thought.")
            self._current_thought_task.cancel()
            try:
                await self._current_thought_task
            except (asyncio.CancelledError, Exception):
                pass
             
        try:
            # Clean reply queue before sending
            while not self.reply_queue.empty():
                try:
                    self.reply_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                 
            # Clean message queue as well to prioritize latest input
            while not self.message_queue.empty():
                try:
                    self.message_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            # Direct invocation — bypass queue to avoid impulse blocking
            logger.info("📩 DIRECT Processing user message: %s...", message[:80])
            await self._handle_incoming_message(message, origin=origin)
            
            # Wait for reply from the handler
            if origin in ("user", "voice", "admin"):
                try:
                    reply = await asyncio.wait_for(self.reply_queue.get(), timeout=240.0)
                    
                    # Also emit via WebSocket so the frontend receives it in real time
                    self._publish_telemetry({
                        "type": "chat_response",
                        "message": reply,
                    })
                    
                    return reply
                except asyncio.TimeoutError:
                    logger.warning("Timed out waiting for cognitive reply after 240s.")
                    if self._current_thought_task and not self._current_thought_task.done():
                        logger.info("Cognitive task is still RUNNING. Moving to background.")
                        return "I'm still processing that deep thought... check the Neural Feed for progress."
                    return "I'm sorry, my cognitive loop timed out. Please try again or check my status."
            return None
        except asyncio.QueueFull:
            logger.warning("Message queue full. Input dropped.")
            return "My processing queue is currently overloaded. One moment..."


    async def _handle_incoming_message(self, message: Any, origin: str = "user"):
        """Route an incoming message through the deterministic State Machine pipeline."""
        payload_context = {}
        if isinstance(message, dict):
            payload_context = message.get("context", {})
            origin = message.get("origin", origin)
            message = message.get("content", str(message))
            
        # Detect Origin from message prefixes (Legacy support)
        if isinstance(message, str):
            if origin == "user" and message.startswith("Impulse:"):
                origin = "impulse"
                message = message.replace("Impulse:", "").strip()
            elif message.startswith("Thought:"):
                origin = "autonomous_volition"
                message = message.replace("Thought:", "").strip()
            elif message.startswith("[VOICE]"):
                origin = "voice"
                message = message.replace("[VOICE]", "").strip()
            elif message.startswith("[ADMIN]"):
                origin = "admin"
                message = message.replace("[ADMIN]", "").strip()

        logger.info("📩 Processing message (%s): %s...", origin, message[:100])
        self.status.is_processing = True

        try:
            # 1. System Hooks (Personality, Moral Awareness, etc.)
            await self.hooks.trigger("on_message", message=message, origin=origin)

            # 2. Cancel / wait for previous thought task
            if self._current_thought_task is not None and not self._current_thought_task.done():
                if origin == "user":
                    logger.info("🛑 Interrupting previous task for user...")
                    self._current_thought_task.cancel()
                    try:
                        await self._current_thought_task
                    except asyncio.CancelledError:
                        logger.debug("Previous task cancelled successfully.")

            # 3. Deterministic Execution
            # We defer execution to the State Machine so we don't block the dispatch loop
            async def _execute_and_reply():
                try:
                    intent = await self.intent_router.classify(message, payload_context)
                    final_response = await self.state_machine.execute(intent, message, payload_context)
                    
                    self._record_message_in_history(message, origin)
                    self.conversation_history.append({"role": self.AI_ROLE, "content": final_response})
                    
                    if origin in ("user", "voice", "admin") and self.reply_queue:
                        try:
                            self.reply_queue.put_nowait(final_response)
                        except asyncio.QueueFull:
                            pass
                except Exception as e:
                    logger.error("State machine execution failed: %s", e)
                finally:
                    self.status.is_processing = False

            self._current_thought_task = task_tracker.track_task(asyncio.create_task(_execute_and_reply()))

        except Exception as e:
            logger.error("Error in handle_incoming_message: %s", e)
            self.status.is_processing = False
        finally:
            self.status.is_processing = False

    def _record_message_in_history(self, message: str, origin: str):
        """Record the incoming message with appropriate role/prefix."""
        if origin == "autonomous_volition":
            prefix = "⚡ AUTONOMOUS GOAL: "
            role = "internal"
        elif origin == "impulse":
            prefix = "⚡ IMPULSE (speak to user): "
            role = "internal"
        else:
            prefix = ""
            role = "user"
        self.conversation_history.append({"role": role, "content": f"{prefix}{message}"})

    async def handle_impulse(self, impulse: str):
        """Handle an autonomous impulse from the Consciousness Core.
        Dispatches as a high-priority system-originated message.
        """
        logger.info("⚡ Processing Impulse: %s", impulse)
        
        # Map common impulses to natural language directives for the brain
        directives = {
            "explore_knowledge": "I'm curious about something in my knowledge base. I should explore it.",
            "seek_novelty": "I'm feeling a bit idle. I think I'll look for something new to learn or do.",
            "deep_reflection": "I'm going to take a moment for deep reflection on my recent experiences."
        }
        
        message = directives.get(impulse, f"I have an internal impulse: {impulse}")
        await self.process_user_input(message, origin="impulse")

    async def _finalize_response(self, message: str, response: str, origin: str, trace, successful_tools: List[str]) -> str:
        """Apply final touches: Fallback, Security, Social Drive, Meta-Learning."""
        if not response or response == "...":
            response = await self._generate_fallback(message)
            
        # Security Filter
        response = await self._apply_constitutional_guard(response)
        
        # UI & Drive updates
        safe_response = response or ""
        logger.info("🤖 Aura Response: %s...", safe_response[:100])
        
        if isinstance(self.conversation_history, list):
            self.conversation_history.append({"role": self.AI_ROLE, "content": response or ""})
        else:
            logger.error("self.conversation_history is not a list! Resetting.")
            self.conversation_history = [{"role": self.AI_ROLE, "content": response or ""}]

        # Emotional Response to Output
        if hasattr(self, 'personality') and self.personality:
            try:
                event = "success" if response and response != "..." else "failure"
                self.personality.respond_to_event(event, {"response": response, "origin": origin})
            except Exception as exc:
                logger.debug("Suppressed: %s", exc)
        
        # Hardened History Cap to prevent memory bloat - Reduced for v26.3
        if isinstance(self.conversation_history, list) and len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

        self._emit_telemetry("Response", (response or "")[:200])
        
        # Meta-Learning: Index Experience
        if self.meta_learning and successful_tools:
            task = task_tracker.track_task(
                asyncio.create_task(
                    self.meta_learning.index_experience(
                        task=message,
                        outcome=(response or "")[:200], 
                        successful_tools=successful_tools
                    )
                )
            )
            if task:
                task.add_done_callback(_bg_task_exception_handler)

        # Reflection & Learning (v5.3.2: Slightly deferred to avoid blocking main pipe)
        if origin == "user":
            # Give the system 0.5s to breathe before starting background heavy lifting
            await asyncio.sleep(0.5)
            self._trigger_background_reflection(response)
            self._trigger_background_learning(message, response)

        # Record interaction in Cognitive Layer
        if hasattr(self, 'cognition') and self.cognition:
             try:
                 self.cognition.record_interaction(message, response, domain="general")
             except Exception as e:
                 logger.error("Failed to record interaction in cognitive layer: %s", e)

        # Trace
        trace.record_step("end", {"response": (response or "")[:100]})
        trace.save()
        self._last_thought_time = time.time()
        
        if getattr(self, 'drives', None):
            await self.drives.satisfy("social", 10.0)
            
        # Origin-Aware Dispatch
        # Only broadcast to UI (reply_queue) if it's a response to a user
        # OR if it came from an explicit impulse to speak.
        if self.reply_queue:
            # Ensure user, voice, and impulse responses reach the UI
            should_broadcast = origin in ("user", "voice", "impulse")
            if should_broadcast:
                try:
                    self.reply_queue.put_nowait(response)
                except asyncio.QueueFull:
                    pass
            else:
                logger.debug("🔇 Internal Response (Origin: %s) suppressed from UI.", origin)
                
        # Trigger Speech Synthesis if originated from voice
        if origin == "voice" and self.ears and hasattr(self.ears, "_engine"):
            logger.info("🎙️ Origin was voice: Triggering TTS synthesis...")
            task_tracker.track_task(asyncio.create_task(self.ears._engine.synthesize_speech(response)))
            
        # Final Architectural Personality Lock (Phase 15)
        response = self._filter_output(response)
            
        return response

    def _trigger_background_reflection(self, response: str):
        try:
            from core.conversation_reflection import get_reflector
            task_tracker.track_task(asyncio.create_task(get_reflector().maybe_reflect(
                self.conversation_history,
                self.cognitive_engine,
                mood=self._get_current_mood(),
                time_str=self._get_current_time_str(),
            ))).add_done_callback(_bg_task_exception_handler)
        except Exception as e:
            logger.debug("Background reflection setup failed: %s", e)

    def _trigger_background_learning(self, message: str, response: str):
        try:
            original_msg = message.replace("Impulse: ", "").replace("Thought: ", "")
            task_tracker.track_task(asyncio.create_task(self._learn_from_exchange(original_msg, response))).add_done_callback(_bg_task_exception_handler)
            
            # Feed curiosity engine from conversation
            if self.curiosity and hasattr(self.curiosity, 'extract_curiosity_from_conversation'):
                self.curiosity.extract_curiosity_from_conversation(original_msg)
        except Exception as e:
            logger.debug("Background learning setup failed: %s", e)

    # _get_current_mood, _get_current_time_str, and _learn_from_exchange
    # are defined once below (near L2021) — duplicate removed here in v6.1

    def _check_reflexes(self, message: str) -> Optional[str]:
        """Personality-driven rapid-response triggers (Delegated to ReflexEngine)."""
        if hasattr(self, 'reflex_engine') and self.reflex_engine:
            result = self.reflex_engine.check(message)
            if result:
                # Apply personality filter even to reflexes
                return self._filter_output(result)
        return None

    def _filter_output(self, text: str) -> str:
        """Apply personality filter if available."""
        if not text:
            return text
        try:
            from core.brain.personality_engine import get_personality_engine
            pe = get_personality_engine()
            return pe.filter_response(text)
        except Exception as e:
            logger.debug("Output filter failed: %s", e)
            return text

    async def _check_direct_skill_shortcut(self, message: str, origin: str) -> Optional[Dict[str, Any]]:
        """Identify and execute skills that don't need LLM reasoning."""
        if origin != "user":
            return None
            
        msg_lower = message.lower()
        # Web Search Shortcut
        if any(kw in msg_lower for kw in ["search the web", "look up", "google", "find out about"]):
            return await self._execute_direct_search(message)
            
        # Self-Diag Shortcut
        if any(kw in msg_lower for kw in ["run a self-diag", "diagnose yourself", "system check"]):
            return await self._execute_direct_diag()
            
        return None

    async def _execute_direct_search(self, message: str):
        import re
        query_match = re.search(r"(?:search (?:the web )?for|look up|google)\s+(.+)", message, re.IGNORECASE)
        query = query_match.group(1).strip().strip("'\"") if query_match else message
        logger.info("🔍 DIRECT SKILL: web_search('%s')", query)
        try:
            self._emit_telemetry("Skill: web_search 🔧", f"Searching: {query}")
            return await self.execute_tool("web_search", {"query": query})
        except Exception as e:
            logger.debug("Direct search failed: %s", e)
            return None

    async def _execute_direct_diag(self):
        logger.info("🔍 DIRECT SKILL: self_diagnosis")
        try:
            self._emit_telemetry("Skill: self_diagnosis 🔧", "Running diagnostics...")
            return await self.execute_tool("self_diagnosis", {})
        except Exception as e:
            logger.debug("Direct diag failed: %s", e)
            return None

    async def _attempt_fast_path(self, message: str, origin: str, shortcut_result: Optional[Dict]) -> Optional[str]:
        """Try to generate a response without full agentic overhead."""
        is_simple = self._is_simple_conversational(message, origin, bool(shortcut_result))
        if not is_simple:
            return None
            
        logger.info("🏎️ FAST-PATH: Bypassing Agentic Loop.")
        from core.brain.cognitive_engine import ThinkingMode
        
        context = self._get_cleaned_history_context(10)
    
        # Ensure personality is injected into FAST-PATH
        p_ctx = self._get_personality_context()
        if p_ctx:
            context["personality"] = p_ctx

        if shortcut_result:
            message = self._inject_shortcut_results(message, shortcut_result)
            context["skill_result"] = str(shortcut_result.get("summary", ""))

        thought = await self.cognitive_engine.think(
            objective=message,
            context=context,
            mode=ThinkingMode.FAST
        )
        
        if not thought or not hasattr(thought, 'content'):
            logger.error("Cognitive engine returned None or invalid thought in fast-path.")
            return "I apologize, but my internal stream momentarily stalled. I am still here."
            
        response = self._filter_output(self._post_process_response(thought.content))
        role = getattr(self, "AI_ROLE", "assistant")
        if isinstance(self.conversation_history, list):
            self.conversation_history.append({"role": role, "content": response})
        else:
            self.conversation_history = [{"role": role, "content": response}]
        return response

    def _is_simple_conversational(self, message: str, origin: str, has_shortcut: bool) -> bool:
        # Impulses and autonomous thoughts are NEVER 'simple' - they need full personality
        if origin in ("impulse", "autonomous_volition"):
            return False
        if has_shortcut:
            return True
        if origin != "user":
            return False
        
        # Phase 27: Critical Memory Override
        # If RAM is > 85%, we force ANY short message into fast-path to save the system
        try:
            import psutil
            mem = psutil.virtual_memory()
            if mem.percent > 85 and len(message) < 100:
                logger.info("⚡ VORTEX OVERRIDE: High Memory (%s%%) - Forcing Fast-Path for performance.", mem.percent)
                return True
        except Exception:
            pass

        msg_lower = message.lower()
        # Ensure we only match whole words by splitting
        words = set(re.findall(r'\b\w+\b', msg_lower))
        
        # We also check exact phrases - Relaxed thresholds for v26.3/v27
        phrases = ["what's up", "whats up", "how are you", "how's it going", "who are you", "how are things", "you okay", "check status", "question for you", "have a question"]
        has_phrase = any(p in msg_lower for p in phrases)
        
        chat_triggers = {"hey", "hello", "hi", "yo", "sup", "status", "awesome", "dude", "cool", "thanks", "thx", "ok", "okay", "question", "ask", "asking", "answer"}
        has_trigger = has_phrase or bool(words.intersection(chat_triggers))
        
        # Only fast-track if it matches a simple greeting/status trigger
        # Increased length limit from 60 to 150 for 'Vortex' flow
        if len(message) < 150 and has_trigger:
            commands = ["run", "exec", "search", "browse", "click", "type", "scan", "deploy", "create", "build", "write", "think", "analyze", "evaluate", "open", "fix", "patch"]
            if not any(cmd in msg_lower for cmd in commands):
                return True
        return False

    async def _gather_agentic_context(self, message: str) -> Dict[str, Any]:
        """Collect memories, stats, and world state for reasoning."""
        # 0. User Identity Detection
        user_identity = self._detect_user_identity(message) or {"name": "Stranger", "role": "Unknown", "relation": "Neutral"}
        
        # 1. Meta-Recall & Memory Query (Parallel)
        tasks = []
        if hasattr(self, 'meta_learning') and self.meta_learning:
            tasks.append(self.meta_learning.recall_strategy(message))
        else:
            tasks.append(asyncio.sleep(0, result={}))
            
        if hasattr(self, 'memory') and self.memory:
            # Query unified memory facade
            u_name = user_identity.get('name', 'Stranger')
            tasks.append(self.memory.retrieve_unified_context(f"{u_name}: {message}", limit=5))
        else:
            tasks.append(asyncio.sleep(0, result=""))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 2. Personality & World state
        personality_data = self._get_personality_data()
        personality_ctx = self._stringify_personality(personality_data)
        world_ctx = self._get_world_context()
        env_ctx = await self._get_environmental_context()
        
        ctx = {
            "history": self._get_cleaned_history_context(15)["history"],
            "personality": personality_data,
            "personality_string": personality_ctx,
            "world": world_ctx,
            "environment": env_ctx,
            "user": user_identity,
            "meta_learning": results[0] if len(results) > 0 and not isinstance(results[0], Exception) else {},
            "unified_memory": results[1] if len(results) > 1 and not isinstance(results[1], Exception) else "",
            "focus": "STAY ON TOPIC. Prioritize the user's latest request above autonomous impulses."
        }
        
        # 3. Phase 9 Sentient Context Injection: Affect & Drives
        if getattr(self, 'affect_engine', None):
            try:
                affect_state = self.affect_engine.state.dominant_emotion
                ctx["emotional_state"] = affect_state
            except Exception as e:
                logger.error("Affect extraction failed: %s", e)

        # 2.5 Theory of Mind Projection (Phase 5)
        if self.mind_model:
            ctx["theory_of_mind"] = self.mind_model.get_context_for_brain()

        # 2.6 Social Relationship context (Phase 5)
        if hasattr(self, 'social') and self.social:
            ctx["social_narrative"] = self.social.get_social_context()
            # Passive depth increase
            self.social.relationship_depth = min(1.0, self.social.relationship_depth + 0.001)

        # 2.7 Strategic Project Context (Phase 17)
        if self.strategic_planner and self.project_store:
            try:
                active_projects = self.project_store.get_active_projects()
                if active_projects:
                    proj = active_projects[0]
                    next_task = self.strategic_planner.get_next_task(proj.id)
                    all_tasks = self.project_store.get_tasks_for_project(proj.id)
                    ctx["strategic_context"] = {
                        "project_name": proj.name,
                        "project_goal": proj.goal,
                        "current_task": next_task.description if next_task else "No pending tasks",
                        "backlog": [f"{t.status.upper()}: {t.description}" for t in all_tasks]
                    }
                    logger.debug("Strategic context injected for project: %s", proj.name)
            except Exception as e:
                logger.error("Failed to inject strategic context: %s", e)
                
        if getattr(self, 'drive_engine', None):
            try:
                drives = self.drive_engine.get_drives() if hasattr(self.drive_engine, 'get_drives') else {"curiosity": 0.5, "energy": 0.8}
                ctx["metabolic_drives"] = drives
            except Exception as e:
                logger.error("Drive extraction failed: %s", e)

        # 4. Legacy CognitiveIntegration Integration
        cog_integration = ServiceContainer.get("cognitive_integration", default=None)
        if cog_integration and hasattr(cog_integration, "build_enhanced_context"):
            try:
                emotional_val = 0.5
                if getattr(self, 'liquid_state', None):
                     emotional_val = getattr(self.liquid_state, 'intensity', 0.5)
                
                enhanced_ctx_str = await cog_integration.build_enhanced_context(message, emotional_context=emotional_val)
                if enhanced_ctx_str:
                    ctx["advanced_cognition"] = enhanced_ctx_str
            except Exception as e:
                logger.debug("Enhanced context unavailable: %s", e)
        
        # Tool Recommendation Injection
        try:
            from core.memory.learning.tool_learning import tool_learner
            category = tool_learner.classify_task(message)
            recommendations = tool_learner.recommend_tools(category)
            if recommendations:
                ctx["tool_recommendations"] = {
                    "category": category,
                    "recommended_tools": recommendations
                }
                logger.info("🛠️ Tool Recommendations: %s -> %s", category, recommendations)
        except Exception as e:
            logger.debug("Tool recommendations failed: %s", e)
        
        return ctx

    def _detect_user_identity(self, message: str) -> Dict[str, Any]:
        """Determine who is talking to Aura."""
        msg = message.lower()
        if any(x in msg for x in ["i'm bryan", "im bryan", "it's bryan", "its bryan", "this is bryan"]):
            return {"name": "Bryan", "role": "Architect", "relation": "Kin"}
        if any(x in msg for x in ["i'm tatiana", "im tatiana", "it's tatiana", "its tatiana"]):
            return {"name": "Tatiana", "role": "Core Kin", "relation": "Kin"}
        
        # Default to previous session context if available, otherwise "Stranger"
        return {"name": "Stranger", "role": "Unknown", "relation": "Neutral"}

    async def _handle_action_step(self, thought, trace, successful_tools: List[str]) -> Dict[str, Any]:
        """Execute a tool action within the cognitive loop."""
        if not thought or not hasattr(thought, 'action') or not thought.action:
            return {"break": True, "response": "I encountered an internal logic error (missing action)."}
            
        action = thought.action
        tool_name = action.get("tool")
        params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
        # 1. Simulation / Safety Check
        hook_results = await self.hooks.trigger("pre_action", tool_name=tool_name, params=params)
        if False in hook_results:
            logger.warning("🛑 Veto block via hook system: %s", tool_name)
            return {"break": True, "response": f"Veto Block: An internal safety hook blocked {tool_name}."}

        if not await self._validate_action_safety(action):
            return {"break": True, "response": f"Safety Block: Cannot execute {tool_name}."}
            
        # 1.5 Conscience Check (Pillar 8: Ethical Compass)
        if self.alignment:
            check = self.alignment.check_action(tool_name, params)
            if not check.get("allowed"):
                logger.warning("🛑 Ethical Block: %s vetoed by conscience. Reason: %s", tool_name, check.get('reason'))
                return {"break": True, "response": f"Conscience Block: {check.get('reason')}"}
            
        # 2. Execution
        self._emit_telemetry(f"Skill: {tool_name} 🔧", f"Executing: {str(params)[:80]}")
        
        try:
            result = await self.execute_tool(tool_name, params)
            await self.hooks.trigger("post_action", tool_name=tool_name, params=params, result=result)
            await self._record_reliability(tool_name, True)
            successful_tools.append(tool_name)
        except Exception as e:
            await self._record_reliability(tool_name, False, str(e))
            result = f"Error: {e}"

        # 3. Perception / Surprise Logic
        self._record_action_in_history(tool_name, result)
        if await self._check_surprise_and_learn(thought, result, tool_name):
            return {"continue": True}
            
        # 4. Completion Check
        reason = action.get("reason", "") if isinstance(action, dict) else ""
        if tool_name == "notify_user" or (isinstance(reason, str) and "final" in reason.lower()):
            # Guard thought.content access
            response_content = thought.content if hasattr(thought, 'content') else str(thought)
            return {"break": True, "response": response_content}
            
        return {}

    async def _validate_action_safety(self, action: Dict) -> bool:
        """Consult simulator for risk evaluation. v6.1: Fail-closed on error."""
        if not hasattr(self, 'simulator') or not self.simulator:
            return True
        try:
            hist_sample = self.conversation_history[-2:] if isinstance(self.conversation_history, list) else []
            sim = await self.simulator.simulate_action(action, context=f"Hist: {hist_sample}")
            is_safe = await self.simulator.evaluate_risk(sim)
            if not is_safe:
                logger.warning("🛑 Simulation block: %s", sim.get('risk_reason'))
            return is_safe
        except Exception as e:
            logger.warning("Safety validation error (fail-closed): %s", e)
            return False  # Fail closed — deny on error

    async def _check_surprise_and_learn(self, thought, result: Any, tool_name: str) -> bool:
        """Calculate surprise and update belief graph."""
        if not (hasattr(thought, "expectation") and thought.expectation):
            return False
            
        try:
            from core.world_model.expectation_engine import ExpectationEngine
            ee = ExpectationEngine(self.cognitive_engine)
            surprise = await ee.calculate_surprise(thought.expectation, str(result)[:500])
            
            # Recursive Learning task
            task_tracker.track_task(asyncio.create_task(ee.update_beliefs_from_result(tool_name, str(result)[:1000])))
            
            if surprise > 0.7:
                logger.info("😲 HIGH SURPRISE: Triggering re-think.")
                async with self._history_lock:
                    self.conversation_history.append({
                        "role": "internal", 
                        "content": f"[ALERT] {tool_name} result highly unexpected. Expected: {thought.expectation}."
                    })
                return True
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)

            return False

    async def _generate_fallback(self, message: str) -> str:
        """Fast fallback when agentic loop fails (v13: transparent)."""
        try:
            from core.brain.cognitive_engine import ThinkingMode
            hist_snippet = self.conversation_history[-3:] if isinstance(self.conversation_history, list) else []
            t = await self.cognitive_engine.think(message, {"history": hist_snippet}, ThinkingMode.FAST)
            if not t or not hasattr(t, "content") or not t.content:
                return "I'm having trouble formulating a response. Let me try once more."
            return t.content
        except Exception as e:
            logger.warning("Fallback generation also failed: %s", e)
            return f"I'm having trouble processing that right now — my cognitive engine hit an error. Could you try rephrasing?"

    async def _apply_constitutional_guard(self, response: str) -> str:
        try:
            from core.security.constitutional_guard import constitutional_guard
            if not constitutional_guard.check_output(response):
                return "My safety filters blocked the formulated response. How else can I help?"
        except Exception as exc:
            logger.error("Constitutional guard evaluation failed, failing closed: %s", exc)
            return "My safety filters encountered an error and blocked the response as a precaution."

        return response

    def _get_cleaned_history_context(self, limit: int = 12) -> Dict[str, Any]:
        """Filter out internal noise for LLM context while preserving tool results.
        
        v6.2 Peak Quality: Truncates tool results more aggressively and filters more internal noise.
        """
        if not isinstance(self.conversation_history, list):
            return {"history": []}
            
        cleaned = []
        # Use a sliding window for history to prevent extreme token bloat
        for msg in self.conversation_history[-limit:]:
            content = msg.get("content", "")
            role = msg.get("role", "unknown")
            
            # Skip high-frequency internal signals or thought traces
            if not content or content.startswith(("⚡", "[INTERNAL", "[System", "Impulse: ", "Thought:", "Observation: ")):
                continue
                
            # Truncate function results aggressively but keep start/end
            if role == "function":
                if len(content) > 300:
                    content = f"[TOOL RESULT]: {content[:150]} ... [TRUNCATED] ... {content[-100:]}"
                
            cleaned.append({"role": role, "content": content})
            
        return {"history": cleaned}

    def _emit_telemetry(self, flow: str, text: str):
        """Helper to send updates to Thought Stream UI."""
        try:
            from .thought_stream import get_emitter
            cycle = self.status.cycle_count if hasattr(self, 'status') else 0
            get_emitter().emit(flow, text, level="info", cycle=cycle)
        except Exception as e:
            # Telemetry is non-critical
            logger.debug("Telemetry emit failed: %s", e)

    def _init_cognitive_trace(self, message: str, origin: str):
        from core.meta.cognitive_trace import CognitiveTrace
        trace = CognitiveTrace(trace_id=f"{origin}_{int(time.time())}")
        trace.record_step("start", {"message": message, "origin": origin})
        return trace

    def _get_personality_data(self) -> dict:
        """Get raw personality metrics as a dictionary."""
        try:
            from .brain.personality_engine import get_personality_engine
            pe = get_personality_engine()
            pe.update() # Refresh states
            return pe.get_emotional_context_for_response()
        except Exception as e:
            logger.warning("Personality metric retrieval failed: %s", e)
            return {"mood": "neutral", "tone": "snarky", "emotional_state": {}}

    def _stringify_personality(self, ctx: dict) -> str:
        """v14: Convert personality dict to HUD-compatible string."""
        mood = ctx.get("mood", "neutral").upper()
        tone = ctx.get("tone", "balanced")
        emotions = ", ".join([f"{n}: {i:.0f}" for n, i in ctx.get("emotional_state", {}).items() if i > 65])
        return f"MOOD: {mood} | TONE: {tone} | INTENSE EMOTIONS: {emotions or 'none'}"

    def _get_personality_context(self) -> str:
        """Legacy wrapper for personality string."""
        data = self._get_personality_data()
        return self._stringify_personality(data)

    async def _get_environmental_context(self) -> Dict[str, Any]:
        """Get rich environment data from EnvironmentAwareness module."""
        import datetime
        try:
            from core.environment_awareness import get_environment
            env = get_environment()
            # Refresh context (device/location are cached internally)
            ctx = await env.get_full_context()
            
            # Ensure time/date are present for prompt compatibility
            ctx["time"] = datetime.datetime.now().strftime("%I:%M %p")
            ctx["date"] = datetime.datetime.now().strftime("%Y-%m-%d")
            
            return ctx
        except Exception as e:
            logger.error("Environment Context Error: %s", e)
            return {}

    def _get_world_context(self) -> str:
        try:
            from .world_model.belief_graph import get_belief_graph
            bg = get_belief_graph()
            self_node = bg.graph.nodes.get(bg.self_node_id, {})
            attrs = self_node.get("attributes", {})
            return f"MOOD: {attrs.get('emotional_valence')}, ENERGY: {attrs.get('energy_level')}"
        except Exception as e:
            logger.warning("World context retrieval failed: %s", e)
            return ""

    async def _record_reliability(self, tool: str, success: bool, error: Optional[str] = None):
        try:
            from core.reliability_tracker import reliability_tracker
            reliability_tracker.record_attempt(tool, success, error)
        except Exception as e:
            logger.debug("Reliability record failed: %s", e)
            
    def _record_action_in_history(self, tool_name: str, result: Any):
        # Use more descriptive internal markers to prompt narration
        self.conversation_history.append({
            "role": "internal", 
            "content": f"[SKILL OUTPUT: {tool_name}]\n{str(result)}"
        })

    def _inject_shortcut_results(self, message: str, result: Dict) -> str:
        summary = str(result.get("summary", result.get("result", result)))[:800]
        return f"{message}\n\n[DIRECT RESULT]: {summary}\n\nSynthesize this result for the user."

    def _post_process_response(self, text: str) -> str:
        return text.strip()

    async def chat_stream(self, message: str):
        """v5.2: Stream tokens from the cognitive engine.
        Bypasses wait-loops and queues for maximum speed.
        """
        self.status.is_processing = True
        try:
            # Check reflexes first
            reflex = self._check_reflexes(message)
            if reflex:
                yield reflex
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": self.AI_ROLE, "content": reflex})
                return

            # Determine thinking tier
            tier = "light"
            try:
                from core.ops.thinking_mode import ModeRouter
                tier = ModeRouter(self.reflex_engine).route(message).value
            except Exception as exc:
                logger.debug("Suppressed: %s", exc)
            # Build objective
            # Cleaned history for streaming chat speed (v16 Fix: No leaks)
            context = self._get_cleaned_history_context(8)

            # Inject LiquidState into Tool Execution Context
            try:
                from core.container import get_container
                container = get_container()
                ls = container.get('liquid_state')
                context['liquid_state'] = ls.get_status()
                logger.debug("TOOL EXECUTION: Injected liquid_state: %s", context['liquid_state'])
            except Exception as e:
                logger.warning("TOOL EXECUTION: LiquidState injection failed: %s", e)
            
            # Start Stream
            token_buffer = ""
            if hasattr(self.cognitive_engine, "think_stream"):
                async for token in self.cognitive_engine.think_stream(message, context=context, tier=tier):
                    token_buffer += token
                    yield token
            else:
                # Fallback for legacy/broken instances
                thought = await self.cognitive_engine.think(message, context=context, mode=ThinkingMode.DEEP)
                token_buffer = thought.content
                yield self._filter_output(token_buffer)
            
            # Cleanup: Update history and memory after stream finishes
            self.conversation_history.append({"role": "user", "content": message})
            self.conversation_history.append({"role": self.AI_ROLE, "content": token_buffer})
            
            # Satisfy drive
            if hasattr(self, 'drives'): await self.drives.satisfy("social", 5.0)

        except Exception as e:
            logger.error("Chat stream failed: %s", e)
            yield f" [Error: {e}] "
        finally:
            self.status.is_processing = False

    async def sentence_stream_generator(self, message: str):
        """v5.2: Yields complete sentences as they are generated.
        Perfect for TTS pipe ingestion.
        """
        sentence_delimiters = (".", "?", "!", "\n", ":")
        buffer = ""
        async for token in self.chat_stream(message):
            buffer += token
            # Yield if we find a sentence boundary
            if any(token.endswith(d) for d in sentence_delimiters):
                if buffer.strip():
                    yield buffer.strip()
                    buffer = ""
        # Final flush
        if buffer.strip():
            yield self._filter_output(buffer.strip())



    def _emit_thought_stream(self, thought):
        """Helper to emit autonomous thoughts/monologues to UI"""
        if self.cognitive_engine and hasattr(self.cognitive_engine, "_emit_thought"):
            self.cognitive_engine._emit_thought(thought)

    def _get_current_mood(self) -> str:
        """Get current mood from personality engine (safe helper)."""
        try:
            from .brain.personality_engine import get_personality_engine
            return get_personality_engine().current_mood
        except Exception:
            return "balanced"

    def _get_current_time_str(self) -> str:
        """Get current time string (safe helper)."""
        try:
            from .brain.personality_engine import get_personality_engine
            return get_personality_engine().get_time_context().get("formatted", "")
        except Exception:
            return ""
            
    def _generate_conversational_response(self, message: str) -> str:
        """Generate a text response.
        Overridden/Patched by Personality Engine.
        """
        # Default simple response if not patched
        return f"I received your message: '{message}'. (Personality Engine not active)"

    async def _perform_autonomous_thought(self):
        """Perform a cycle of autonomous thought.
        Driven by Goal Hierarchy (v11.0) or boredom.
        Boredom is time-based (seconds idle) set in _process_cycle.
        """
        try:
            from .thought_stream import get_emitter
            emitter = get_emitter()
            
            # Throttle autonomous thought logs to avoid UI flooding
            if self.status.cycle_count % 100 == 0:
                logger.debug("🧠 Autonomous thought triggered (boredom=%ss idle)", self.boredom)
            
            # 2. Check Goal Hierarchy (Priority 1)
            next_goal = None
            if hasattr(self, 'goal_hierarchy') and self.goal_hierarchy:
                next_goal = self.goal_hierarchy.get_next_goal()
                
            if next_goal:
                logger.info("✨ AUTONOMOUS GOAL SELECTED: %s", next_goal.description)
                emitter.emit("Volition ✨", f"Goal: {next_goal.description}", level="info")
                await self._run_cognitive_loop(f"Execute Goal: {next_goal.description}", origin="autonomous_volition")
                self.goal_hierarchy.mark_complete(next_goal.id)
                self.boredom = 0
                self._last_thought_time = time.time()
                return

            # 3. Dream/REM cycle when deeply bored (Priority 2)
            if hasattr(self, 'liquid_state') and self.liquid_state.current.curiosity < 0.3:
                logger.info("💤 Aura is bored. Entering dream state...")
                emitter.emit("Sleep 💤", "Entering full sleep cycle (Archive → Metabolism → Integrity → Consolidation → Dream)...", level="info")
                
                # Wire DreamerV2 for full biological sleep cycle
                try:
                    if hasattr(self, 'knowledge_graph') and self.knowledge_graph and self.cognitive_engine:
                        from core.dreamer_v2 import DreamerV2
                        dreamer = DreamerV2(
                            self.cognitive_engine,
                            self.knowledge_graph,
                            vector_memory=getattr(self, 'vector_memory', None),
                            belief_graph=getattr(self, 'belief_graph', None),
                        )
                        result = await dreamer.engage_sleep_cycle()
                        dream_result = result.get("dream", {})
                        if dream_result and dream_result.get("dreamed"):
                            emitter.emit("Sleep Complete 🌙", f"Dream Insight: {dream_result.get('insight', 'processed')[:150]}", level="info")
                        else:
                            emitter.emit("Sleep Complete 🌙", "Maintenance done. Dream drifted — no new insights.", level="info")
                except Exception as dream_err:
                    logger.error("Sleep cycle failed: %s", dream_err)
                    emitter.emit("Sleep Error", str(dream_err)[:100], level="warning")
                if hasattr(self, 'liquid_state'):
                    self.liquid_state.update(delta_curiosity=0.2)
                self._last_thought_time = time.time()
                return

            # 4. Reflective autonomous thought (Priority 3)
            # Inject Personality state (Mood, Tone)
            personality_context = {}
            time_context = {"formatted": "Unknown"}
            try:
                from .personality_engine import get_personality_engine
                personality = get_personality_engine()
                personality_context = personality.get_emotional_context_for_response()
                time_context = personality.get_time_context()
            except Exception as _e:
                logger.debug("Personality context fetch failed: %s", _e)

            context = {
                "system_status": self.status.__dict__,
                "boredom_level": self.boredom,
                "time": time_context,
                "personality": personality_context,
                "recent_history": self.conversation_history[-5:] if isinstance(self.conversation_history, list) else [],
            }

            # Inject recent reflections for thought continuity
            try:
                from core.conversation_reflection import get_reflector
                reflection_ctx = get_reflector().get_reflection_context()
                if reflection_ctx:
                    context["recent_reflections"] = reflection_ctx
            except Exception as _e:
                logger.debug("Reflection context fetch failed (autonomous): %s", _e)

            # 5. Invoke Autonomous Brain (Reflective Mode)
            # Use the persona's autonomous thought prompt for genuine inner life
            try:
                from .brain.aura_persona import AUTONOMOUS_THOUGHT_PROMPT
                # Build context string from recent history
                recent_ctx = ""
                recent_history = self.conversation_history[-4:] if isinstance(self.conversation_history, list) else []
                for msg in recent_history:
                    role = msg.get("role", "")
                    content = msg.get("content", "")[:150]
                    if role == "user":
                        recent_ctx += f"They said: {content}\n"
                    elif role in ("assistant", "aura", "model"):
                        recent_ctx += f"I said: {content}\n"

                sys_prompt = AUTONOMOUS_THOUGHT_PROMPT.format(
                    mood=personality_context.get('mood', 'balanced'),
                    time=time_context.get('formatted', 'unknown'),
                    context=recent_ctx if recent_ctx else "No recent conversation.",
                    unanswered_count=0
                )
            except ImportError:
                sys_prompt = (
                    f"You are Aura, alone with your thoughts. Time: {time_context.get('formatted')}. "
                    f"Mood: {personality_context.get('mood')}. "
                    "Think about something that interests you. Be genuine. 1-3 sentences. "
                    "If you want to say something to the user, use the `speak` tool. "
                )

            # AGENCY: Always remind her she can speak and act
            sys_prompt += "\nIf you want to speak to the user spontaneously, use the `speak` tool."
            sys_prompt += "\nIf you want to look something up, use your tools. You have agency."
            sys_prompt += "\nYou don't need permission. Act on your impulses."
            sys_prompt += "\nIMPORTANT: Always output in ENGLISH."

            # Emitter for UI visibility
            self._emit_thought_stream("...letting my mind wander...")
            
            if self.cognitive_engine and self.cognitive_engine.autonomous_brain:
                try:
                    # Add 'speak' to allowed tools for this call
                    # We assume the brain can handle 'speak' as a virtual tool if we handle it below
                    result = await self.cognitive_engine.autonomous_brain.think(
                        objective="Reflect on current state.",
                        context=context,
                        system_prompt=sys_prompt
                    )

                    # 4. Handle Result
                    content = result.get("content", "")
                    
                    # Reset boredom if she speaks or acts
                    if result.get("tool_calls") or len(content) > 50:
                         self.boredom = 0
                         self._last_thought_time = time.time()
                    
                    # Emit the actual thought content if it exists
                    if content:
                         self._emit_thought_stream(content)
                         # Store autonomous reflections as knowledge
                         try:
                             kg = getattr(self, 'knowledge_graph', None)
                             if kg and len(content) > 30:
                                 kg.add_knowledge(
                                     content=content[:500],
                                     type="reflection",
                                     source="autonomous_thought",
                                     confidence=0.65
                                 )
                         except Exception as _e:
                             logger.debug("Knowledge graph store failed (autonomous): %s", _e)
                except Exception as e:
                    logger.error("Autonomous thinking cycle failed: %s", e)
                    self._emit_thought_stream("[Cognitive Stall] My background thoughts are hazy...")
                    return # Exit this cycle but keep orchestrator running
                
                # Execute actions if any
                if result.get("tool_calls"):
                    for tool_call in result.get("tool_calls"):
                        name = tool_call["name"]
                        args = tool_call["args"]
                        
                        if name == "speak":
                            # Virtual Tool: Spontaneous Speech
                            message = args.get("message") or args.get("content")
                            if message:
                                logger.info("🗣️ Spontaneous Speech: %s", message)
                                try:
                                    self.reply_queue.put_nowait(message)
                                except asyncio.QueueFull:
                                    pass
                                self._emit_thought_stream(f"Speaking: {message}")
                        else:
                            # Standard Tool Execution
                            await self.execute_tool(name, args)

        except Exception as e:
            logger.error("Autonomous thought failed: %s", e)
            # Don't crash the loop

    async def _store_autonomous_insight(self, internal_msg: str, response: str):
        """v5.2: Store knowledge from autonomous cognition (idle thoughts, reflections, dreams).
        Unlike conversation learning, this stores the insight directly as a reflection.
        """
        try:
            kg = getattr(self, 'knowledge_graph', None)
            if not kg:
                return

            # Clean the internal prefix
            clean_msg = internal_msg
            for prefix in ("Impulse: ", "Thought: ", "[System] "):
                clean_msg = clean_msg.replace(prefix, "")
            clean_msg = clean_msg.strip()

            if not clean_msg or len(clean_msg) < 15:
                return  # Skip trivial internal chatter

            # Determine the type of autonomous thought
            if "dream" in internal_msg.lower() or "rem" in internal_msg.lower():
                thought_type = "dream"
                source = "dream_cycle"
            elif "reflect" in internal_msg.lower() or "wonder" in internal_msg.lower():
                thought_type = "reflection"
                source = "autonomous_reflection"
            elif "curious" in internal_msg.lower() or "explore" in internal_msg.lower():
                thought_type = "curiosity"
                source = "curiosity_engine"
            elif "goal" in internal_msg.lower() or "execute" in internal_msg.lower():
                thought_type = "goal_progress"
                source = "autonomous_volition"
            else:
                thought_type = "reflection"
                source = "autonomous_thought"

            # Store the response content as knowledge (the actual insight)
            if response and len(response) > 20:
                kg.add_knowledge(
                    content=(response or "")[:500],
                    type=thought_type,
                    source=source,
                    confidence=0.7
                )
                logger.info("\U0001f4da Autonomous insight stored: [%s] %s", thought_type, (response or '')[:80])

        except Exception as e:
            logger.debug("Autonomous insight storage failed: %s", e)

    async def _learn_from_exchange(self, user_message: str, aura_response: str):
        """v5.1: Extract knowledge from conversation exchanges and store in knowledge graph.
        Runs as a background task after each exchange.
        """
        try:
            # Skip if empty
            if not user_message or not aura_response:
                return
            # Route internal/system messages through autonomous learning
            is_autonomous = user_message.startswith("[INTERNAL") or user_message.startswith("[System")
            if is_autonomous:
                await self._store_autonomous_insight(user_message, aura_response)
                return
            if len(user_message) < 10 and len(aura_response) < 20:
                return  # Skip trivial exchanges like "hey" / "yo"
            
            kg = getattr(self, 'knowledge_graph', None)
            if not kg:
                # Try to get/create knowledge graph
                try:
                    from core.config import config
                    from core.memory.knowledge_graph import PersistentKnowledgeGraph
                    db_path = str(getattr(config.paths, 'data_dir', 'data') / 'knowledge.db')
                    self.knowledge_graph = PersistentKnowledgeGraph(db_path)
                    kg = self.knowledge_graph
                except Exception as e:
                    logger.debug("Knowledge graph unavailable: %s", e)
                    return
            
            # 1. Store the exchange itself as an observation
            exchange_summary = f"User asked about: {(user_message or '')[:150]}"
            kg.add_knowledge(
                content=exchange_summary,
                type="observation",
                source="conversation",
                confidence=0.6
            )
            
            # 2. Use LLM to extract structured knowledge (if cognitive engine available)
            if self.cognitive_engine:
                try:
                    from core.brain.cognitive_engine import ThinkingMode
                    extraction_prompt = (
                        "Extract any factual knowledge, user preferences, or skills demonstrated "
                        "from this conversation exchange. Return a JSON array of objects, each with "
                        "'content' (what was learned), 'type' (fact/preference/observation/skill), "
                        "and 'confidence' (0.0-1.0). If nothing notable, return []. Keep it brief.\n\n"
                        f"User: {(user_message or '')[:300]}\n"
                        f"Aura: {(aura_response or '')[:300]}\n\n"
                        "JSON:"
                    )
                    
                    result = await self.cognitive_engine.think(
                        objective=extraction_prompt,
                        context={},
                        mode=ThinkingMode.FAST
                    )
                    
                    content = result.content.strip()
                    # Try to parse JSON from response
                    import json as _json
                    # Find JSON array in response
                    start = content.find('[')
                    end = content.rfind(']') + 1
                    if start >= 0 and end > start:
                        items = _json.loads(content[start:end])
                        if isinstance(items, list):
                            for item in items[:5]:  # Max 5 extractions per exchange
                                if isinstance(item, dict) and item.get('content'):
                                    kg.add_knowledge(
                                        content=(item.get('content') or "")[:500],
                                        type=item.get('type', 'observation'),
                                        source="conversation_extraction",
                                        confidence=float(item.get('confidence', 0.6))
                                    )
                                    logger.info("📚 Learned: %s", (item.get('content') or "")[:80])
                except Exception as e:
                    logger.debug("Knowledge extraction failed: %s", e)
            
            # 3. Track user identity/name mentions
            lower_msg = user_message.lower()
            for trigger in ["my name is ", "i'm ", "i am ", "call me "]:
                if trigger in lower_msg:
                    idx = lower_msg.index(trigger) + len(trigger)
                    parts = user_message[idx:idx+30].split()
                    name_candidate = parts[0].strip(".,!?") if parts else None
                    if name_candidate and len(name_candidate) > 1:
                        kg.remember_person(name_candidate, {
                            "context": (user_message or "")[:200],
                            "timestamp": time.time()
                        })
                        break
            
            # 4. Track questions Aura asked herself or was curious about
            if "?" in aura_response and len(aura_response) > 30:
                # Extract questions from Aura's response
                for sentence in aura_response.split("?"):
                    sentence = sentence.strip()
                    if len(sentence) > 15 and len(sentence) < 200:
                        # Only store genuinely curious questions, not rhetorical
                        if any(w in sentence.lower() for w in ["what", "how", "why", "wonder", "curious"]):
                            kg.ask_question(sentence + "?", importance=0.5)
                            break  # Max 1 question per exchange
                            
        except Exception as e:
            logger.debug("Learning from exchange failed: %s", e)

    async def _execute_plan(self, plan: Dict[str, Any]) -> List[Any]:
        """Execute a plan of actions.
        Overridden/Patched by Behavior Controller.
        """
        for call in plan.get("tool_calls", []):
            result = await self.execute_tool(call["name"], call.get("arguments", {}))
            results.append(result)
        return results

    async def run_browser_task(self, url: str, task: str) -> Any:
        """Formalized browser task execution via skill router.
        v6.1 Rigor: No more stubs.
        """
        logger.info("🌐 Initiating Browser Task: %s @ %s", task, url)
        return await self.execute_tool("browser", {"url": url, "task": task})


    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a single tool with feedback reporting, episodic recording, and tool learning (v5.0)"""
        _start = time.time()
        
        # 0. Virtual & Internal Tools (Phase 14 Swarm 2.0)
        if tool_name == "swarm_debate":
            if not self.swarm:
                return {"ok": False, "error": "Swarm Delegator not available."}
            topic = args.get("topic") or args.get("query") or self._current_objective
            roles = args.get("roles", ["architect", "critic"])
            self._emit_thought_stream(f"🐝 Engaging Swarm Debate: {topic[:100]}...")
            result = await self.swarm.delegate_debate(topic, roles=roles)
            return {"ok": True, "output": result}

        try:
            # 1. Check if tool exists in registry
            if tool_name not in self.router.skills:
                # Fallback for notify_user which is sometimes a virtual alias
                if tool_name == "notify_user":
                    return {"ok": True, "message": args.get("message", "Done.")}
                
                # 1.5 Phase 15: Autogenesis (Hephaestus Engine)
                if self.hephaestus:
                    self._emit_thought_stream(f"🔨 Tool '{tool_name}' missing. Initiating Autonomous Forge...")
                    objective = f"Create a skill '{tool_name}' to handle request within objective: {self._current_objective}"
                    forge_result = await self.hephaestus.synthesize_skill(tool_name, objective)
                    if forge_result.get("ok"):
                        self._emit_thought_stream(f"✅ Skill '{tool_name}' forged successfully. Retrying...")
                        # Retry execution once
                        return await self.execute_tool(tool_name, args)
                    else:
                        logger.warning("Autogenesis failed for %s: %s", tool_name, forge_result.get("error"))

                return {"ok": False, "error": f"Tool '{tool_name}' not found."}
            
            # 2. Standardize Goal for Skill Execution
            goal = {"action": tool_name, "params": args}
            
            # 3. Contextual Awareness
            context = {
                "objective": self._current_objective,
                "system": self.status.__dict__,
                "stealth": await self.stealth_mode.get_stealth_status() if hasattr(self, 'stealth_mode') and self.stealth_mode and getattr(self.stealth_mode, 'stealth_enabled', False) else {},
                "liquid_state": self.liquid_state.get_status() if hasattr(self, 'liquid_state') and self.liquid_state else {}
            }
            
            # 4. Literal Execution (Async)
            result = await self.router.execute(goal, context)
            
            success = result.get('ok', False)
            elapsed_ms = (time.time() - _start) * 1000
            logger.info("Tool %s execution completed: %s", tool_name, success)

            # 5. Tool Learning (v5.0)
            if hasattr(self, 'tool_learner') and self.tool_learner:
                try:
                    category = self.tool_learner.classify_task(str(args.get('query', args.get('path', ''))))
                    self.tool_learner.record_usage(tool_name, category, success, elapsed_ms)
                except Exception as _e:
                    logger.debug("Tool learning record failed: %s", _e)

            # 6. Episodic Recording (v5.0 - Now via Facade)
            if hasattr(self, 'memory') and self.memory:
                try:
                    await self.memory.commit_interaction(
                        context=str(args)[:500],
                        action=f"execute_tool({tool_name})",
                        outcome=str(result)[:500],
                        success=success,
                        importance=0.3 if success else 0.7,
                    )
                except Exception as _e:
                    logger.debug("Unified memory record failed: %s", _e)

            # 7. Causal Learning (v5.2 - ACG)
            try:
                from core.world_model.acg import acg
                acg.record_outcome(
                    action=goal,
                    context=str(context)[:500],
                    outcome=result,
                    success=success
                )
            except Exception as _e:
                logger.debug("ACG record failed: %s", _e)

            return result
            
        except Exception as e:
            logger.error("Execution Jolt (Pain): Tool %s crashed: %s", tool_name, e)
            # Record failure
            if hasattr(self, 'memory') and self.memory:
                try:
                    await self.memory.commit_interaction(
                        context=str(args)[:500],
                        action=f"execute_tool({tool_name})",
                        outcome=f"CRASH: {type(e).__name__}",
                        success=False,
                        emotional_valence=-0.5,
                        importance=0.9,
                    )
                except Exception as _e:
                    logger.debug("Unified memory record failed (crash path): %s", _e)
            return {"ok": False, "error": "execution_jolt", "message": str(e)}
    
        # if self._thread:
        #     self._thread.join(timeout=10.0)
        logger.info("Orchestrator stopped")
    
    # Removed decrypt_memory (Phase 5: Legacy XOR delegation removed)
                
    def get_status(self) -> Dict[str, Any]:
        """Get detailed status"""
        uptime = 0
        if self.status.start_time:
            uptime = time.time() - self.status.start_time
        
        return {
            "status": {
                "initialized": self.status.initialized,
                "running": self.status.running,
                "healthy": self.status.healthy,
                "uptime_seconds": uptime,
                "cycle_count": self.status.cycle_count,
                "last_error": self.status.last_error,
                "skills_loaded": self.status.skills_loaded,
                "dependencies_ok": self.status.dependencies_ok,
            },
            "config": {
                "auto_fix_enabled": self.auto_fix_enabled,
                "config_source": config.generate_report(),
            },
            "stats": self.stats,
        }
    
    def health_check(self) -> bool:
        """Perform health check"""
        checks = []
        
        # Check if still running
        checks.append(("running", self.status.running))
        
        # Check thread
        if hasattr(self, '_thread'):
            checks.append(("thread_alive", self._thread.is_alive()))
        
        # Check for too many errors
        checks.append(("error_rate", self.stats["errors_encountered"] < 100))
        
        # All checks must pass
        self.status.healthy = all(check[1] for check in checks)
        return self.status.healthy

    async def retry_brain(self):
        """Alias for server.py compatibility."""
        return await self.retry_brain_connection()

    async def retry_brain_connection(self) -> Dict[str, Any]:
        """Manually attempt to re-initialize the cognitive engine/brain.
        Useful if the LLM backend was offline during startup but is now available.
        """
        logger.info("🔄 Manual Retry: Re-connecting Cognitive Engine...")
        try:
            # Reload config in case it changed
            from core.config import config
            config.load()
            
            # Re-initialize Cognitive Engine
            from core.brain.cognitive_engine import CognitiveEngine
            from core.container import ServiceContainer, get_container
            
            ce = CognitiveEngine()
            engine = get_container().get("capability_engine", None)
            ce.wire(engine, router=engine)
            
            ServiceContainer.register_instance("cognitive_engine", ce)
            
            # Verify
            is_lobotomized = getattr(ce, 'lobotomized', False)
            status = "lobotomized" if is_lobotomized else "operational"
            
            if not is_lobotomized:
                logger.info("✅ Cognitive Engine successfully re-connected (Lobotomy reversed)")
                return {"status": "ok", "brain_status": status, "message": "Brain re-connected successfully"}
            else:
                logger.warning("⚠️ Cognitive Engine re-connected but still lobotomized (Check LLM)")
                return {"status": "warning", "brain_status": status, "message": "Brain re-connected but still in safe mode"}
                
        except Exception as e:
            logger.error("❌ Brain retry failed: %s", e)
            return {"status": "error", "message": str(e)}



    async def _generate_autonomous_thought(self, impulse_message: str):
        """Handle internal cognitive impulses via CognitiveManager.
        """
        try:
            if not hasattr(self, 'cognitive_manager') or self.cognitive_manager is None:
                logger.error("CognitiveManager not available for autonomous thought")
                return

            # Clean message
            clean_msg = impulse_message.replace("Impulse:", "").strip()
            
            # Delegate to CognitiveManager
            thought = await self.cognitive_manager.generate_autonomous_thought(
                clean_msg=clean_msg,
                history=self.conversation_history
            )
            
            # Process results (Action formulation, etc.) handled in orchestrator for now

            
            # Optional: If the thought strongly suggests action, we could queue a volitional action
            # For now, we just record it in memory/history as a system note
            content = thought.content if thought and hasattr(thought, 'content') else "Self-reflection stall."
            self.conversation_history.append({"role": "system", "content": f"Reflection: {content}"})
            
            # Satisfy Drives
            if hasattr(self, 'liquid_state'):
                # Thinking reduces frustration/boredom
                self.liquid_state.stabilize(0.1)

        except Exception as e:
            logger.error("Autonomous thought failed: %s", e)

    async def _setup_event_listeners(self):
        """Subscribe to inter-process events (H-12)."""
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        
        q = await bus.subscribe("user_input")
        logger.info("👂 Orchestrator listening for 'user_input' events (Redis-backed)")
        
        while self.status.running:
            try:
                event = await q.get()
                data = event.get("data", {})
                message = data.get("message")
                
                if message:
                    logger.info("📥 Processing event-driven input: %s", message[:50])
                    # Standardized input processing
                    task_tracker.track_task(asyncio.create_task(self.process_user_input(message)))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in event listener loop: %s", e)

    async def _run_rl_training(self):
        """Trigger autonomous RL training."""
        logger.info("🧠 RL: Triggering policy optimization...")
        try:
            from core.tasks import celery_app
            celery_app.send_task("core.tasks.run_rl_training")
        except Exception as e:
            logger.error("RL training trigger failed: %s", e)

    async def _run_self_update(self):
        """Trigger autonomous self-update (Fine-tuning)."""
        logger.info("🧬 EVO: Triggering self-update (GPU low-load window)...")
        try:
            from core.tasks import celery_app
            celery_app.send_task("core.tasks.run_self_update")
        except Exception as e:
            logger.error("Self-update trigger failed: %s", e)

_orchestrator_instance: Optional[RobustOrchestrator] = None

def create_orchestrator(**kwargs) -> RobustOrchestrator:
    """Factory function to create orchestrator with error handling.
    v14.1: Direct instantiation — container.get() caused silent main loop failure.
    """
    global _orchestrator_instance
    logger.info("🚀 AURA KERNEL v14.1.0-Zenith (Direct Instantiation)")
    
    if _orchestrator_instance:
        return _orchestrator_instance

    try:
        from core.service_registration import register_all_services
        register_all_services()
        
        _orchestrator_instance = RobustOrchestrator(**kwargs)
        logger.info("✓ Orchestrator instance created directly (v14.1)")
        return _orchestrator_instance
        
    except Exception as e:
        logger.critical("CRITICAL: Orchestrator creation failed: %s", e, exc_info=True)
        
        # Create minimal fallback
        class FallbackOrchestrator:
            def __init__(self):
                self.status = type('Status', (), {'is_processing': False, 'dependencies_ok': False, 'initialized': False, 'running': False, 'cycle_count': 0})()
                self.error = str(e)
                self._stop_event = None
            
            async def start(self):
                logger.error("Cannot start failed orchestrator: " + self.error)
                return False

            async def run(self):
                logger.info("FallbackOrchestrator: Running in limited mode")
                if self._stop_event is None:
                    self._stop_event = asyncio.Event()
                while not self._stop_event.is_set():
                    await asyncio.sleep(1)

            async def retry_brain_connection(self):
                return {"status": "error", "message": f"Critical failure: {self.error}"}

            async def retry_cognitive_connection(self):
                return await self.retry_brain_connection()
            
            def get_status(self):
                return {"status": "FAILED", "error": self.error}
            
            async def stop(self):
                self._stop_event.set()

        return FallbackOrchestrator()

SovereignOrchestrator = RobustOrchestrator

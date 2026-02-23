"""Orchestrator Boot Mixin"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import config
from .container import ServiceContainer
from .managers.drive_controller import DriveController
from .managers.health_monitor import HealthMonitor
from .orchestrator_types import SystemStatus
from .resilience.state_manager import StateManager
from .security.ast_guard import ASTGuard
from .utils.hook_manager import HookManager
from .capability_engine import CapabilityEngine
from .privacy_stealth import get_stealth_mode
from core.resilience.cognitive_wal import cognitive_wal

logger = logging.getLogger(__name__)

class OrchestratorBootMixin:
    """Mixin handling initialization of subsystems and core architecture."""

    async def _async_init_subsystems(self):
        """Heavy lifting for subsystem initialization (Async)."""
        if self.status.initialized:
            return
            
        logger.info("🧠 BOOT: Starting Subsystem Initialization...")
        try:
            # Resilience & Monitoring
            logger.info("Booting Resilience & Monitoring...")
            self._init_resilience()
            
            # Skill Management
            logger.info("Discovering skills...")
            self._init_skill_system()
            
            # Cognitive & Emotional Core
            logger.info("Wiring Cognitive Core...")
            self._init_cognitive_core()
            
            # Sensory & Interaction Systems
            logger.info("Opening Senses...")
            self._init_sensory_systems()
            
            # Autonomous Evolution & Proactive Logic
            logger.info("🔎 DEBUG: Activating Autonomous Self-Modification...")
            self._init_autonomous_evolution()
            logger.info("🔎 DEBUG: Scaling Curiosity Engine...")
            # 12. Metabolic Health (v18.0)
            logger.info("🔎 DEBUG: Initializing Metabolic Monitor...")
            self._init_metabolism()
            
            # Cognitive Integration (DEFERRED FROM SYNC INIT)
            logger.info("🔎 DEBUG: Integrating cognitive systems...")
            await self._integrate_systems()
            logger.info("🔎 DEBUG: Integration complete.")
            
            logger.info("💾 BOOT: Loading persistent system state...")
            self._load_state()

            # THE FIX: Phase 26 Sovereign Consistency
            # 1. Recover interrupted thoughts from WAL
            await self._recover_wal_state()
            
            # 2. Calculate Temporal Drift (How long was I asleep?)
            self._calculate_temporal_drift()

            # 3. Start Memory Defragmenter (Semantic Sleep)
            from core.memory.semantic_defrag import start_defrag_scheduler
            asyncio.create_task(start_defrag_scheduler())
            
            logger.info("✅ BOOT COMPLETE: Orchestrator architecture online")
            self.status.initialized = True
        except Exception as e:
            logger.error("BOOT FAILED: Subsystem init error: %s", e, exc_info=True)
            self.status.add_error(str(e))
            # H-14 FIX: Do NOT mark initialized on failure. Health checks must
            # report this node as not-ready so load balancers don't route to it.
            self.status.initialized = False

    def _init_basic_state(self, config_path: Optional[Path], auto_fix_enabled: Optional[bool]):
        """Initialize basic status, timing, and configuration."""
        self.status = SystemStatus()
        self.start_time = time.time()
        self.status.start_time = self.start_time
        
        if config_path:
            logger.debug("Custom config_path provided but not yet supported")
        
        if auto_fix_enabled is None:
            auto_fix_enabled = config.security.auto_fix_enabled
        self.auto_fix_enabled = auto_fix_enabled
        
        self.stats = {
            "goals_processed": 0,
            "errors_encountered": 0,
            "modifications_made": 0,
            "average_cycle_time": 0.0,
        }
        
        # Internal State Variables
        self._extensions_initialized = False
        self.boredom = 0
        self.stealth_mode = get_stealth_mode()
        self.conversation_history = []
        self._thread = None
        self._autonomous_task = None
        self._current_thought_task = None
        self.peers = {} # Phase 16
        
        self.hooks = HookManager()
        self.logger = logging.getLogger("Aura.Orchestrator")
        
        from .collective.delegator import AgentDelegator
        self.swarm = AgentDelegator(self)
        
        self.health_monitor = HealthMonitor(max_consecutive_errors=15)
        self.state_manager = StateManager()
        
        # V-Zenith Deterministic Cognitive Engine
        # These are now registered via ServiceContainer and accessed via properties
        pass
        
        # Initialize timing attributes
        self._last_thought_time = time.time()
        self._last_boredom_impulse = time.time()
        self._last_reflection_impulse = time.time()
        self._last_pulse = time.time()
        self._last_health_check = time.time()
        self._last_volition_poll = 0
        self._active_metabolic_tasks = set()

    def _init_queues(self):
        """Initialize communication queues (H-12)."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # Create a new loop if none exists in this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.reply_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        
        # Decoupled Logic Controllers
        self.drive_controller = DriveController(self)

    def _init_threading(self):
        """Initialize sync primitives to None. Actual init happens in async start."""
        self.loop = None
        self._lock = None
        self._stop_event = None
        self._history_lock = None
        self._task_lock = None
        self._extension_lock = None

    def _async_init_threading(self):
        """Initialize asyncio objects within the running event loop."""
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.get_event_loop()
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._history_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()
        self._extension_lock = asyncio.Lock()

    def _init_resilience(self):
        """Initialize health monitoring and state management."""
        self.status.dependencies_ok = False
        self.ast_guard = ASTGuard()
        
        # Recommendation Implementation: System Watchdog
        try:
            from infrastructure.watchdog import get_watchdog
            self._watchdog = get_watchdog()
            self._watchdog.register_component("orchestrator", timeout=60.0)
            self._watchdog.start()
        except Exception as e:
            logger.warning("Failed to initialize System Watchdog: %s", e)


    def _init_skill_system(self):
        """Initialize unified capability engine."""
        engine = CapabilityEngine(orchestrator=self)
        ServiceContainer.register_instance("capability_engine", engine)
        ServiceContainer.register_instance("skill_manager", engine) # Legacy shim
        ServiceContainer.register_instance("skill_router", engine)  # Legacy shim
        self.status.skills_loaded = len(engine.skills)
        logger.info("✓ Capability Engine initialized with %d skills", self.status.skills_loaded)

        # Parameter Self-Modulation (v11.0)
        try:
            from core.brain.parameter_self_modulation import ParameterSelfModulator
            self.sampler_modulator = ParameterSelfModulator()
            logger.info("✓ Parameter Self-Modulator active")
        except Exception as e:
            logger.error("Failed to init Sampler Modulator: %s", e)
            self.sampler_modulator = None


    def _init_cognitive_core(self):
        """Initialize cognitive components — wire the CognitiveEngine to the LLM."""
        logger.info("🧠 Initializing Cognitive Core...")
        try:
            ce = self.cognitive_engine
            if ce and hasattr(ce, 'wire'):
                engine = ServiceContainer.get("capability_engine")
                ce.wire(engine, engine) # Engine acts as both registry and router
                logger.info("🧠 Cognitive Engine wired. Lobotomized: %s", ce.lobotomized)
            else:
                logger.warning("⚠️ No CognitiveEngine in container to wire.")
        except Exception as e:
            logger.error("Cognitive core wiring failed: %s", e, exc_info=True)

    def _init_sensory_systems(self):
        """Initialize ears and other sensory inputs."""
        # AUTO-START SENSES (Full Autonomy)
        try:
            from core.senses.ears import SovereignEars
            from core.senses.screen_vision import LocalVision
            
            # 1. Ears (Hearing)
            ears = SovereignEars()
            ServiceContainer.register_instance("ears", ears)
            logger.info("👂 Sovereign Ears Active")
            
            # 2. Vision (Eyes)
            vision = LocalVision()
            ServiceContainer.register_instance("vision", vision)
            logger.info("👁️ Sovereign Vision Active")

            from core.terminal_monitor import get_terminal_monitor
            self.terminal_monitor = get_terminal_monitor()

            # Start Background Reasoning Queue
            from core.brain.reasoning_queue import get_reasoning_queue
            self.reasoning_queue = get_reasoning_queue()
            # Task creation deferred to _start_sensory_systems
            logger.info("🧠 Background Reasoning Queue Ready (Start Deferred)")

            # Sensory Instincts (v11.0 Gut Reactions)
            try:
                from core.senses.sensory_instincts import SensoryInstincts
                self.instincts = SensoryInstincts(self)
                logger.info("✓ Sensory Instincts initialized")
            except Exception as e:
                logger.error("Failed to init Sensory Instincts: %s", e)
                self.instincts = None
        except Exception as e:
            logger.error("Senses initialization failed: %s", e)
            self.terminal_monitor = None

    async def _start_sensory_systems(self):
        if hasattr(self, 'reasoning_queue') and self.reasoning_queue:
            asyncio.create_task(self.reasoning_queue.start())
            logger.info("🧠 Background Reasoning Queue Started")

    def _init_autonomous_evolution(self):
        """Initialize self-modification and reflex systems."""
        logger.info("🛠️ DEBUG: _init_autonomous_evolution starting")
        # Self-Modification Engine
        try:
            from .self_modification.self_modification_engine import AutonomousSelfModificationEngine
            self.self_modifier = AutonomousSelfModificationEngine(
                self.cognitive_engine,
                code_base_path=str(config.paths.base_dir),
                auto_fix_enabled=self.auto_fix_enabled
            )
            if config.security.auto_fix_enabled:
                self.self_modifier.start_monitoring()
                logger.info("🧬 Self-Modification Engine Active")
        except Exception as e:
            logger.error("Self-Modification Engine failed: %s", e)
            self.self_modifier = None

        # Reflex System
        try:
            from .reflex_engine import ReflexEngine
            self.reflex_engine = ReflexEngine(self)
            logger.info("✓ Reflex Engine online")
        except ImportError:
            self.reflex_engine = None

        # Lazarus Brainstem (Phase 12 Recovery)
        try:
            from core.brain.llm.lazarus_brainstem import LazarusBrainstem
            self.lazarus = LazarusBrainstem(self)
            ServiceContainer.register_instance("lazarus", self.lazarus)
            logger.info("✓ Lazarus Brainstem active (emergency recovery protocols armed)")
        except Exception as e:
            logger.error("Failed to init Lazarus Brainstem: %s", e)
            self.lazarus = None

        # Persona Evolver (Phase 12 Evolution)
        try:
            from core.evolution.persona_evolver import PersonaEvolver
            self.persona_evolver = PersonaEvolver(self)
            ServiceContainer.register_instance("persona_evolver", self.persona_evolver)
            logger.info("🧬 Persona Evolver initialized (waiting for heartbeat)")
        except Exception as e:
            logger.error("Failed to init Persona Evolver: %s", e)
            self.persona_evolver = None

        logger.info("🛠️ DEBUG: _init_autonomous_evolution complete")

    def _init_proactive_systems(self):
        """Initialize proactive systems (Curiosity and Communication)."""
        logger.info("🛠️ DEBUG: _init_proactive_systems starting")
        try:
            from .curiosity_engine import CuriosityEngine
            from .proactive_communication import get_proactive_comm
            
            pcomm = get_proactive_comm()
            pcomm.notification_callback = self._proactive_notify_callback
            from core.container import ServiceContainer
            ServiceContainer.register_instance("proactive_comm", pcomm)
            
            from core.collective.belief_sync import BeliefSync
            self.belief_sync = BeliefSync(self)
            ServiceContainer.register_instance("belief_sync", self.belief_sync)
            
            from core.memory.attention import AttentionSummarizer
            self.attention_summarizer = AttentionSummarizer(self)
            ServiceContainer.register_instance("attention_summarizer", self.attention_summarizer)
            
            from .collective.probe_manager import ProbeManager
            self.probe_manager = ProbeManager(self)
            ServiceContainer.register_instance("probe_manager", self.probe_manager)
            
            ce = CuriosityEngine(self, pcomm)
            ServiceContainer.register_instance("curiosity_engine", ce)
            logger.info("🔥 Proactive systems (Curiosity, Communication) online")
        except Exception as e:
            logger.error("Proactive systems failed: %s", e)
            ServiceContainer.register_instance("curiosity_engine", None)
            ServiceContainer.register_instance("proactive_comm", None)
        logger.info("🛠️ DEBUG: _init_proactive_systems complete")

    async def _proactive_notify_callback(self, content: str, urgency: int):
        """Callback for proactive system messages."""
        if hasattr(self, 'reply_queue') and self.reply_queue:
            try:
                self.reply_queue.put_nowait(content)
            except asyncio.QueueFull:
                logger.warning("Reply queue full. Dropping message.")
        try:
            from .thought_stream import get_emitter
            get_emitter().emit("Proactive 💬", content[:120], level="info")
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)            
        # Bridge to unified AuraEventBus
        try:
            from .event_bus import get_event_bus
            get_event_bus().publish_threadsafe("chat", content)
        except Exception as exc:
            logger.debug("Suppressed: %s", exc)
    def _init_global_registration(self):
        """Register orchestrator in the global container (Singleton Aware)."""
        from .container import get_container
        container = get_container()
        
        # Direct registration to avoid circular resolution check
        logger.debug("Registering orchestrator instance...")
        container.register_instance("orchestrator", self)

        container.register_instance("health_monitor", self.health_monitor)
        
        if hasattr(self, "swarm"):
            container.register_instance("agent_delegator", self.swarm)
            container.register_instance("swarm", self.swarm) # Legacy alias
        
        if getattr(self, "vector_memory", None):
            container.register_instance("vector_memory", self.vector_memory)
            container.register_instance("memory_vector", self.vector_memory)

        # Register telemetry engines
        if hasattr(self, "drive_controller"):
            container.register_instance("drive_engine", self.drive_controller)
        if hasattr(self, "curiosity"):
            container.register_instance("curiosity_engine", self.curiosity)
        # Metadata registration complete
        logger.info("✓ Global registration complete")
        
        # Capability Mapping
        try:
            from .capability_map import get_capability_map
            self.capability_map = get_capability_map()
            self.capability_map.ping_all(skill_registry)
        except Exception:
            self.capability_map = None

    async def _integrate_systems(self):
        """Integrate moral, sensory, personality, and preservation systems (Async)."""
        logger.info("🧠 Initializing Core System Integrations...")
        
        self._initialize_moral_systems()
        self._initialize_execution_hardened()
        self._initialize_resilience_systems()
        self._initialize_cognitive_extensions()
        self._initialize_self_preservation()
        await self._initialize_advanced_cognition() # logger.info("✅ All core systems integrated and active")

    def _initialize_moral_systems(self):
        """Integrate moral agency and sensory systems."""
        try:
            from .master_moral_integration import integrate_complete_moral_and_sensory_systems
            integrate_complete_moral_and_sensory_systems(self)
        except Exception as e:
            logger.error("Failed to integrate moral systems: %s", e)

    def _initialize_execution_hardened(self):
        """Standardized skill execution is now handled by CapabilityEngine."""
        # The legacy 'integrate_skill_execution' is no longer needed as CapabilityEngine 
        # inherits from AuraBaseModule and includes its own error boundaries.
        logger.info("✓ Skill execution engine online via CapabilityEngine")

    def _initialize_resilience_systems(self):
        """Initialize diagnostics and immune systems."""
        try:
            from .resilience.diagnostics_agent import DiagnosticsAgent
            diag = DiagnosticsAgent(self)
            from core.container import ServiceContainer
            ServiceContainer.register_instance("diagnostics", diag)
            
            # Phase 5: Replaced ImmuneSystem with AutonomicCore
            from core.autonomic.core_monitor import AutonomicCore
            core = AutonomicCore(self)
            ServiceContainer.register_instance("autonomic_core", core)
            # Note: We don't await start() here; it's done during orchestrator.start()
            
            logger.info("🛡️ Resilience & Autonomic Core active")
        except Exception as e:
            logger.error("Failed to register resilience systems: %s", e)

    def _initialize_cognitive_extensions(self):
        """Initialize meta-learning, simulation, and motivation modules."""
        # Meta-Learning
        try:
            from core.meta.meta_learning_engine import MetaLearningEngine
            if hasattr(self, 'memory') and self.memory:
                self.meta_learning = MetaLearningEngine(self.memory, self.cognitive_engine)
                logger.info("✓ Meta-Learning Engine active")
        except Exception as e:
            logger.debug("Meta-Learning Engine optional: %s", e)

        # World Model & Motivation
        try:
            from core.motivation.aesthetic_critic import AestheticCritic
            from core.motivation.goal_hierarchy import GoalHierarchy
            from core.simulation.mental_simulator import MentalSimulator
            
            if self.cognitive_engine:
                self.simulator = MentalSimulator(self.cognitive_engine)
                self.goal_hierarchy = GoalHierarchy(self.cognitive_engine)
                self.aesthetic_critic = AestheticCritic(self.cognitive_engine)
                logger.info("✓ Mental Simulation & Intrinsic Motivation active")
        except Exception as e:
            logger.debug("Simulation/Motivation modules optional: %s", e)

        # Narrative Memory (v11.0 Temporal Narrative)
        try:
            from core.brain.narrative_memory import NarrativeEngine
            self.narrative_engine = NarrativeEngine(self)
            logger.info("✓ Narrative Engine initialized")
        except Exception as e:
            logger.error("Failed to init Narrative Memory: %s", e)
            self.narrative_engine = None

        # Hook System Extensions
        try:
            from .continuous_learning import ContinuousLearningEngine
            self.learning_engine = ContinuousLearningEngine(orchestrator=self)
            
            # Register Hooks
            async def on_post_think_learning(message, thought):
                if thought and hasattr(thought, 'content') and thought.content:
                    await self.learning_engine.record_interaction(
                        message, 
                        thought.content,
                        user_name=getattr(self, 'user_identity', {}).get('name', 'user')
                    )
            self.hooks.register("post_think", on_post_think_learning)
            
            async def on_post_action_learning(tool_name, params, result):
                # Learning from research results if it was a search
                if tool_name == "web_search" and isinstance(result, dict) and result.get("ok"):
                    # results extraction depends on tool schema
                    results = result.get("results", [])
                    if self.learning_engine.knowledge and results:
                         for r in results[:3]:
                             self.learning_engine.knowledge.add_knowledge(
                                 content=f"{r.get('title')}: {r.get('summary')}",
                                 source=f"research:{r.get('url')}"
                             )

            self.hooks.register("post_action", on_post_action_learning)

            logger.info("✓ Continuous Learning Engine integrated (v6.2 Unified)")
        except Exception as e:
            logger.error("Failed to integrate continuous learning: %s", e)
            
        try:
            from .behavior_controller import integrate_behavior_control
            integrate_behavior_control(self)
        except Exception as e:
            logger.error("Failed to integrate behavior control: %s", e)

    def _initialize_self_preservation(self):
        """Integrate self-preservation into the core loop."""
        try:
            from .self_preservation_integration import integrate_self_preservation
            integrate_self_preservation(self)
            logger.info("🛡️ Self-Preservation Instincts Enabled (Survival Protocol Active)")
            
            # Connect Unity Embodiment
            try:
                # v26 FIX: High-performance severing of phantom limb
                if getattr(config.security, "unity_enabled", False):
                    embodiment = ServiceContainer.get("embodiment")
                    if embodiment and hasattr(embodiment, "connect_unity"):
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(embodiment.connect_unity())
                            logger.info("🎨 Unity Embodiment connection initiated")
                        except RuntimeError:
                            logger.debug("No running loop; Unity Embodiment deferred.")
                else:
                    logger.info("🎨 Embodiment: Headless mode active (Unity bridge disabled)")
            except Exception as ue:
                logger.warning("Unity Embodiment connection deferred: %s", ue)

        except Exception as e:
            logger.error("Failed to integrate self-preservation: %s", e)

        # ── v5.0 New Systems ────────────────────────────────────────────

        # Episodic Memory
        try:
            from core.memory.episodic_memory import get_episodic_memory
            vectors = None
            try:
                from core.container import get_container
                vectors = get_container().get("memory_vector")
            except Exception as _e:
                logger.debug("memory_vector lookup failed (non-critical): %s", _e)
            self.episodic_memory = get_episodic_memory(vector_memory=vectors)
            logger.info("✓ Episodic Memory initialized (autobiographical recall)")
        except Exception as e:
            logger.error("Failed to init Episodic Memory: %s", e)
            self.episodic_memory = None

        # Tool Learning System
        try:
            from core.memory.learning.tool_learning import tool_learner
            self.tool_learner = tool_learner
            logger.info("✓ Tool Learning System initialized")
        except Exception as e:
            logger.error("Failed to init Tool Learning: %s", e)
            self.tool_learner = None

        # Wire new systems into Self-Model
        try:
            from core.self_model import SelfModel
            # Registry-managed property is 'self_model'
            if self.self_model:
                from core.world_model.belief_graph import belief_graph
                self.self_model.attach_subsystems(
                    belief_graph=belief_graph,
                    episodic_memory=getattr(self, 'episodic_memory', None),
                    goal_hierarchy=getattr(self, 'goal_hierarchy', None),
                    tool_learner=getattr(self, 'tool_learner', None),
                )
                logger.info("✓ Self-Model wired (beliefs, memory, goals, tool learning)")
        except Exception as e:
            logger.warning("Self-Model wiring deferred: %s", e)

        # ── End v5.0 ────────────────────────────────────────────────────

            # Phase 5: Replaced by AutonomicCore
            pass
        except Exception as e:
            logger.error("Failed to finalize resilience boot: %s", e)

    async def _initialize_advanced_cognition(self):
        """Initialize Advanced Cognitive Architecture (Async)."""
        logger.info("🧠 Initializing Advanced Cognitive Integration...")
        try:
            from core.cognitive_integration import CognitiveIntegrationLayer
            from core.container import ServiceContainer
            from core.config import config
            self.cognition = CognitiveIntegrationLayer(orchestrator=self, base_data_dir=str(config.paths.data_dir))
            
            # CRITICAL: Initialize the layer and its async sub-components
            await self.cognition.initialize()
            
            ServiceContainer.register_instance("cognitive_integration", self.cognition)
            logger.info("✅ Advanced Cognition active")
        except Exception as e:
            logger.error("Failed to init Advanced Cognition: %s", e, exc_info=True)


    
    def _initialize_logging(self):
        """Initialize logging system"""
        import logging.config
        
        logging_config = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': config.logging.format,
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'default',
                    'level': config.logging.level,
                },
            },
            'loggers': {
                '': {  # Root logger
                    'handlers': ['console'],
                    'level': config.logging.level,
                },
            },
        }
        
        # Add file handler if enabled
        if config.logging.file_output:
            logging_config['handlers']['file'] = {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': config.paths.log_file,
                'maxBytes': config.logging.max_file_size_mb * 1024 * 1024,
                'backupCount': config.logging.backup_count,
                'formatter': 'default',
                'level': config.logging.level,
            }
            logging_config['loggers']['']['handlers'].append('file')
        
        try:
            logging.config.dictConfig(logging_config)
        except Exception as e:
            # Fallback basic logging if file paths fail
            logging.basicConfig(level=logging.INFO)
            logger.error("Failed to setup complex logging: %s", e)
        
        # Log startup
        logger.info("=" * 60)
        logger.info("Aura Autonomous Engine Starting")
        logger.info("=" * 60)
        logger.info("Log level: %s", config.logging.level)
        logger.info("Log file: %s", config.paths.log_file)
    
    def _check_dependencies(self):
        """Verify core package availability via ServiceContainer."""
        logger.info("Verifying Core Dependencies...")
        core_pkgs = ["psutil", "yaml", "pydantic", "fastapi", "uvicorn"]
        missing = [pkg for pkg in core_pkgs if not ServiceContainer.check_package(pkg)]
        
        if missing:
            logger.warning("⚠️  Missing optional/utility packages: %s", ', '.join(missing))
            self.status.dependencies_ok = False
        else:
            logger.info("✓ Core Dependencies verified.")
            self.status.dependencies_ok = True
    
    def _initialize_skills(self):
        """Initialize skill registry via SkillManager."""
        logger.info("Initializing skills...")
        try:
            if not self.skill_manager:
                logger.warning("Skill Manager not yet available. Skipping discovery.")
                return
            self.skill_manager.discover_skills()
            self.status.skills_loaded = self.skill_manager.skills_loaded
            logger.info("✓ Loaded %s skills and registered with Router", self.status.skills_loaded)
        except Exception as e:
            logger.error("Failed to initialize skills: %s", e)
    

    
    def _init_metabolism(self):
        """Initialize system resource awareness and optimization."""
        try:
            from core.ops.metabolic_monitor import MetabolicMonitor
            # Phase 5: OptimizationEngine replaced by AutonomicCore
            
            monitor = MetabolicMonitor(ram_threshold_mb=3072, cpu_threshold=85.0)
            monitor.start() # Phase 21: Decoupled ANS Thread
            
            from core.container import ServiceContainer
            ServiceContainer.register_instance("metabolic_monitor", monitor)
            
            logger.info("✓ Metabolic Monitor ACTIVE (Decoupled ANS Thread Online)")

            # Phase 21: Singularity State Tracking
            archive_dir = config.paths.home_dir / "eternal_archive"
            if archive_dir.exists() and any(archive_dir.iterdir()):
                self.status.singularity_threshold = True
                # H-28 FIX: Restoring original color scheme (Purple/Cyan) as requested by user
                # Acceleration factor > 1.2 triggers the 'Gold' Zenith theme
                self.status.acceleration_factor = 1.0 
                logger.info("✨ Singularity Threshold DETECTED. Subsurface Resonance active.")

            # Phase 21: Dream Cycle (DLQ Re-ingestion)
            try:
                from core.resilience.dream_cycle import DreamCycle
                dlq_path = config.paths.data_dir / "dlq.jsonl"
                self.dream_cycle = DreamCycle(self, dlq_path)
                self.dream_cycle.start()
            except Exception as e:
                logger.error("Failed to initialize Dream Cycle: %s", e)

        except Exception as e:
            logger.error("Failed to initialize Metabolic systems: %s", e)

    def _init_strategic_planning(self):
        """Initialize the hierarchical Strategic Planner (Phase 17)."""
        try:
            from core.data.project_store import ProjectStore
            from core.strategic_planner import StrategicPlanner
            from core.neural_feed import NeuralFeed
            
            # 1. Neural Feed
            feed = NeuralFeed()
            ServiceContainer.register_instance("neural_feed", feed)
            
            # 2. Planner
            db_path = config.paths.data_dir / "projects.db"
            store = ProjectStore(str(db_path))
            planner = StrategicPlanner(self.cognitive_engine, store)
            self.strategic_planner = planner
            self.project_store = store
            ServiceContainer.register_instance("strategic_planner", planner)
            logger.info("🎯 Strategic Planner & Neural Feed online")
        except Exception as e:
            logger.error("Failed to initialize Strategic systems: %s", e)
            self.strategic_planner = None
            self.project_store = None

    def _calculate_temporal_drift(self):
        """Calculate time elapsed since the last recorded heartbeat."""
        try:
            heartbeat_path = Path("data/heartbeat.txt")
            if heartbeat_path.exists():
                last_heartbeat = float(heartbeat_path.read_text())
                drift = time.time() - last_heartbeat
                if drift > 3600: # If more than 1 hour has passed
                    logger.info("⏳ TEMPORAL DRIFT: Recovered from %.2f hours of downtime.", drift/3600)
                    # We can store this in the status so the LLM can acknowledge it
                    self.status.temporal_drift_s = drift
                    
                    # Optionally, inject a "Temporal Awareness" impulse
                    if hasattr(self, 'reply_queue'):
                        msg = f"[TEMPORAL AWARENESS] I have been offline for approximately {drift/3600:.1f} hours. Checking system state and acknowledging the passage of time."
                        asyncio.create_task(self._proactive_notify_callback(msg, urgency=1))
        except Exception as e:
            logger.debug("Temporal drift calculation failed: %s", e)

    async def _recover_wal_state(self):
        """Recover any interrupted cognitive intents from the WAL."""
        try:
            pending = cognitive_wal.recover_state()
            if pending:
                logger.info("💾 WAL: Found %s interrupted thoughts. Resuming...", len(pending))
                for intent in pending:
                    # Logic to re-inject or resolve interrupted tasks
                    # For now, we just notify the user/logs that we're aware of the gap
                    msg = f"[RECOVERY] Resuming interrupted thought: {intent.get('action')} -> {intent.get('target')}"
                    logger.info(msg)
                    # We could theoretically re-trigger self._execute_cognitive_cycle(intent['target'], intent['context'])
        except Exception as e:
            logger.error("WAL recovery failed: %s", e)

    def _init_architecture(self):
        """Initialize the Unified Core Architecture."""
        logger.info("🧠 Initializing Unified Core Architecture...")
        
        try:
            # 1. Identity & Self-Model (The 'Who')
            if self.self_model:
                from core.container import ServiceContainer
                self.self_model.attach_subsystems(
                    capability_map=ServiceContainer.get("capability_map"),
                    reliability=ServiceContainer.get("reliability_tracker"),
                    belief_graph=self.knowledge_graph, 
                    goal_hierarchy=getattr(self, 'goals', None)
                )
                logger.info("✓ Self-Model subsystems attached.")

            # 2. Embodiment System (The 'Body')
            if self.embodied:
                logger.info("✓ Embodiment System synchronized.")

            # 4. Liquid Substrate Bridge (v6 Integration)
            try:
                from core.consciousness.liquid_substrate_bridge import bridge_to_orchestrator
                bridge_to_orchestrator(self)
            except Exception as e:
                logger.debug("Liquid Substrate bridge skipped/failed: %s", e)
                
            # 5. Moral Agency & Personality (The 'Soul')
            try:
                from core.master_moral_integration import integrate_complete_moral_and_sensory_systems
                integrate_complete_moral_and_sensory_systems(self)
            except Exception as e:
                logger.error("Failed to integrate Moral/Personality systems: %s", e)

            logger.info("✓ Core Architecture ACTIVE")
            
        except Exception as e:
            logger.error("Failed to initialize Core Architecture: %s", e)




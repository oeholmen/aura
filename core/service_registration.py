import logging
from typing import Any

from .container import ServiceContainer, ServiceLifetime, get_container

logger = logging.getLogger(__name__)


# Minimal trace debug


def register_all_services():
    """Register all core services with the DI container.
    """
    container = get_container()
    from .config import config

    logger.info("Registering system services...")

    # 0. Event Bus (Unified messaging backbone)
    def create_event_bus():
        from .event_bus import get_event_bus
        return get_event_bus()
    container.register('event_bus', create_event_bus, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 0.1 Input Bus (Legacy - keeping for compatibility)
    def create_input_bus():
        from .events import InputBus
        return InputBus()
    container.register('input_bus', create_input_bus, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 0.1 Liquid State
    def create_liquid_state():
        from .evolution.liquid_state import LiquidState
        return LiquidState()
    container.register('liquid_state', create_liquid_state, lifetime=ServiceLifetime.SINGLETON, required=True)


    # 1. Cognitive Engine
    def create_cognitive_engine():
        logger.info("Factory: Creating cognitive_engine...")
        try:
            from .brain.cognitive_engine import CognitiveEngine
            cognitive_engine = CognitiveEngine()
            logger.info("Factory SUCCESS: cognitive_engine instance created: %s", type(cognitive_engine))
            return cognitive_engine
        except Exception:
            logger.exception("Factory CRITICAL: Failed to create cognitive_engine")
            return None
    container.register('cognitive_engine', create_cognitive_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 1.1 Cognitive Manager (Lifecyle & Autonomous Control)
    def create_cognitive_manager():
        logger.info("Factory: Creating cognitive_manager...")
        try:
            from .brain.cognitive_manager import CognitiveManager
            mgr = CognitiveManager()
            logger.info("Factory SUCCESS: cognitive_manager instance created.")
            return mgr
        except Exception:
            logger.exception("Factory CRITICAL: Failed to create cognitive_manager")
            return None
    container.register('cognitive_manager', create_cognitive_manager, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 1.2 LLM Router (Multi-tier Failover)
    def create_llm_router():
        try:
            from .brain.llm.llm_router import IntelligentLLMRouter
            return IntelligentLLMRouter()
        except Exception as e:
            logger.error("Failed to create llm_router: %s", e)
            return None
    container.register('llm_router', create_llm_router, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 1.3 Local LLM (Direct Bridge)
    def create_local_llm():
        try:
            from .brain.local_llm import LocalBrain
            return LocalBrain()
        except Exception as e:
            logger.error("Failed to create local_llm: %s", e)
            return None
    container.register('local_llm', create_local_llm, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 1.4 Ollama Client (Low-level)
    def create_ollama_client():
        try:
            from .brain.llm.ollama_client import RobustOllamaClient
            return RobustOllamaClient()
        except Exception as e:
            logger.error("Failed to create ollama client: %s", e)
            return None
    container.register('ollama', create_ollama_client, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 4. Capability Engine (Consolidated Skill System)
    def create_capability_engine():
        from .capability_engine import CapabilityEngine
        orch = container.get("orchestrator", None)
        return CapabilityEngine(orchestrator=orch)
    container.register('capability_engine', create_capability_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 4.2 Intent Router (V-Zenith)
    def create_intent_router():
        from .cognitive.router import IntentRouter
        return IntentRouter()
    container.register('intent_router', create_intent_router, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 4.3 State Machine (V-Zenith Handlers)
    def create_state_machine():
        from .cognitive.state_machine import StateMachine
        orch = container.get("orchestrator")
        return StateMachine(orch)
    container.register('state_machine', create_state_machine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 4.1 Agent Delegator (Swarm 2.0)
    def create_swarm():
        from .collective.delegator import AgentDelegator
        orch = container.get("orchestrator")
        return AgentDelegator(orch)
    container.register('agent_delegator', create_swarm, lifetime=ServiceLifetime.SINGLETON, required=True)

    # Shims for legacy dependency injection
    container.register('skill_registry', lambda: container.get("capability_engine"), lifetime=ServiceLifetime.SINGLETON, required=False)
    container.register('skill_router', lambda: container.get("capability_engine"), lifetime=ServiceLifetime.SINGLETON, required=False)
    container.register('skill_manager', lambda: container.get("capability_engine"), lifetime=ServiceLifetime.SINGLETON, required=False)

    # 7. Memory (Base Store)
    def create_memory():
        from .config import config
        from .memory.sqlite_storage import SQLiteMemory
        db_path = config.paths.data_dir / "memory" / "atomic_knowledge.db"
        return SQLiteMemory(storage_file=str(db_path))
    container.register('memory', create_memory, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 7.1 Knowledge Ledger (Micro-trace)
    def create_ledger():
        from .memory.knowledge_ledger import KnowledgeLedger
        return KnowledgeLedger()
    container.register('knowledge_ledger', create_ledger, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 8. Memory Manager
    def create_memory_manager():
        from .managers.memory_manager import MemoryManager
        memory = container.get("memory")
        vector = container.get("memory_vector", None)  # May be None if not yet registered
        return MemoryManager(sqlite_memory=memory, vector_memory=vector)
    container.register('memory_manager', create_memory_manager, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 9.0 Health Monitor
    def create_health_monitor():
        from .ops.health_monitor import HealthMonitor
        return HealthMonitor()
    container.register('health_monitor', create_health_monitor, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 9.1 Metabolic Monitor (v6.0 Resource Tracking)
    def create_metabolic_monitor():
        from .ops.metabolic_monitor import MetabolicMonitor
        return MetabolicMonitor()
    container.register('metabolic_monitor', create_metabolic_monitor, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 9.2 Autonomic Core (V-Zenith Unified Heartbeat)
    def create_autonomic_core():
        from .autonomic.core_monitor import AutonomicCore
        orch = container.get("orchestrator")
        return AutonomicCore(orch)
    container.register('autonomic_core', create_autonomic_core, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 10. Degradation Manager
    def create_degradation_manager():
        try:
            from .degradation import degradation_manager
            return degradation_manager
        except ImportError as e:
            logger.warning("Optional Service Check: degradation_manager not found (%s)", e)
            return None
    container.register('degradation_manager', create_degradation_manager, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 11. Thought Stream Emitter
    def create_emitter():
        from .thought_stream import get_emitter
        return get_emitter()
    container.register('emitter', create_emitter, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 12. Planner
    def create_planner():
        from .planner import Planner
        brain = container.get("cognitive_engine")
        return Planner(brain)
    container.register('planner', create_planner, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 13. Orchestrator
    def create_orchestrator():
        from .orchestrator import RobustOrchestrator
        return RobustOrchestrator()
    container.register('orchestrator', create_orchestrator, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 13.1 Identity System (Consolidated v6.0)
    def create_identity():
        from .identity import get_identity_system
        orch = container.get("orchestrator")
        return get_identity_system(orch)
    container.register('identity', create_identity, lifetime=ServiceLifetime.SINGLETON, required=True)
    # Legacy alias
    container.register('identity_kernel', create_identity, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 14. Web Search
    def create_web_search():
        try:
            from skills.web_search import EnhancedWebSearchSkill
            return EnhancedWebSearchSkill()
        except ImportError as e:
            logger.warning("Optional Service Check: web_search not found (%s)", e)
            return None
    container.register('web_search', create_web_search, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 15. Code Sandbox
    def create_sandbox():
        try:
            from skills.sandbox import SecureSandbox
            return SecureSandbox()
        except ImportError as e:
            logger.warning("Optional Service Check: sandbox not found (%s)", e)
            return None
    container.register('sandbox', create_sandbox, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 16. Memory Pruner
    def create_pruner():
        try:
            from .memory.context_pruner import ContextPruner
            return ContextPruner()
        except ImportError as e:
            logger.warning("Optional Service Check: memory_pruner not found (%s)", e)
            return None
    container.register('memory_pruner', create_pruner, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 17. Personality Engine
    def create_personality():
        try:
            from .brain.personality_engine import PersonalityEngine
            return PersonalityEngine()
        except ImportError as e:
            logger.warning("Optional Service Check: personality_engine not found (%s)", e)
            return None
    container.register('personality_engine', create_personality, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 17.1 Capability Map
    def create_capability_map():
        from .capability_map import get_capability_map
        return get_capability_map()
    container.register('capability_map', create_capability_map, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 17.2 Reliability Tracker
    def create_reliability():
        from .reliability_tracker import reliability_tracker
        return reliability_tracker
    container.register('reliability_tracker', create_reliability, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 18. Soul
    def create_soul():
        try:
            from .soul import Soul
            orch = container.get("orchestrator")
            return Soul(orch)
        except (ImportError, Exception) as e:
            logger.error("Failed to create Soul: %s", e)
            return None
    container.register('soul', create_soul, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 19. Resilience Engine (Consolidated)
    def create_resilience():
        try:
            from .resilience.resilience import ResilienceEngine
            return ResilienceEngine()
        except ImportError as e:
            logger.warning("Optional Service Check: resilience not found (%s)", e)
            return None
    container.register('resilience', create_resilience, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 21. Meta Cognition
    def create_meta_cognition():
        from .consciousness.metacognition import MetaCognitionEngine
        brain = container.get("cognitive_engine")
        return MetaCognitionEngine(brain)
    container.register('metacognition', create_meta_cognition, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 22. Stealth Mode (v3.3+)
    def create_stealth():
        try:
            from .privacy_stealth import StealthMode
            return StealthMode()
        except ImportError as e:
            logger.warning("Optional Service Check: stealth_mode not found (%s)", e)
            return None
    container.register('stealth_mode', create_stealth, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 23. Knowledge Graph (v3.5)
    def create_knowledge_graph():
        try:
            from .config import config
            from .memory.knowledge_graph import PersistentKnowledgeGraph
            kg_path = config.paths.data_dir / "knowledge_graph"
            return PersistentKnowledgeGraph(str(kg_path))
        except (ImportError, Exception) as e:
            logger.warning("Optional Service Check: knowledge_graph not found (%s)", e)
            return None
    container.register('knowledge_graph', create_knowledge_graph, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 24. Memory Vector Store (v5.0) — ChromaDB-backed with Sovereign JSON Fallback
    def create_vector_memory():
        try:
            from .memory.vector_memory import VectorMemory
            # VectorMemory now handles its own fallback and dependency management robustly
            return VectorMemory()
        except (ImportError, Exception) as e:
            logger.error("Failed to initialize VectorMemory: %s", e)
            return None
    container.register('memory_vector', create_vector_memory, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 25. Theory of Mind
    def create_tom():
        try:
            from core.consciousness.theory_of_mind import TheoryOfMindEngine
            brain = container.get("cognitive_engine")
            return TheoryOfMindEngine(brain)
        except ImportError as e:
            logger.warning("Optional Service Check: theory_of_mind not found (%s)", e)
            return None
    container.register('theory_of_mind', create_tom, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 26. Conversation Engine (v5.5)
    def create_conv_engine():
        try:
            from .conversation.engine import ConversationEngine
            brain = container.get("cognitive_engine")
            memory = container.get("memory_manager")
            return ConversationEngine(brain, memory)
        except ImportError as e:
            logger.error("CRITICAL: Failed to create conversation_engine: %s", e)
            return None
    container.register('conversation_engine', create_conv_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 27. Voice Engine (v5.6 Consolidated)
    def create_voice_engine():
        try:
            from .senses.voice_engine import SovereignVoiceEngine
            return SovereignVoiceEngine()
        except ImportError as e:
            logger.warning("Optional Service Check: voice_engine not found (%s)", e)
            return None
    container.register('voice_engine', create_voice_engine, lifetime=ServiceLifetime.SINGLETON, required=False)

    def create_ears():
        try:
            from .senses.ears import SovereignEars
            return SovereignEars()
        except ImportError as e:
            logger.warning("Optional Service Check: ears not found (%s)", e)
            return None
    container.register('ears', create_ears, lifetime=ServiceLifetime.SINGLETON, required=False)
    
    # 28.1 Strategic Planning & Projects (Phase 20)
    def create_project_store():
        from .config import config
        from .data.project_store import ProjectStore
        db_path = config.paths.data_dir / "projects.db"
        return ProjectStore(str(db_path))
    container.register('project_store', create_project_store, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_strategic_planner():
        from .strategic_planner import StrategicPlanner
        brain = container.get("cognitive_engine")
        store = container.get("project_store")
        return StrategicPlanner(brain, store)
    container.register('strategic_planner', create_strategic_planner, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_episodic_memory():
        from .memory.episodic_memory import get_episodic_memory
        vectors = container.get("memory_vector", None)
        return get_episodic_memory(vector_memory=vectors)
    container.register('episodic_memory', create_episodic_memory, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_semantic_memory():
        from .brain.semantic_memory import SemanticMemory
        from .config import config
        sm = SemanticMemory(memory_dir=str(config.paths.memory_dir))
        return sm
    container.register('semantic_memory', create_semantic_memory, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_memory_facade():
        from .memory.memory_facade import MemoryFacade
        episodic = container.get("episodic_memory")
        semantic = container.get("semantic_memory")
        vector = container.get("memory_vector")
        ledger = container.get("knowledge_ledger", None)
        graph = container.get("belief_graph")
        return MemoryFacade(
            episodic=episodic,
            semantic=semantic,
            vector=vector,
            ledger=ledger,
            graph=graph
        )
    container.register('memory_facade', create_memory_facade, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 29. Vision Engine (v5.6)
    def create_vision():
        try:
            from .senses.screen_vision import LocalVision
            return LocalVision()
        except ImportError as e:
            logger.warning("Optional Service Check: vision_engine not found (%s)", e)
            return None
    container.register('vision_engine', create_vision, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 29.1 Pulse Manager (Proactive Awareness)
    def create_pulse_manager():
        try:
            from .senses.pulse_manager import PulseManager
            orch = container.get("orchestrator")
            return PulseManager(orchestrator=orch)
        except ImportError as e:
            logger.warning("Optional Service Check: pulse_manager not found (%s)", e)
            return None
    container.register('pulse_manager', create_pulse_manager, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 29.2 Optimization and Singularities handled by AutonomicCore

    # 29.3 Singularity Monitor (Phase 20)
    def create_singularity_monitor():
        from .ops.singularity_monitor import SingularityMonitor
        orch = container.get("orchestrator")
        return SingularityMonitor(orch)
    container.register('singularity_monitor', create_singularity_monitor, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 30. Core Architecture Upgrade (v6.2)
    
    # 30.1 Global Workspace (Attention)
    def create_global_workspace():
        from .global_workspace import GlobalWorkspace
        return GlobalWorkspace()
    container.register('global_workspace', create_global_workspace, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.2 Self Model (Unified v6.0)
    def create_self_model():
        import asyncio

        from .self_model import SelfModel
        # Since this is synchronous factory, we create or load (handled by orchestrator usually)
        try:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # If we are in the loop thread, we cannot block.
                    # Usually the orchestrator will load this properly during start()
                    logger.debug("SelfModel: loop is running, returning default (should be loaded by orchestrator later)")
                    return SelfModel(id="default")
            except RuntimeError:
                # No running loop, safe to run
                return asyncio.run(SelfModel.load())
            return SelfModel(id="default")
        except Exception as e:
            logger.error("Failed to load SelfModel: %s", e)
            return SelfModel(id="default")
    container.register('self_model', create_self_model, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.3 Drive Engine (Resource Budgets)
    def create_drive_engine():
        from .drive_engine import DriveEngine
        return DriveEngine()
    container.register('drive_engine', create_drive_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.4 Affect Engine (Unified Damasio V2)
    def create_affect_engine():
        from .affect.damasio_v2 import AffectEngineV2
        return AffectEngineV2()
    container.register('affect_engine', create_affect_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.5 Embodiment System (Unified v6.0)
    def create_embodiment():
        from .embodiment import get_embodiment_system
        return get_embodiment_system()
    container.register('embodiment', create_embodiment, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_soma():
        from .embodiment.soma import SystemSoma
        return SystemSoma()
    container.register('soma', create_soma, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.6 Self-Preservation Integration
    def create_self_preservation():
        try:
            from .self_preservation_integration import SelfPreservationIntegration
            orch = container.get("orchestrator")
            return SelfPreservationIntegration(orch)
        except ImportError as e:
            logger.warning("Optional Service Check: self_preservation not found (%s)", e)
            return None
    container.register('self_preservation', create_self_preservation, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 30.6 Survival managed by AutonomicCore

    def create_homeostasis():
        from .consciousness.homeostasis import HomeostasisEngine
        return HomeostasisEngine()
    container.register('homeostasis', create_homeostasis, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_alignment():
        from .security.conscience import AlignmentEngine
        return AlignmentEngine()
    container.register('alignment_engine', create_alignment, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_mind_model():
        from .consciousness.mind_model import MindModel
        return MindModel()
    container.register('mind_model', create_mind_model, lifetime=ServiceLifetime.SINGLETON, required=True)

    def create_social_memory():
        from .memory.social_memory import SocialMemory
        return SocialMemory()
    container.register('social_memory', create_social_memory, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 31. Liquid Neural Network (LNN)
    def create_lnn():
        try:
            from .evolution.liquid_time_engine import ContinuousState
            return ContinuousState()
        except ImportError as e:
            logger.warning("Optional Service Check: lnn not found (%s)", e)
            return None
    container.register('lnn', create_lnn, lifetime=ServiceLifetime.SINGLETON, required=False)

    # 31.5 Affect Engine (Phase 9 Sentient Unity) - MOVED TO 30.4
    # Duplicate removed to prevent overwriting AffectEngineV2

    # 32. Archive Engine (Phase 9 Metabolic Compression)
    def create_archive_engine():
        from .systems.archiver import ArchiveEngine
        return ArchiveEngine()
    container.register('archive_engine', create_archive_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 32.5 Dead Letter Queue (Phase 7 Resilience)
    def create_dlq():
        from .resilience.dlq_service import DeadLetterQueue
        return DeadLetterQueue()
    container.register('dead_letter_queue', create_dlq, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 33. Resilience and Immune System managed by AutonomicCore

    # 33. Belief Graph (World Model)
    def create_belief_graph():
        try:
            from .world_model.belief_graph import get_belief_graph
            return get_belief_graph()
        except Exception as e:
            logger.warning("Failed to load belief_graph: %s", e)
            return None
    container.register('belief_graph', create_belief_graph, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 34. Central Nervous System (CNS)
    def create_cns():
        try:
            from .neuroweb.cns import CentralNervousSystem
            brain = container.get("cognitive_engine")
            memory = container.get("memory_manager")
            registry = container.get("capability_engine")
            return CentralNervousSystem(memory_system=memory, brain=brain, registry=registry)
        except ImportError as e:
            logger.warning("Optional Service Check: cns not found (%s)", e)
            return None
        except Exception as e:
             logger.error("Failed to create CNS: %s", e)
             return None
    container.register('central_nervous_system', create_cns, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 36. Permission Guard (Hardware Integrity)
    def create_permission_guard():
        from .security.permission_guard import PermissionGuard
        return PermissionGuard()
    container.register('permission_guard', create_permission_guard, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 37. Scratchpad Engine (System 2 Thinking)
    def create_scratchpad():
        from .brain.scratchpad import ScratchpadEngine
        return ScratchpadEngine()
    container.register('scratchpad_engine', create_scratchpad, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 38. Hephaestus Engine (Autogenesis)
    def create_hephaestus():
        from .skill_management.hephaestus import HephaestusEngine
        return HephaestusEngine()
    container.register('hephaestus_engine', create_hephaestus, lifetime=ServiceLifetime.SINGLETON, required=True)

    # 35. Learning Engine (Consolidated v6.2)
    def create_learning_engine():
        from .continuous_learning import ContinuousLearningEngine
        orch = container.get("orchestrator", None)
        return ContinuousLearningEngine(orchestrator=orch)
    container.register('learning_engine', create_learning_engine, lifetime=ServiceLifetime.SINGLETON, required=True)

    # --- Final Validation ---
    logger.info("Validating service container...")
    success, errors = container.validate()
    if not success:
        logger.critical("SERVICE REGISTRATION FAILED")
        for error in errors:
            logger.critical("  FAILED: %s", error)

    logger.info("All services registered and validated")
    return container

def inject_services_into_context(context: dict) -> dict:
    """Inject all services into a context dictionary."""
    container = get_container()
    for name, descriptor in container._services.items():
        if descriptor.lifetime == ServiceLifetime.SINGLETON and descriptor.instance:
            context[name] = descriptor.instance
    return context


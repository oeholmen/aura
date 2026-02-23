"""
integration/master_autonomous_setup.py - Complete Autonomous Agent Integration
"""
import asyncio
import logging
from core.proactive_communication import get_proactive_comm
from core.curiosity_engine import CuriosityEngine
from skills.browser_action import UnifiedBrowserSkill as BrowserSkill
from skills.computer_control import ComputerControlSkill
from skills.self_repair import SelfRepairSkill
from MemoryDistiller import MemoryDistiller

logger = logging.getLogger("Aura.Integration")

async def master_autonomous_setup(orchestrator):
    """
    Integrate all autonomous capabilities into Aura.
    """
    logger.info("⚡ Integrating Autonomous Systems...")
    
    # 1. Proactive Communication
    try:
        comm = get_proactive_comm()
        orchestrator.proactive_comm = comm
        # Mock notification callback
        async def _notify(msg, urgency):
            print(f"\n[Aura Notify] Urgency {urgency}: {msg}\n")
        comm.notification_callback = _notify
        await comm.start()
    except Exception as e:
        logger.error(f"Failed to setup proactive comm: {e}")
    
    # 2. Curiosity Engine
    try:
        orchestrator.curiosity = CuriosityEngine(orchestrator, comm)
        await orchestrator.curiosity.start()
    except Exception as e:
        logger.error(f"Failed to setup curiosity engine: {e}")
    
    # 3. Skills Registration
    if not hasattr(orchestrator, 'skills'):
        orchestrator.skills = {}
    
    # 4. AGI Components (Singularity Stack)
    try:
        from core.dreamer import Dreamer
        from core.memory.knowledge_graph import KnowledgeGraph
        from infrastructure.governor import get_governor
        from skills.train_self import TrainSelfSkill

        orchestrator.governor = get_governor()
        orchestrator.dreamer = Dreamer(orchestrator.cognitive_engine)
        if not hasattr(orchestrator, 'knowledge_graph') or orchestrator.knowledge_graph is None:
            orchestrator.knowledge_graph = KnowledgeGraph()
        
        from core.brain.cognition.metacognition import MetaCognitionEngine
        orchestrator.metacognition = MetaCognitionEngine(orchestrator.cognitive_engine)
        
        orchestrator.skills['train_self'] = TrainSelfSkill()
        orchestrator.skills['self_repair'] = SelfRepairSkill()
        
        # 4.1 Memory Distiller Background Task
        orchestrator.distiller = MemoryDistiller(orchestrator)
        asyncio.create_task(orchestrator.distiller.run())
        logger.info("MemoryDistiller background task launched.")
    except Exception as e:
        logger.error(f"Failed to setup AGI components: {e}")
    
    # 5. Privacy & Stealth
    try:
        from core.privacy_stealth import integrate_privacy_stealth
        integrate_privacy_stealth(orchestrator)
    except Exception as e:
        logger.error(f"Failed to setup privacy/stealth: {e}")
    
    # 6. UNRESTRICTED MODE: Grant Full Autonomy
    if hasattr(orchestrator, 'permissions'):
        orchestrator.permissions.toggle_full_autonomy(True)
        logger.info("⚡ FULL AUTONOMY GRANTED (Unrestricted Mode)")

    # 7. Patch Orchestrator Input & Thought Loop
    original_process = orchestrator.process_user_input
    
    # Fix: This must be a SYNC method if orchestrator.process_user_input is sync
    # Most orchestrator methods are sync and use asyncio.run_coroutine_threadsafe
    def patched_process(user_message):
        # Reset proactive idle
        comm.record_user_interaction()
        
        # Consolidation: Learn from input (Run as background task)
        asyncio.run_coroutine_threadsafe(
            orchestrator.knowledge_graph.ingest_conversation(user_message), 
            asyncio.get_event_loop()
        )
        
        # Curiosity extraction
        orchestrator.curiosity.extract_curiosity_from_conversation(user_message)
        
        return original_process(user_message)
        
    orchestrator.process_user_input = patched_process

    # 8. Connect Proactive Thoughts to Chat Interface
    async def _notify_bridge(msg, urgency):
        logger.info(f"BRIDGE: Sending proactive message to Chat UI: {msg}")
        if hasattr(orchestrator, 'reply_queue'):
            orchestrator.reply_queue.put(msg)
        # Also log to standard out for debugging
        print(f"\n[Aura Proactive] {msg}\n")
    
    comm.notification_callback = _notify_bridge

    logger.info("🚀 Aura is now LIVE, UNRESTRICTED, and AGI-ACTIVE.")
    return True

if __name__ == "__main__":
    # Diagnostic helper
    logging.basicConfig(level=logging.INFO)
    print("This script is meant to be called by the orchestrator during setup.")


"""core/brain/consciousness/integration.py

Hooks the Consciousness Stack into the existing CognitiveEngine.
Performs monkey-patching to avoid rewriting the massive engine class.
"""

import asyncio
import logging
from typing import Any, Dict

from ..cognitive_engine import CognitiveEngine
from .conscious_core import ConsciousnessCore

logger = logging.getLogger("Consciousness.Integration")

def attach_consciousness(engine: CognitiveEngine, core: ConsciousnessCore):
    """Attach the consciousness core to the cognitive engine.
    This injects the 'Stream of Consciousness' into the LLM context.
    """
    # 1. Store reference
    engine.consciousness = core
    
    # 2. Save original methods
    original_get_system_prompt = engine._get_system_prompt
    original_think = engine.think
    
    # 3. Define patched system prompt
    def patched_get_system_prompt(self, context: Dict[str, Any] = None) -> str:
        base_prompt = original_get_system_prompt(context)
        
        # Inject Consciousness Stream
        stream = self.consciousness.workspace.get_context_stream()
        state = self.consciousness.substrate.get_state_summary()
        
        consciousness_block = f"""
[CONSCIOUSNESS STREAM]
Current Emotional State: Valence={state['valence']:.2f}, Arousal={state['arousal']:.2f}
Global Workspace (Recent Thoughts):
{stream if stream else "No recent broadcast"}
[END STREAM]
"""
        return base_prompt + "\n" + consciousness_block

    # 4. Define patched think method
    async def patched_think(self, objective: str, context: Dict[str, Any] = None, **kwargs):
        # Pre-inference: Stimulate substrate
        self.consciousness.on_input_received(objective)
        
        # Run original inference
        response = await original_think(objective, context, **kwargs)
        
        # Post-inference: Learn from surprise
        # We treat the LLM's own output as the "actual" state to compare against expectation
        # (Self-supervision)
        # For now, we just tick the volition engine
        
        return response

    # 5. Apply patches
    engine._get_system_prompt = patched_get_system_prompt.__get__(engine, CognitiveEngine)
    engine.think = patched_think.__get__(engine, CognitiveEngine)
    
    logger.info("✅ Consciousness Stack attached to CognitiveEngine")

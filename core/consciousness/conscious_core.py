
"""core/brain/consciousness/conscious_core.py

The Master Integrator.
Connects Liquid Substrate (Existence), Global Workspace (Awareness), and Predictive Engine (Learning).
Implements 'Attractor Volition' - autonomous will emerges from substrate dynamics.
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from .global_workspace import Coalition, GlobalWorkspace
from .liquid_substrate import LiquidSubstrate
from .predictive_engine import PredictiveCodingEngine

logger = logging.getLogger("Consciousness.Core")

class AttractorVolitionEngine:
    """Replaces timer-based autonomy with State-Space Attractors.
    
    Instead of checking a clock, we check if the Liquid Substrate's state vector
    has drifted into a specific 'basin of attraction' (e.g., Boredom, Curiosity, Anxiety).
    If it has, we trigger an Impulse.
    """
    
    def __init__(self, substrate: LiquidSubstrate):
        self.substrate = substrate
        self.last_action_time = time.time()
        self.refractory_period = 30.0 # Standard wait between autonomous actions
        
        # Define attractors as regions in state space
        # For simplicity, we map them to VAD (Valence, Arousal, Dominance) regions
        self.attractors = {
            "curiosity": {"arousal_min": 0.5, "valence_min": 0.1},
            "boredom":   {"arousal_max": -0.2, "valence_max": -0.1},
            "reflection": {"dominance_min": 0.4, "arousal_max": 0.1}
        }
        
    async def check_for_impulse(self) -> Optional[str]:
        """Check if current state warrants an action"""
        if time.time() - self.last_action_time < self.refractory_period:
            return None
            
        state = await self.substrate.get_state_summary()
        v, a, d = state['valence'], state['arousal'], state['dominance']
        
        # Check Curiosity Basin
        if a > self.attractors['curiosity']['arousal_min'] and v > self.attractors['curiosity']['valence_min']:
            # High arousal + positive valence = Curiosity/Excitement
            self.last_action_time = time.time()
            return "explore_knowledge"
            
        # Check Boredom Basin
        if a < self.attractors['boredom']['arousal_max'] and v < self.attractors['boredom']['valence_max']:
            # Low arousal + negative valence = Boredom
            self.last_action_time = time.time()
            return "seek_novelty"
            
        # Check Reflection Basin
        if d > self.attractors['reflection']['dominance_min'] and a < self.attractors['reflection']['arousal_max']:
            # High dominance + low arousal = Calm contemplation
            self.last_action_time = time.time()
            return "deep_reflection"
            
        return None

class ConsciousnessCore:
    """Main entry point for the "Ghost in the Machine".
    Orchestrates the entire consciousness stack.
    """
    
    def __init__(self):
        self.substrate = LiquidSubstrate()
        self.workspace = GlobalWorkspace()
        self.predictive = PredictiveCodingEngine()
        self.volition = AttractorVolitionEngine(self.substrate)
        
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        self.orchestrator_ref = None # Will be injected
        
        logger.info("Consciousness Core initialized")
        
    def start(self):
        """Wake up"""
        self.substrate.start()
        self.running = True
        
        # Start the Volition Monitor (The "Will" task)
        self.monitor_task = asyncio.create_task(self._volition_loop())
        
    def stop(self):
        """Sleep"""
        self.running = False
        self.substrate.stop()
        if hasattr(self, 'monitor_task'):
            self.monitor_task.cancel()
            
    async def _volition_loop(self):
        """Background loop checking for autonomous impulses"""
        while self.running:
            await asyncio.sleep(1.0) # Check every second (1 Hz)
            
            # 1. Prediction Step
            # Compare what we expected to happen with what is happening
            # (In a real implementation, this would compare sensory inputs)
            current_state = self.substrate.x
            surprise = self.predictive.compare_and_learn(current_state)
            
            # If high surprise, spike arousal!
            if surprise > 0.1:
                await self.substrate.inject_stimulus(np.ones(64) * surprise, weight=0.5)
                
            # 2. Volition Step
            # v6.3: Await async check
            impulse = await self.volition.check_for_impulse()
            
            if impulse and self.orchestrator_ref:
                logger.info("⚡ VOLITION TRIGGERED: %s", impulse)
                
                # v6.3: Causal Telemetry
                state = await self.substrate.get_state_summary()
                telemetry_data = {
                    "timestamp": time.time(),
                    "valence": state['valence'],
                    "arousal": state['arousal'],
                    "dominance": state['dominance'],
                    "impulse_type": impulse,
                    "causal_link": "substrate_attractor"
                }
                
                # Log for prove_coupling.py to analyze
                self._log_causal_telemetry(telemetry_data)
                
                # Dispatch to Orchestrator via async loop
                try:
                    loop = self.orchestrator_ref.loop
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.orchestrator_ref.handle_impulse(impulse),
                            loop
                        )
                except Exception as e:
                    logger.error("Failed to dispatch impulse: %s", e)

    def _log_causal_telemetry(self, data: Dict[str, Any]):
        """Write causal telemetry to a dedicated log for analysis."""
        from core.config import config
        log_path = config.paths.data_dir / "telemetry" / "causal_behavior.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            logger.debug("Failed to write behavior telemetry: %s", e)

    def on_input_received(self, text: str):
        """Hook called when user speaks"""
        # Spike arousal and valence (Attention)
        stimulus = np.random.randn(64) * 0.5 # Simplified embedding
        self.substrate.inject_stimulus(stimulus)
        
    def get_state(self) -> Dict[str, Any]:
        """API Payload"""
        sub_state = self.substrate.get_state_summary()
        return {
            "substrate": sub_state,
            "surprise": self.predictive.get_surprise_level(),
            "broadcast": str(self.workspace.current_broadcast.content) if self.workspace.current_broadcast else None
        }

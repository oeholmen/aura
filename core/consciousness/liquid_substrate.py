
"""core/consciousness/liquid_substrate.py

Implements the "Liquid Substrate" - a continuous-time dynamical system that gives Aura 
persistence, emotional depth, and temporal continuity.

Based on Liquid Time-Constant Networks (LTCs) and global workspace theory.
"""

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

logger = logging.getLogger("Consciousness.Substrate")

@dataclass
class SubstrateConfig:
    """Configuration for Liquid Substrate"""

    neuron_count: int = 64
    time_constant: float = 0.1  # Integration time step (dt)
    update_rate: float = 20.0   # Hz (updates per second)
    decay_rate: float = 0.05    # State decay
    noise_level: float = 0.01   # Stochastic noise
    hebbian_rate: float = 0.001 # Learning rate for synaptic plasticity
    save_interval: int = 300    # Seconds between auto-saves
    state_file: Optional[Path] = None

class LiquidSubstrate:
    """The continuous dynamical core of Aura's consciousness.
    
    It runs a recurrent neural network (RNN) solved via ODEs.
    This ensures that Aura 'exists' continuously, even when not processing user input.
    """
    
    def __init__(self, config: SubstrateConfig = None):
        self.config = config or SubstrateConfig()
        
        # State Vectors
        self.x = np.zeros(self.config.neuron_count)  # Neuron activations (-1.0 to 1.0)
        self.v = np.zeros(self.config.neuron_count)  # Velocity (change in x)
        
        # Connectivity Matrix (The Connectome)
        self.W = np.random.randn(self.config.neuron_count, self.config.neuron_count) * 0.1
        
        # Operational Flags
        self.running = False
        self.thread: Optional[asyncio.Task] = None
        self.lock = asyncio.Lock()
        self.sync_lock = threading.Lock() # For sync state access
        self.last_update = 0.0
        
        # Emotional State Mapping (VAD)
        self.idx_valence = 0
        self.idx_arousal = 1
        self.idx_dominance = 2
        
        # Metadata
        self.tick_count = 0
        self.start_time = 0.0
        
        # Persistence
        if self.config.state_file:
            self.state_path = self.config.state_file
        else:
            try:
                from core.config import config as aura_config
                self.state_path = aura_config.paths.data_dir / "substrate_state.npy"
            except Exception:
                self.state_path = Path("data/substrate_state.npy")
                
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_state()

        logger.info("Liquid Substrate initialized (Unified, Neurons: %s)", self.config.neuron_count)

    async def start(self):
        """Start the continuous background existence loop"""
        if self.running:
            return
            
        self.running = True
        self.start_time = time.time()
            
        try:
            loop = asyncio.get_running_loop()
            self.thread = loop.create_task(self._run_loop(), name="LiquidConsciousness")
            logger.info("Liquid Substrate STARTED (Unified Cycle)")
        except RuntimeError:
            logger.error("Failed to start Liquid Substrate: No running asyncio loop.")
            self.running = False

    async def stop(self):
        """Stop the background loop"""
        self.running = False
        if self.thread:
            self.thread.cancel()
            self.thread = None
        self._save_state()
        logger.info("Liquid Substrate STOPPED")

    async def _run_loop(self):
        """Main ODE solver loop"""
        try:
            while self.running:
                start_time = time.time()
                
                # 1. Integrate Dynamics (ODE)
                await self._step_dynamics(dt=self.config.time_constant)
                
                # 2. Hebbian Learning
                if self.tick_count % 100 == 0:
                    await self._apply_plasticity()
                
                # 3. Persistence
                if self.tick_count % (self.config.update_rate * self.config.save_interval) == 0:
                    await asyncio.to_thread(self._save_state)
                
                self.tick_count += 1
                
                # 4. Enforce Update Rate (20Hz)
                elapsed = time.time() - start_time
                sleep_time = max(0, (1.0 / self.config.update_rate) - elapsed)
                await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            pass

    async def _step_dynamics(self, dt: float):
        """Update state using Euler integration for Neural ODE.
        dx/dt = -x + tanh(Wx + I) + noise
        """
        async with self.lock:
            x = self.x
            recurrent = np.dot(self.W, x)
            activity = np.tanh(recurrent)
            noise = np.random.randn(self.config.neuron_count) * self.config.noise_level
            dx = (-self.config.decay_rate * x + activity + noise) * dt
            
            new_x = np.clip(x + dx, -1.0, 1.0)
            
            with self.sync_lock:
                self.x = new_x
                self.v = dx
            self.last_update = time.time()

    async def _apply_plasticity(self):
        """Hebbian learning: Neurons that fire together, wire together."""
        async with self.lock:
            coactivity = np.outer(self.x, self.x)
            self.W += self.config.hebbian_rate * coactivity
            
            # Normalization
            norm = np.linalg.norm(self.W)
            if norm > 10.0:
                self.W *= (10.0 / norm)

    def inject_stimulus(self, vector: np.ndarray, weight: float = 1.0):
        if len(vector) != self.config.neuron_count:
            new_vec = np.zeros(self.config.neuron_count)
            size = min(len(vector), self.config.neuron_count)
            new_vec[:size] = vector[:size]
            vector = new_vec
            
        with self.sync_lock:
            self.x = np.clip(self.x + vector * weight * 0.1, -1.0, 1.0)

    def get_state_summary(self) -> Dict[str, float]:
        """Return high-level emotional/cognitive state"""
        with self.sync_lock:
            return {
                "valence": float(self.x[self.idx_valence]),
                "arousal": float(self.x[self.idx_arousal]),
                "dominance": float(self.x[self.idx_dominance]),
                "global_energy": float(np.mean(np.abs(self.x))),
                "volatility": float(np.mean(np.abs(self.v))) * 100
            }

    def _save_state(self):
        try:
            with open(self.state_path, 'wb') as f:
                np.savez_compressed(f, x=self.x, W=self.W, tick=self.tick_count)
        except Exception as e:
            logger.error("Failed to save substrate state: %s", e)

    def _load_state(self):
        if not self.state_path.exists():
            return
        try:
            with open(self.state_path, 'rb') as f:
                data = np.load(f)
                self.x = data['x']
                self.W = data['W']
                self.tick_count = int(data['tick'])
            logger.info("Substrate state restored.")
        except Exception as e:
            logger.error("Failed to load substrate state: %s", e)
            self.x = np.zeros(self.config.neuron_count)
            self.W = np.random.randn(self.config.neuron_count, self.config.neuron_count) * 0.1

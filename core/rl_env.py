import hashlib
import logging
import random
from typing import Any, Dict, Optional

import numpy as np

from .world_model.belief_graph import belief_graph

# Conditional import to avoid crashing if gym isn't installed
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    gym = object # Mock
    spaces = None

logger = logging.getLogger("Kernel.RL")

class AutonomyEnv(gym.Env if spaces else object):
    """Gymnasium Environment for Training the Agent via PPO/RL.
    Maps 'Goals' to 'Rewards' based on World Model state.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(self, agent_orchestrator, world_model=None):
        super().__init__()
        if not spaces:
            logger.warning("Gymnasium not installed. RL Disabled.")
            return

        self.agent = agent_orchestrator
        self.world_model = world_model or belief_graph
        
        # Action Space: 0=Browse, 1=Code, 2=Maintain, 3=Resource, 4=Sleep
        self.action_space = spaces.Discrete(5)
        
        # Observation Space: Simple 128-dim vector representing compressed world state
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(128,), dtype=np.float32)

    def _get_obs(self):
        """Derive a high-fidelity vector observation from the graph-based World Model.
        Includes internal state (valence, energy) and belief metrics.
        """
        # 1. Pull metrics from World Model
        summary = self.world_model.get_summary()
        self_data = self.world_model.graph.nodes.get(self.world_model.self_node_id, {})
        attrs = self_data.get("attributes", {})
        
        valence = attrs.get("emotional_valence", 0.5)
        energy = attrs.get("energy_level", 100) / 100.0
        
        # 2. Base Observation Vector
        # We start with a base derived from the belief summary and internal state
        obs = np.zeros(128, dtype=np.float32)
        obs[0] = valence
        obs[1] = energy
        obs[2] = min(1.0, summary.get("total_beliefs", 0) / 100.0)
        obs[3] = min(1.0, summary.get("strong", 0) / 50.0)
        obs[4] = min(1.0, summary.get("weak", 0) / 20.0)
        
        # 3. Deterministic hashing for consistency (No random noise)
        beliefs = self.world_model.get_beliefs()
        belief_str = str(sorted([str(b) for b in beliefs])) # Sort for determinism
        seed = int(hashlib.sha256(belief_str.encode()).hexdigest(), 16) % (2**32)
        
        # Use seed to generate deterministic feature vector (simulating embeddings)
        rng = np.random.default_rng(seed)
        obs[5:] = rng.standard_normal(123).astype(np.float32) * 0.1
        
        return obs

    def step(self, action):
        """Execute one step of the agent based on RL policy action.
        Rewards are grounded in world coherence and agent well-being.
        """
        logger.info("RL Agent invoking Action %s", action)
        
        goal_mapping = {
            0: "gather_info",
            1: "self_repair",
            2: "maintenance",
            3: "resource_optimization",
            4: "idle"
        }
        
        goal_name = goal_mapping.get(action, "idle")
        
        # Metrics before action
        prev_summary = self.world_model.get_summary()
        prev_strong = prev_summary.get("strong", 0)
        
        # In a fully autonomous loop, this would trigger the orchestrator
        # For RL training/simulation, we track the impact of the "intent"
        
        # Calculate Reward based on World Coherence and Goal Accomplishment
        # Reward increases for gaining strong beliefs or maintaining high energy
        reward = 0.0
        
        # Current state after "imagined" or real action
        curr_summary = self.world_model.get_summary()
        curr_strong = curr_summary.get("strong", 0)
        
        # Reward for gaining knowledge/certainty
        if curr_strong > prev_strong:
            reward += 0.5
            
        # Penalize low energy or idleness when energy is high
        self_data = self.world_model.graph.nodes.get(self.world_model.self_node_id, {})
        energy = self_data.get("attributes", {}).get("energy_level", 100)
        
        if action == 4: # Idle
            if energy > 80:
                reward -= 0.1 # Slight penalty for wasting high energy
            else:
                reward += 0.2 # Reward for resting when needed
        
        if energy < 20:
            reward -= 0.5 # Survival penalty
            
        truncated = False
        terminated = False
        info = {"goal": goal_name, "energy": energy, "strong_beliefs": curr_strong}
        
        obs = self._get_obs()
        return obs, reward, terminated, truncated, info

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        obs = self._get_obs()
        return obs, {}

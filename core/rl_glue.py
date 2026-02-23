# core/rl_glue.py
import logging

import numpy as np

logger = logging.getLogger("Kernel.RL_Glue")

class RLInterface:
    """Connects the Cognitive Architecture to the RL Environment.
    """

    def __init__(self, memory_nexus):
        self.memory = memory_nexus

    def get_state_vector(self) -> np.ndarray:
        """Converts current Agent State -> Vector (Observation).
        Uses the last few episodic logs + drive states.
        """
        # 1. Get embedding of last action (Mocking embedding here)
        # In prod, self.memory.vector.embed(last_log)
        action_vector = np.random.rand(64) 
        
        # 2. Get Drive States (Hunger/Curiosity)
        # Assuming we can access drives from here, or pass them in
        drive_vector = np.array([0.5, 0.8, 0.2]) # Mock values
        
        # 3. Concatenate and Pad
        full_vec = np.concatenate([action_vector, drive_vector])
        
        # Pad to 128 dim (as defined in rl_env.py)
        if len(full_vec) < 128:
            full_vec = np.pad(full_vec, (0, 128 - len(full_vec)))
            
        return full_vec

    def calculate_reward(self, result: dict) -> float:
        """Determines reward based on tool execution success.
        """
        if result.get("ok"):
            return 1.0
        return -0.1

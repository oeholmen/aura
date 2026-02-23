
"""core/consciousness/predictive_engine.py

Implements Predictive Coding / Free Energy Principle.
The brain is a prediction machine. It constantly generates expectations about the future.
"Surprise" (Prediction Error) is the difference between Expectation and Reality.
Minimizing surprise is the core drive of the system.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("Consciousness.Predictive")

@dataclass
class Prediction:
    """An expectation about the future state"""
    source_module: str
    content: str
    expected_state_vector: Optional[np.ndarray] = None # Predicted substrate state
    expected_changes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8 # Precision
    timestamp: float = field(default_factory=time.time)

class PredictiveEngine:
    """Manages the hierarchy of predictions and error minimization.
    Combines world-model state predictions and substrate-level vector predictions.
    """
    
    def __init__(self, world_model=None, neuron_count: int = 64):
        self.world_model = world_model
        self.neuron_count = neuron_count
        self.active_predictions: List[Prediction] = []
        self.total_surprise = 0.0
        self.surprise_history: List[float] = []
        
        # Simple generative model for substrate
        self.internal_model = np.zeros(neuron_count)
        
        logger.info("Predictive Engine initialized (Unified).")
        
    async def predict_next_state(self, action: Dict[str, Any]) -> Prediction:
        """Predict the outcome of an action on the world state.
        """
        prediction = Prediction(
            source_module="GenerativeModel",
            content=f"Predicting outcome of {action.get('type', 'action')}",
            timestamp=time.time()
        )
        
        if self.world_model:
            try:
                current_summary = self.world_model.get_summary()
                action_type = action.get("type", "unknown")
                
                if action_type == "search":
                    prediction.expected_changes["total_beliefs"] = current_summary.get("total_beliefs", 0) + 2
                elif action_type == "apply_fix":
                    prediction.expected_changes["strong"] = current_summary.get("strong", 0) + 1
            except Exception as e:
                logger.debug("World model prediction failed: %s", e)

        # Substrate prediction (momentum heuristic)
        prediction.expected_state_vector = self.internal_model * 0.95
        
        self.active_predictions.append(prediction)
        if len(self.active_predictions) > 10:
            self.active_predictions.pop(0)
            
        return prediction

    def compute_surprise(self, actual_state_summary: Dict[str, Any], actual_substrate_x: Optional[np.ndarray] = None) -> float:
        """Compare actual state with predicted state to compute surprise (prediction error).
        """
        if not self.active_predictions:
            return 0.0
            
        best_p = self.active_predictions[-1]
        surprise = 0.0
        
        # 1. World Model Surprise
        for key, p_val in best_p.expected_changes.items():
            a_val = actual_state_summary.get(key, 0)
            surprise += abs(p_val - a_val)
            
        # 2. Substrate Surprise
        if actual_substrate_x is not None and best_p.expected_state_vector is not None:
            error_vector = actual_substrate_x - best_p.expected_state_vector
            sub_surprise = np.mean(np.square(error_vector))
            surprise += sub_surprise * 5.0 # Weight substrate surprise
            
            # Update internal model (Learning)
            alpha = 0.1
            self.internal_model = (1 - alpha) * self.internal_model + alpha * actual_substrate_x

        # Normalize/Scale surprise
        normalized_surprise = min(1.0, surprise / 5.0)
        self.total_surprise = (self.total_surprise * 0.9) + (normalized_surprise * 0.1)
        self.surprise_history.append(normalized_surprise)
        
        if len(self.surprise_history) > 100:
            self.surprise_history.pop(0)
            
        if normalized_surprise > 0.6:
            logger.warning("HIGH SURPRIZE: %.2f", normalized_surprise)
            
        return normalized_surprise

    def get_surprise_metrics(self) -> Dict[str, float]:
        return {
            "current_surprise": self.surprise_history[-1] if self.surprise_history else 0.0,
            "average_surprise": float(np.mean(self.surprise_history)) if self.surprise_history else 0.0,
            "total_accumulated": self.total_surprise
        }

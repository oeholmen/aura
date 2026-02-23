import numpy as np


class PredictiveSelfModel:
    def __init__(self, dim: int = 256):
        self.dim = dim
        # Weights map context -> predicted_next_state
        self.weights = np.zeros((dim,), dtype=np.float32)
        self.state = np.zeros((dim,), dtype=np.float32)

    def predict(self, context_vector: np.ndarray) -> np.ndarray:
        """Simple linear prediction of next state based on context.
        """
        # Element-wise weighting for simplicity in this V1
        return np.tanh(self.weights * context_vector[:self.dim])

    def observe_and_update(self, context_vector: np.ndarray, lr: float = 0.01) -> float:
        """1. Predict next state from current context.
        2. Observe actual state (using the context itself as the proxy for 'now').
        3. Compute error (surprise).
        4. Update weights to minimize future error.
        
        Returns:
            prediction_error (float): Magnitude of surprise.

        """
        if context_vector.shape[0] < self.dim:
             context_vector = np.pad(context_vector, (0, self.dim - context_vector.shape[0]))
        
        # In a real predictive coding loop, 'context' would be T-1 and we'd observe T.
        # Here we simulate the loop by trying to predict the input signal stability.
        
        obs = context_vector[:self.dim]
        pred = self.predict(obs) # Simplified: attempting to predict self-consistency
        
        error = obs - pred
        
        # Simple hebbian-like update
        self.weights += lr * error * obs
        
        # Clip weights to prevent instability
        self.weights = np.clip(self.weights, -1.0, 1.0)
        
        self.state = obs
        
        # Return error norm as 'Surprise' signal
        return float(np.linalg.norm(error))

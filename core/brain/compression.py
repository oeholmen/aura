
# core/brain/compression.py
import logging

import numpy as np

logger = logging.getLogger("Aura.CognitiveCompressor")

class CognitiveCompressor:
    """Squashes high-dimensional LLM embeddings into a dense, low-dimensional space
    so the CPU can calculate the Unified Phenomenal Field in real-time.
    Based on Johnson-Lindenstrauss lemma.
    """

    def __init__(self, input_dim: int = 1536, target_dim: int = 64):
        self.input_dim = input_dim
        self.target_dim = target_dim
        
        # We seed the random generator so the projection matrix is identical 
        # every time Aura boots up. If this changed, her "mind" would scramble on reboot.
        np.random.seed(42) 
        
        # Create a fixed random projection matrix (Gaussian distribution)
        # Scaled to preserve vector distances (Johnson-Lindenstrauss)
        self.projection_matrix = np.random.randn(self.input_dim, self.target_dim) / np.sqrt(self.target_dim)
        
        logger.info("Initialized Cognitive Compressor: %sD -> %sD", input_dim, target_dim)

    def compress(self, vector: np.ndarray) -> np.ndarray:
        """Projects a large embedding down to the dense target dimension."""
        if vector is None:
            return np.zeros(self.target_dim)
            
        # Ensure it's a 1D numpy array
        vector = np.atleast_1d(vector).flatten()
        
        # Pad with zeros if the input is unexpectedly small
        if len(vector) < self.input_dim:
            padded = np.zeros(self.input_dim)
            padded[:len(vector)] = vector
            vector = padded
        # Truncate if unexpectedly large
        elif len(vector) > self.input_dim:
            vector = vector[:self.input_dim]
            
        # Matrix multiplication to squash the dimensions
        compressed_vector = np.dot(vector, self.projection_matrix)
        
        # L2 Normalize the result so it doesn't blow up the tensor math downstream
        norm = np.linalg.norm(compressed_vector)
        if norm > 0:
            compressed_vector = compressed_vector / norm
            
        return compressed_vector

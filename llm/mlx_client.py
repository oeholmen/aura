import logging
import sys

logger = logging.getLogger("LLM.MLX")

class MLXClient:
    """
    Client for running local LLMs on Apple Silicon via mlx_lm.
    """
    def __init__(self, model_path="mlx-community/Mistral-7B-Instruct-v0.3-4bit"):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        try:
            from mlx_lm import load
            logger.info(f"Loading MLX Model: {self.model_path}...")
            self.model, self.tokenizer = load(self.model_path)
            logger.info("MLX Model Loaded Successfully.")
        except ImportError:
            logger.error("mlx-lm not installed. Run 'pip install mlx-lm'.")
        except Exception as e:
            logger.error(f"Failed to load MLX model: {e}")

    def call(self, prompt: str, **kwargs) -> dict:
        if not self.model:
            return {"ok": False, "error": "MLX Model not loaded (pkg missing?)"}

        try:
            from mlx_lm import generate
            logger.info("Generating response with MLX...")
            response_text = generate(
                self.model, 
                self.tokenizer, 
                prompt=prompt, 
                max_tokens=800, 
                verbose=False
            )
            return {"ok": True, "text": response_text}
        except Exception as e:
            logger.error(f"MLX Generation Error: {e}")
            return {"ok": False, "error": str(e)}

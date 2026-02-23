# llm/client.py - Sovereign Deployment
import logging
from typing import Dict, Any, Optional
import os

# Sovereign Imports
from core.brain.local_llm import LocalBrain

logger = logging.getLogger("LLM.Sovereign")

class OpenAIClient:
    """
    Sovereign Replacement for Legacy OpenAI Client.
    Redirects all calls to the local Ollama brain.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        # Legacy compat: api_key is ignored in sovereign mode
        self.brain = LocalBrain()
        logger.info("Sovereign LLM Client initialized (Ollama bridge).")

    def call(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Calls the local sovereign brain.
        """
        try:
            # We map kwargs for compatibility if needed, but LocalBrain.generate handles core logic
            text = self.brain.generate(prompt, system_prompt=system)
            
            if "Error" in text:
                 return {"ok": False, "error": text}
                 
            return {
                "ok": True, 
                "text": text, 
                "raw": {"provider": "sovereign", "model": self.brain.model}
            }
        except Exception as e:
            logger.exception("Sovereign brain call failed")
            return {"ok": False, "error": str(e)}

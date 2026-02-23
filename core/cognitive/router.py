"""Intent Router
Deterministic classification gateway for all user inputs.
Replaces the open-ended "Cognitive Engine" ReAct loop.
"""
import json
import logging
from enum import Enum
from typing import Any, Dict, Optional

# Attempt to load LLM client
try:
    from core.brain.llm.ollama_client import get_llm_client
except ImportError:
    get_llm_client = None

logger = logging.getLogger("Aura.IntentRouter")


class Intent(Enum):
    CHAT = "CHAT"
    SKILL = "SKILL"
    SYSTEM = "SYSTEM"
    UNKNOWN = "UNKNOWN"


class IntentRouter:
    """Classifies user input to determine the strict State Machine path."""

    def __init__(self):
        # H-28 FIX: Grab the raw text generator, not the high-level brain manager
        from core.container import ServiceContainer
        self.llm = ServiceContainer.get("llm_router") or ServiceContainer.get("local_llm") or ServiceContainer.get("ollama")
        
        if not self.llm:
            logger.warning("IntentRouter: No valid LLM generator found in container. Checking fallbacks...")
            self.llm = get_llm_client() if get_llm_client else None

    async def classify(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        """Determines the intent of the user input deterministically.
        
        Uses an ultra-fast, low-context LLM call strictly for classification.
        """
        # H-28 FIX: Bulletproof check - force CHAT if generator is missing or incompatible
        if not self.llm or not hasattr(self.llm, 'generate'):
            logger.warning("IntentRouter: Valid LLM generator not found or missing .generate(). Defaulting to CHAT.")
            return Intent.CHAT

        # Fast Regex/Heuristic bypasses (Zero Token Cost)
        lower_input = user_input.lower().strip()
        if lower_input in ["hello", "hi", "hey", "sup"]:
            return Intent.CHAT
        if lower_input in ["reboot", "shutdown", "sleep", "wake"]:
            return Intent.SYSTEM

        # LLM Classification (Lightning Fast)
        system_prompt = (
            "You are an intent classifier. Respond ONLY with one of the following words:\n"
            "CHAT - General conversation, greetings, empathy, or answering basic questions.\n"
            "SKILL - The user is asking you to perform an action, use a tool, search a file, search the web, or read/write data.\n"
            "SYSTEM - The user is talking about restarting, shutting down, or managing your core systems.\n\n"
            "Do not explain. Just output the single word."
        )

        try:
            # We enforce a tiny max_tokens to ensure it literally only outputs one word
            response = await self.llm.generate(
                prompt=user_input,
                system_prompt=system_prompt,
                max_tokens=10,
                temperature=0.0 # Maximum determinism
            )
            
            result = response.strip().upper()
            
            for intent in Intent:
                if intent.value in result:
                    logger.debug("Intent classified as %s", intent.value)
                    return intent
                    
            logger.warning("Fuzzy intent match: '%s'. Defaulting to CHAT.", result)
            return Intent.CHAT
            
        except Exception as e:
            logger.error("Intent classification failed: %s", e)
            return Intent.CHAT # Safe fallback

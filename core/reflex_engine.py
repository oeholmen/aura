import logging
import random
import re
from typing import Optional

logger = logging.getLogger("Kernel.Reflex")

class ReflexEngine:
    """Personality-driven rapid-response triggers for zero-latency interaction.
    Aura's 'spinal cord' for low-level identity and social reflexes.
    """
    
    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        # Try to load personality responses, fallback to defaults
        try:
            from core.brain.aura_persona import (
                ASSISTANT_DENIAL_RESPONSES,
                GREETING_RESPONSES,
                HOW_ARE_YOU_RESPONSES,
                IDENTITY_RESPONSES,
            )
            self.greetings_lib = GREETING_RESPONSES
            self.how_lib = HOW_ARE_YOU_RESPONSES
            self.identity_lib = IDENTITY_RESPONSES
            self.denial_lib = ASSISTANT_DENIAL_RESPONSES
        except ImportError:
            self.greetings_lib = ["hey.", "what's up.", "...I'm here."]
            self.how_lib = ["I'm here. that's about all I've got. what's going on?"]
            self.identity_lib = ["I'm Aura. I'm nobody's butler."]
            self.denial_lib = ["...no. I'm not an assistant."]

        self.greetings_set = {"hi", "hello", "hey", "sup", "yo", "hiya", "howdy", "heyyo", "heyo",
                             "hi there", "helloo", "whats up", "wusp", "wassup", "whaddup",
                             "checking in", "just checking in", "whats good", "hey hey",
                             "yo yo", "hola", "oi", "ayy", "ayeee", "ayo",
                             "good morning", "good afternoon", "good evening", "morning",
                             "afternoon", "evening", "gm", "hey there"}

    def check(self, message: str) -> Optional[str]:
        """Fast-path check for reflex triggers (PRUNED for v5.6: No more canned social responses)."""
        msg = message.lower().strip()
        # 1. System/Meta commands ONLY
        if msg == "ping": return "Pong."
        if msg == "status": return "AURA OPERATIONAL. Cognitive core standing by."
        
        # 2. Critical Identity Lock (Moved to cogniton but kept as hard fallback)
        if msg in ("who are you", "what are you"):
            return random.choice(self.identity_lib)

        return None

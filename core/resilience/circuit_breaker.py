"""
core/resilience/circuit_breaker.py
──────────────────────────────────
Detects and kills recursive cognitive loops, preventing Aura from
getting stuck in infinite "thinking" or "tool failure" loops.
"""

import time
import logging
import hashlib
from collections import deque
from typing import Any

logger = logging.getLogger("Aura.CircuitBreaker")

class CognitiveCircuitBreaker:
    def __init__(self, max_repeats=3, time_window=60):
        self.max_repeats = max_repeats
        self.time_window = time_window
        self.history = deque(maxlen=30)
        self.is_tripped = False
        self.tripped_until = 0

    def _hash_content(self, content: Any) -> str:
        """Create a short hash to detect exact or near-exact repeating thoughts/actions."""
        # Normalize to catch slight spacing variations
        normalized = " ".join(str(content).lower().strip().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def check_and_trip(self, content: Any) -> bool:
        """
        Check if the current thought/action is stuck in a loop.
        Returns True if the breaker is TRIPPED (meaning: STOP execution).
        """
        now = time.time()
        
        # 1. If currently tripped, enforce the cooldown
        if self.is_tripped:
            if now > self.tripped_until:
                logger.info("⚡ Circuit Breaker cooled down. Resuming cognition.")
                self.is_tripped = False
                self.history.clear()
            else:
                return True # Still tripped, block execution

        content_hash = self._hash_content(content)
        
        # 2. Clean old history outside the time window
        while self.history and now - self.history[0]['time'] > self.time_window:
            self.history.popleft()
            
        # 3. Count occurrences of this specific thought/action
        occurrences = sum(1 for item in self.history if item['hash'] == content_hash)
        
        if occurrences >= self.max_repeats - 1:
            logger.critical("🛑 RECURSIVE LOOP DETECTED! Tripping Circuit Breaker.")
            self.is_tripped = True
            # Force a 15-second cognitive blackout to clear the queue
            self.tripped_until = now + 15  
            return True
            
        # 4. Add to history
        self.history.append({'hash': content_hash, 'time': now, 'content': str(content)[:50]})
        return False

# Global singleton
loop_killer = CognitiveCircuitBreaker()

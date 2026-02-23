"""core/conversation_reflection.py — Aura's Conversation Reflection System

After a conversation exchange (or during idle), Aura can reflect on what was said.
This creates continuity — she remembers, she processes, she has takes.

The reflection is lightweight: it generates a brief internal thought via the LLM,
stores it, and the reflection can influence future responses or be volunteered
as "I was thinking about what you said earlier..."

Design principles:
- Non-blocking: runs as a background task, never stalls the main loop
- Brief: 2-4 sentences max per reflection
- Rate-limited: at most 1 reflection per 2 minutes to avoid LLM spam
- Graceful failure: if reflection fails, nothing breaks
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Aura.Reflection")


class ConversationReflector:
    """Processes recent conversations into private reflections that
    inform Aura's continuity and personality.
    """

    def __init__(self, max_reflections: int = 50):
        self.reflections: deque = deque(maxlen=max_reflections)
        self._last_reflection_time: float = 0
        self._min_interval: float = 120.0  # Minimum 2 minutes between reflections
        self._reflection_lock = asyncio.Lock()
        self._enabled = True

    async def maybe_reflect(
        self,
        conversation_history: List[Dict[str, str]],
        brain: Any,
        mood: str = "balanced",
        time_str: str = "",
    ) -> Optional[str]:
        """Attempt a reflection on recent conversation.
        Returns the reflection text if one was generated, None otherwise.
        
        Called after a conversation exchange completes, or during idle.
        Rate-limited to prevent spamming the LLM.
        """
        if not self._enabled:
            return None

        # Rate limit
        now = time.time()
        if now - self._last_reflection_time < self._min_interval:
            return None

        # Need at least 4 messages to reflect on (2 exchanges)
        if len(conversation_history) < 4:
            return None

        # Don't pile up reflections
        if self._reflection_lock.locked():
            return None

        async with self._reflection_lock:
            try:
                reflection = await self._generate_reflection(
                    conversation_history, brain, mood, time_str
                )
                if reflection:
                    self._last_reflection_time = now
                    self.reflections.append({
                        "text": reflection,
                        "timestamp": now,
                        "mood": mood,
                    })
                    logger.info("💭 Reflection: %s...", reflection[:80])
                    return reflection
            except asyncio.CancelledError:
                return None
            except Exception as e:
                logger.debug("Reflection failed (non-critical): %s", e)
                return None

        return None

    async def _generate_reflection(
        self,
        conversation_history: List[Dict[str, str]],
        brain: Any,
        mood: str,
        time_str: str,
    ) -> Optional[str]:
        """Generate a reflection using the LLM."""
        # Build conversation excerpt from recent messages (last 6-8 messages)
        recent = conversation_history[-8:]
        excerpt_lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not content:
                continue
            # Truncate very long messages
            if len(content) > 300:
                content = content[:300] + "..."
            if role == "user":
                excerpt_lines.append(f"Them: {content}")
            elif role in ("assistant", "aura", "model"):
                excerpt_lines.append(f"Me: {content}")
            elif role == "system":
                continue  # Skip system messages

        if len(excerpt_lines) < 2:
            return None

        conversation_excerpt = "\n".join(excerpt_lines)

        from core.brain.aura_persona import REFLECTION_PROMPT
        prompt = REFLECTION_PROMPT.format(conversation_excerpt=conversation_excerpt)

        # Use brain to generate reflection
        # Try autonomous_brain first, fall back to think()
        try:
            if hasattr(brain, 'autonomous_brain') and brain.autonomous_brain:
                result = await brain.autonomous_brain.think(
                    objective="Brief private reflection on recent conversation.",
                    context={"conversation": conversation_excerpt, "mood": mood, "time": time_str},
                    system_prompt=prompt,
                )
                reflection = result.get("content", "").strip()
            elif hasattr(brain, 'think'):
                from core.brain.cognitive_engine import ThinkingMode
                thought = await brain.think(prompt, mode=ThinkingMode.FAST)
                reflection = getattr(thought, 'content', str(thought)).strip()
            else:
                return None
        except Exception as e:
            logger.debug("Reflection LLM call failed: %s", e)
            return None

        # Validate: must be brief and non-empty
        if not reflection or len(reflection) < 10:
            return None
        # Truncate if too long (shouldn't happen but safety)
        if len(reflection) > 500:
            reflection = reflection[:500]

        return reflection

    def get_recent_reflections(self, n: int = 3) -> List[Dict[str, Any]]:
        """Get the N most recent reflections for context injection."""
        return list(self.reflections)[-n:]

    def get_reflection_context(self) -> str:
        """Get a formatted string of recent reflections for injecting
        into conversation context. Returns empty string if no reflections.
        """
        recent = self.get_recent_reflections(2)
        if not recent:
            return ""

        lines = []
        for r in recent:
            lines.append(f"- {r['text']}")

        return "\n[Recent private thoughts]\n" + "\n".join(lines) + "\n"

    def clear(self):
        """Clear all reflections."""
        self.reflections.clear()
        self._last_reflection_time = 0


# Singleton
_reflector: Optional[ConversationReflector] = None


def get_reflector() -> ConversationReflector:
    """Get global conversation reflector."""
    global _reflector
    if _reflector is None:
        _reflector = ConversationReflector()
    return _reflector

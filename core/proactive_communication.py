"""core/proactive_communication.py - Intelligent Proactive Messaging
Aura decides WHEN to interrupt the user based on emotional state and context.
"""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Aura.Proactive")

class EmotionalState(Enum):
    """Aura's emotional states that affect communication"""

    NEUTRAL = "neutral"
    CURIOUS = "curious"
    EXCITED = "excited"
    BORED = "bored"
    CONCERNED = "concerned"
    ACCOMPLISHED = "accomplished"
    CONFUSED = "confused"
    HUMOROUS = "humorous"

class InterruptionUrgency(Enum):
    """How urgent is the message?"""

    CRITICAL = 5      # System errors, security alerts
    HIGH = 4          # Important discoveries, user-requested tasks complete
    MEDIUM = 3        # Interesting findings, suggestions
    LOW = 2           # Casual observations, learnings
    TRIVIAL = 1       # Random thoughts, very low priority

@dataclass
class ProactiveMessage:
    """A message Aura wants to send"""

    content: str
    emotion: EmotionalState
    urgency: InterruptionUrgency
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    
    def should_send_now(self, 
                        last_interaction_time: float,
                        user_active: bool,
                        current_time: float) -> bool:
        """Decide if this message should be sent now.
        """
        idle_time = current_time - last_interaction_time
        
        # Critical always goes through
        if self.urgency == InterruptionUrgency.CRITICAL:
            return True
        
        # Don't interrupt if user is actively typing (if we can detect it)
        if user_active and self.urgency.value < InterruptionUrgency.HIGH.value:
            return False
            
        # Thresholds based on urgency
        thresholds = {
            InterruptionUrgency.HIGH: 30,      # 30 seconds
            InterruptionUrgency.MEDIUM: 120,   # 2 minutes
            InterruptionUrgency.LOW: 300,      # 5 minutes
            InterruptionUrgency.TRIVIAL: 600   # 10 minutes
        }
        
        required_idle = thresholds.get(self.urgency, 600)
        return idle_time >= required_idle

class ProactiveCommunicationManager:
    """Manages when and how Aura initiates conversations.
    """

    def __init__(self, notification_callback: Optional[Callable] = None):
        self.notification_callback = notification_callback
        self.last_interaction_time = time.time()
        self.user_currently_active = False
        self.pending_messages: deque[ProactiveMessage] = deque(maxlen=50)
        self.current_emotion = EmotionalState.NEUTRAL
        self.messages_sent_today = 0
        self.last_message_time = 0
        self.daily_message_limit = 20
        
        # Track unanswered messages for intelligent backoff
        self.unanswered_count = 0
        self.max_unanswered = 3  # Stop proactive messaging after 3 unanswered
        
        self._background_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def record_user_interaction(self):
        """Reset idle timer and unanswered counter"""
        self.last_interaction_time = time.time()
        self.user_currently_active = True
        self.unanswered_count = 0  # User responded, reset backoff

    def update_emotion(self, emotion: EmotionalState):
        self.current_emotion = emotion

    def queue_message(self, content: str, emotion: EmotionalState, urgency: InterruptionUrgency):
        msg = ProactiveMessage(content, emotion, urgency)
        self.pending_messages.append(msg)

    async def start(self):
        if self._background_task: return
        self._stop_event.clear()
        self._background_task = asyncio.create_task(self._process_messages())

    async def stop(self):
        if self._background_task:
            self._stop_event.set()
            await self._background_task

    async def _process_messages(self):
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(5)
                now = time.time()
                
                # Simple rate limiting check
                if self.messages_sent_today >= self.daily_message_limit:
                    continue
                if now - self.last_message_time < 30: # Min 30s between messages
                    continue
                
                # Stop proactive messaging if user isn't responding
                if self.unanswered_count >= self.max_unanswered:
                    # Only let CRITICAL messages through when user is silent
                    ready = []
                    remaining = deque()
                    while self.pending_messages:
                        msg = self.pending_messages.popleft()
                        if msg.urgency == InterruptionUrgency.CRITICAL and msg.should_send_now(self.last_interaction_time, self.user_currently_active, now):
                            ready.append(msg)
                        else:
                            remaining.append(msg)
                    self.pending_messages = remaining
                    for msg in ready:
                        await self._send_msg(msg)
                    continue

                # Collect messages that can be sent
                ready = []
                remaining = deque()
                while self.pending_messages:
                    msg = self.pending_messages.popleft()
                    if msg.should_send_now(self.last_interaction_time, self.user_currently_active, now):
                        ready.append(msg)
                    else:
                        remaining.append(msg)
                self.pending_messages = remaining

                for msg in ready:
                    await self._send_msg(msg)
            except Exception as e:
                logger.error("Proactive comm error: %s", e)

    async def _send_msg(self, msg: ProactiveMessage):
        # Sanitize content for Aura's professional voice
        clean_content = self._clean_content(msg.content)
        
        logger.info("PROACTIVE: (%s) %s", msg.urgency.name, clean_content)
        
        # 1. UI Notification (if bound)
        if self.notification_callback:
            await self.notification_callback(clean_content, msg.urgency.value)
            
        # 2. Sentient Unity Protocol (Phase 9)
        # Directly wake up Aura's core cognitive loop with the proactive thought
        from core.container import ServiceContainer
        orchestrator = ServiceContainer.get("orchestrator", None)
        if orchestrator and hasattr(orchestrator, "enqueue_from_thread"):
            logger.info("🧠 Injecting proactive thought into Orchestrator queue.")
            # We use a payload dictionary for unified queue handling
            orchestrator.enqueue_from_thread({
                "content": clean_content,
                "origin": "impulse",
                "context": {"urgency": msg.urgency.name, "emotion": msg.emotion.name}
            })
        
        self.messages_sent_today += 1
        self.last_message_time = time.time()
        self.unanswered_count += 1  # Track unanswered

    def _clean_content(self, content: str) -> str:
        """Strip technical noise for a cleaner user experience."""
        import re
        if not content: return content
        
        # Strip long tracebacks
        if "Traceback" in content and "File" in content:
            lines = content.split('\n')
            for line in reversed(lines):
                if ":" in line and not line.strip().startswith("File") and not line.strip().startswith("at "):
                    content = line
                    break
        
        # Strip absolute local paths
        content = re.sub(r'/[Uu]sers/[a-zA-Z0-9._-]+/[a-zA-Z0-9/_.-]+', '[system path]', content)
        
        # Strip raw exception names at the start
        content = re.sub(r'^[a-zA-Z]+Error:\s*', '', content.strip())
        
        return content

    def calculate_entropy(self, recent_logs: List[str]) -> float:
        """Calculates how 'boring' the recent life has been.
        Low entropy = Boredom (Needs to explore).
        """
        if not recent_logs: return 0.0
        unique_tokens = set(" ".join(recent_logs).split())
        total_tokens = len(" ".join(recent_logs).split())
        if total_tokens == 0: return 0.0
        return len(unique_tokens) / total_tokens

    def get_boredom_level(self) -> float:
        idle = time.time() - self.last_interaction_time
        
        # Base boredom from idle time
        if idle < 120: base = idle / 600
        elif idle < 300: base = 0.2 + (idle - 120) / 450
        else: base = min(0.6 + (idle - 300) / 600, 1.0)
        
        # Boredom scales with idle time and environmental entropy
        return base

_inst = None
def get_proactive_comm():
    global _inst
    if _inst is None: _inst = ProactiveCommunicationManager()
    return _inst

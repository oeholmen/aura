import logging
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger("Core.Events")

class EventPriority(IntEnum):
    """High value = high priority"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3

class EventType(Enum):
    USER_MESSAGE = auto()
    MIC_TRANSCRIPT = auto()
    TRAINING_STATUS = auto()
    SYSTEM = auto()
    DOWNLOAD_PROGRESS = auto()
    ERROR = auto()
    HEALTH_ALERT = auto()
    SELF_MOD_PROPOSAL = auto()
    SKILL_EXECUTED = auto()
    STATE_CHANGE = auto()

@dataclass(order=True)
class Event:
    priority: EventPriority = field(default=EventPriority.NORMAL, compare=True)
    ts: float = field(default_factory=time.time, compare=True)
    type: EventType = field(default=EventType.SYSTEM, compare=False)
    payload: Dict[str, Any] = field(default_factory=dict, compare=False)
    source: str = field(default="", compare=False)
    retry_count: int = field(default=0, compare=False)

class InputBus:
    """Thread-safe event multiplexer with pub/sub + priority queue.
    Includes a Dead Letter Queue (DLQ) for failed event processing.
    """

    def __init__(self, maxsize: int = 2000):
        # PriorityQueue pops lowest value first.  We want HIGH priority first,
        # so we store (-priority, ts, event) tuples.  Negating priority makes
        # CRITICAL(-3) sort before LOW(0).  Timestamp breaks ties (FIFO within
        # same priority).
        self._q: queue.PriorityQueue = queue.PriorityQueue(maxsize=maxsize)
        self._dlq: List[Event] = []
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="Aura.Events")
        self._dlq_lock = threading.Lock()

    def publish(self, event: Event, block: bool = False, timeout: Optional[float] = None) -> None:
        """Enqueue an event and notify all typed subscribers synchronously."""
        self._notify_subscribers(event)
        self._enqueue(event, block, timeout)

    def publish_async(self, event: Event, block: bool = False, timeout: Optional[float] = None) -> None:
        """Enqueue an event and notify subscribers in a background thread."""
        self._executor.submit(self._notify_subscribers, event)
        self._enqueue(event, block, timeout)

    def _enqueue(self, event: Event, block: bool = False, timeout: Optional[float] = None) -> None:
        """Internal helper — stores (-priority, ts, event) for correct pop order."""
        try:
            self._q.put((-int(event.priority), event.ts, event), block=block, timeout=timeout)
        except queue.Full:
            logger.warning("Event queue full — dropping event type=%s", event.type.name)

    def next(self, timeout: Optional[float] = 0.1) -> Optional[Event]:
        """Poll the next highest-priority event from the queue."""
        try:
            _, _, event = self._q.get(timeout=timeout)
            return event
        except queue.Empty:
            return None

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """Register a callback for a specific event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(callback)
            logger.debug("Subscriber registered for %s", event_type.name)

    def emit(self, event_type: EventType, payload: Dict[str, Any], source: str = "", priority: EventPriority = EventPriority.NORMAL) -> None:
        """Convenience: create and publish an Event in one call."""
        event = Event(type=event_type, payload=payload, source=source, priority=priority)
        self.publish(event)

    def _notify_subscribers(self, event: Event) -> None:
        """Call all subscribers for this event type. Errors are logged, failing events go to DLQ."""
        with self._lock:
            # Copy list to allow unsubscription during iteration if ever needed
            callbacks = list(self._subscribers.get(event.type, []))

        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(
                    "Subscriber %s failed on %s: %s",
                    getattr(cb, "__name__", repr(cb)),
                    event.type.name,
                    e,
                    exc_info=False,
                )
                self._handle_failure(event)

    def _handle_failure(self, event: Event):
        """Track failures and move persistent failures to DLQ."""
        event.retry_count += 1
        if event.retry_count >= 3:
            with self._dlq_lock:
                if len(self._dlq) < 500: # Bound DLQ
                    self._dlq.append(event)
                    logger.critical("Event type=%s moved to Dead Letter Queue after 3 failures.", event.type.name)
                else:
                    logger.error("DLQ full. Dropping failed event type=%s", event.type.name)

    @property
    def subscriber_count(self) -> int:
        """Total number of registered subscribers across all event types."""
        with self._lock:
            return sum(len(cbs) for cbs in self._subscribers.values())

    def get_dlq_stats(self) -> Dict[str, Any]:
        """Report on dead events."""
        with self._dlq_lock:
            return {
                "count": len(self._dlq),
                "types": [e.type.name for e in self._dlq[-10:]] # Last 10
            }

    def shutdown(self) -> None:
        """Shutdown the executor."""
        self._executor.shutdown(wait=True)


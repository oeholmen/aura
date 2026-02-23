import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set

import redis.asyncio as redis
from core.config import config

logger = logging.getLogger("Kernel.EventBus")


class AuraEventBus:
    """Topic-based Asynchronous Event Bus for unified messaging across sub-systems.

    Supports high-throughput pub/sub and cross-process (Redis-backed) event propagation.
    H-12 FIX: Decoupled brain requirement — utilizes Redis for IPC when enabled.
    """

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock_obj: Optional[asyncio.Lock] = None
        
        # Redis integration (H-12)
        self._redis: Optional[redis.Redis] = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._redis_url = config.redis.url if hasattr(config, "redis") else "redis://localhost:6379/0"
        self._use_redis = config.redis.use_for_events if hasattr(config, "redis") else False

        logger.info("AuraEventBus initialized (Redis: %s).", self._use_redis)

    @property
    def _lock(self) -> asyncio.Lock:
        if self._lock_obj is None:
            self._lock_obj = asyncio.Lock()
        return self._lock_obj

    async def _setup_redis(self):
        """Initialize Redis connection and start listener task."""
        if not self._use_redis or self._redis:
            return
            
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            self._pubsub_task = asyncio.create_task(self._redis_listener())
            logger.info("AuraEventBus: Redis Pub/Sub connection established.")
        except Exception as e:
            logger.error("AuraEventBus: Failed to connect to Redis: %s", e)
            self._use_redis = False

    async def _redis_listener(self):
        """Listen for events from other processes via Redis."""
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("aura/events/*")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"]
                    topic = channel.split("/")[-1]
                    try:
                        data = json.loads(message["data"])
                        # Publish locally to this process's subscribers
                        await self._publish_local(topic, data)
                    except json.JSONDecodeError:
                        logger.warning("AuraEventBus: Received malformed JSON from Redis for topic %s", topic)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("AuraEventBus: Redis listener crashed: %s", e)
        finally:
            await pubsub.punsubscribe("aura/events/*")
            await pubsub.close()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Bind the bus to a specific event loop."""
        self._loop = loop

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """Subscribe to a topic and receive a queue for events."""
        # Auto-capture the running loop for threadsafe publishing
        if not self._loop:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
                
        if self._use_redis and not self._redis:
            await self._setup_redis()
            
        q = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subscribers[topic].add(q)
            logger.debug("New subscriber for topic: %s", topic)
        return q

    async def unsubscribe(self, topic: str, q: asyncio.Queue):
        """Remove a subscriber from a topic."""
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(q)
                logger.debug("Subscriber removed from topic: %s", topic)

    async def publish(self, topic: str, data: Any):
        """Publish an event to all subscribers (local and remote)."""
        # 1. Local delivery
        await self._publish_local(topic, data)
        
        # 2. Remote delivery via Redis (H-12)
        if self._use_redis:
            if not self._redis:
                await self._setup_redis()
            if self._redis:
                try:
                    payload = json.dumps(data)
                    await self._redis.publish(f"aura/events/{topic}", payload)
                except Exception as e:
                    logger.debug("AuraEventBus: Redis publish failed: %s", e)

    async def _publish_local(self, topic: str, data: Any):
        """Asynchronously publish an event to all local subscribers of a topic."""
        
        # --- 🛑 PREVENT EVENT ECHOES ---
        # If the data is a dict, track how many times it has bounced
        if isinstance(data, dict):
            bounce_count = data.get("_bounce_count", 0)
            if bounce_count > 3:
                logger.debug("Dropped event on topic %s - Max bounce depth reached.", topic)
                return
            data["_bounce_count"] = bounce_count + 1
        # -------------------------------

        async with self._lock:
            subscribers = list(self._subscribers.get(topic, []))
            # Also notify wildcard subscribers
            subscribers.extend(list(self._subscribers.get("*", [])))

        if not subscribers:
            return

        event = {"topic": topic, "data": data}
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Backpressure: drop oldest message
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    def publish_threadsafe(self, topic: str, data: Any):
        """Safely fire events from background threads to the main asyncio loop."""
        
        # 1. Try specified loop
        if self._loop and self._loop.is_running():
            try:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.publish(topic, data))
                )
                return
            except Exception:
                pass

        # 2. Try current running loop
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.publish(topic, data))
                return
        except RuntimeError:
            pass

        # 3. Last resort: Universal Discovery
        # If we have any running loop in any thread, try to find it.
        # Note: This is a bit of a hack but necessary for complex hybrid environments.
        try:
            for task in asyncio.all_tasks():
                loop = task.get_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.publish(topic, data), loop)
                    return
        except Exception:
            pass

        logger.error("No running event loop found for threadsafe publish on topic: %s", topic)


# Global singleton instance
_bus = AuraEventBus()


def get_event_bus():
    return _bus

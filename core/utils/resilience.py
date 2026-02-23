import asyncio
import logging
import threading
import time
from collections import deque
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

logger = logging.getLogger("Aura.Resilience")

T = TypeVar("T")

class CircuitState(Enum):
    CLOSED = "closed"      # Healthy
    OPEN = "open"          # Failing, blocked
    HALF_OPEN = "half_open" # Probing

class CircuitBreakerError(Exception):
    """Base exception for circuit breaker events."""

    pass

class CircuitBreakerOpenError(CircuitBreakerError):
    """Raised when the circuit is open and no fallback is available."""

    pass

class AsyncCircuitBreaker:
    """v6.0: Diamond-Strong Asynchronous Circuit Breaker.
    Thread-safe and optimized for asyncio workflows.
    """

    def __init__(
        self, 
        name: str, 
        failure_threshold: int = 5, 
        recovery_timeout: float = 60.0,
        success_threshold: int = 3,
        fallback: Optional[Callable] = None
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.fallback = fallback
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.successes = 0
        self.last_failure_time = 0.0
        
        # Use a double lock for hybrid thread/async safety
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    def _should_probe(self) -> bool:
        if self.state == CircuitState.OPEN:
            if (time.time() - self.last_failure_time) > self.recovery_timeout:
                return True
            return False
        return True

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an async function with circuit breaker protection."""
        fallback = self.fallback
        async with self._async_lock:
            if not self._should_probe():
                if fallback:
                    return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)
                raise CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN. Cooling down...")

            if self.state == CircuitState.OPEN:
                logger.info("Circuit '%s': Probing status (HALF-OPEN)", self.name)
                self.state = CircuitState.HALF_OPEN

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)
            
            async with self._async_lock:
                self._record_success()
            return result
        except Exception as e:
            async with self._async_lock:
                self._record_failure(e)
            
            if self.fallback:
                logger.warning("Circuit '%s' caught error: %s. Executing fallback.", self.name, e)
                return await self.fallback(*args, **kwargs) if asyncio.iscoroutinefunction(self.fallback) else self.fallback(*args, **kwargs)
            raise

    def _record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.successes += 1
            if self.successes >= self.success_threshold:
                logger.info("Circuit '%s': RECOVERED. State reset to CLOSED.", self.name)
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.successes = 0
        elif self.state == CircuitState.CLOSED:
            # Gradually decay failure count on success
            self.failures = max(0, self.failures - 1)

    def _record_failure(self, error: Exception):
        self.failures += 1
        self.last_failure_time = time.time()
        logger.warning("Circuit '%s': Failure detected (%s/%s). Error: %s", self.name, self.failures, self.failure_threshold, error)
        
        if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
            logger.error("Circuit '%s': TRIPPED. State set to OPEN for %ss.", self.name, self.recovery_timeout)
            self.state = CircuitState.OPEN
            self.successes = 0

class AdaptiveRateLimiter:
    """Sliding window rate limiter with adaptive backoff support.
    """
    DEFAULT_WINDOW = 60.0  # seconds

    def __init__(self, requests_per_minute: int = 60, window: float = DEFAULT_WINDOW):
        self.max_requests = requests_per_minute
        self.window = window
        self.requests = deque()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.time()
            # Clean old requests
            while self.requests and self.requests[0] < now - self.window:
                self.requests.popleft()
            
            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True
            return False

    def get_backoff(self) -> float:
        with self._lock:
            if not self.requests: return 0.0
            elapsed = time.time() - self.requests[0]
            return max(0.0, self.window - elapsed)

    def reset(self):
        """Clear all request history."""
        with self._lock:
            self.requests.clear()
            logger.info("Rate limiter reset.")

class BlockDetector:
    """Context manager to detect blocking operations in the asyncio event loop.
    """

    def __init__(self, name: str, threshold: float = 0.1):
        self.name = name
        self.threshold = threshold
        self._start_time = 0.0

    def __enter__(self):
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self._start_time
        if duration > self.threshold:
            logger.warning(
                f"🐢 BLOCKING DETECTED: Operation '{self.name}' took {duration:.4f}s "
                f"(Threshold: {self.threshold}s). Consider offloading to a thread."
            )

def resilient(component_name: str, retry: bool = True, circuit_breaker: bool = True, retry_attempts: int = 3, fallback_value: Any = None):
    """Diamond-Strong Resilience Decorator.
    Handles both async and sync functions. Spawns threads for sync blocking work.
    """
    def decorator(func: Callable):
        from functools import wraps
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Logic similar to infrastructure/resilience but using AsyncCircuitBreaker local logic
            # For brevity in this call, we rely on the execute() method of AsyncCircuitBreaker
            # but we need a registry or local breaker.
            
            # Use a simple naming-based breaker registry
            if not hasattr(resilient, "_breakers"):
                resilient._breakers = {}
            if component_name not in resilient._breakers:
                resilient._breakers[component_name] = AsyncCircuitBreaker(component_name)
            
            breaker = resilient._breakers[component_name]
            
            try:
                # Use a local lambda or partial to wrap the retry logic if needed
                async def _attempt():
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    else:
                        return await asyncio.to_thread(func, *args, **kwargs)

                if retry:
                    # Simple inline retry for now or use a utility
                    for i in range(retry_attempts):
                        try:
                            return await breaker.execute(_attempt)
                        except Exception as e:
                            if i == retry_attempts - 1: raise
                            await asyncio.sleep(0.5 * (2 ** i))
                else:
                    return await breaker.execute(_attempt)
            except Exception as e:
                if fallback_value is not None:
                    logger.warning("Resilience triggered for %s: %s. Returning fallback.", component_name, e)
                    return fallback_value
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            # For sync functions, we still return an async wrapper because 
            # the resilience layer (CircuitBreaker) is async.
            return async_wrapper

    return decorator

def resilient_call(breaker: AsyncCircuitBreaker):
    """Legacy compatibility shim."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.execute(func, *args, **kwargs)
        return wrapper
    return decorator

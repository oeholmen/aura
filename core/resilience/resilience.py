"""core/resilience.py
Advanced Resilience Engine with Service Level Gating and Fallback Chains.
"""
import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from infrastructure.resilience import CircuitBreaker, resilient

logger = logging.getLogger("Core.Resilience")

class ResilienceEngine:
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        # Default fallback chains for core capabilities
        self.fallback_chains = {
            "chat": ["ollama", "fallback_rule_based"],
            "vision": ["llava", "vision_unavailable"],
            "code_execution": ["docker_sandbox", "local_subprocess_blocked"]
        }
        self.service_health: Dict[str, bool] = {}

    def get_breaker(self, service_name: str) -> CircuitBreaker:
        if service_name not in self.breakers:
            self.breakers[service_name] = CircuitBreaker(
                failure_threshold=3, 
                recovery_timeout=60
            )
        return self.breakers[service_name]

    async def execute_with_fallback(self, capability: str, task: Dict, context: Dict) -> Any:
        """Executes a capability by trying providers in its fallback chain.
        """
        chain = self.fallback_chains.get(capability)
        if not chain:
            logger.error("ResilienceEngine: Unknown capability '%s', no fallback chain.", capability)
            return {"ok": False, "error": f"Unknown capability: {capability}"}
        
        last_error = None

        for provider in chain:
            breaker = self.get_breaker(provider)
            if not breaker.allow_request():
                logger.warning("ResilienceEngine: Provider '%s' skipped (Circuit Open)", provider)
                continue

            try:
                # Resolve provider to a skill or client
                # In a real system, this would interact with the registry/container
                result = await self._run_provider(provider, task, context)
                breaker.record_success()
                return result
            except Exception as e:
                logger.error("ResilienceEngine: Provider '%s' failed: %s", provider, e)
                breaker.record_failure()
                last_error = e

        logger.critical("ResilienceEngine: All providers for '%s' failed.", capability)
        return {"ok": False, "error": f"Total failure in {capability}: {last_error}"}

    async def _run_provider(self, provider: str, task: Dict, context: Dict) -> Any:
        """Dispatch to the appropriate provider/client."""
        # Resolve provider via container
        from core.container import get_container
        container = get_container()
        
        if provider == "ollama":
            client = container.get("llm_client") or container.get("cognitive_engine")
            if client and hasattr(client, 'think'):
                result = await client.think(task.get("prompt", ""), context)
                return {"ok": True, "result": result}
        elif provider == "fallback_rule_based":
            return {"ok": True, "result": "I'm having trouble with my reasoning right now. Let me try again."}
        elif provider.endswith("_unavailable"):
            return {"ok": False, "error": f"Capability unavailable: {provider}"}
        
        # Generic: try to find a matching skill
        skill = container.get(provider)
        if skill and hasattr(skill, 'execute'):
            return await skill.execute(task, context)
        
        raise RuntimeError(f"Provider '{provider}' not found or not implemented")

def resilient_service(service_name: str, fallback_val: Any = None):
    """Enhanced decorator that uses the ResilienceEngine logic.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # This would ideally pull the engine from a global container
            from core.container import get_container
            container = get_container()
            engine = container.get("resilience_engine")
            
            if not engine:
                # If no engine, fall back to basic circuit breaker logic
                return await func(*args, **kwargs)

            breaker = engine.get_breaker(service_name)
            if not breaker.allow_request():
                return fallback_val

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                logger.error("Resilient Service %s error: %s", service_name, e)
                return fallback_val
        return wrapper
    return decorator

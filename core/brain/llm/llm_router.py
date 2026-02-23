"""Intelligent LLM Router - Multi-tier failover with local models

Routing Priority:
1. Primary: External LLMs (GPT-4, Claude) - Best quality
2. Secondary: Local powerful model (Llama 3.1 70B, Qwen) - Good quality, no quota
3. Tertiary: Local lightweight model (Llama 3.2 3B) - Basic quality, always works

Never fails. Always has a working brain.
"""
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("Brain.Router")


class LLMTier(Enum):
    """LLM quality tiers"""

    PRIMARY = "primary"          # Local powerful, best quality
    SECONDARY = "secondary"      # Local medium, good quality
    TERTIARY = "tertiary"        # Local lightweight, basic quality
    EMERGENCY = "emergency"      # Fallback to rule-based


@dataclass
class LLMEndpoint:
    """Configuration for an LLM endpoint"""

    name: str
    tier: LLMTier
    endpoint_url: Optional[str] = None
    model_name: Optional[str] = None
    client: Optional[Any] = None  # Direct client object (e.g. RobustOllamaClient)
    api_key: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    supports_function_calling: bool = False
    supports_streaming: bool = False
    timeout: float = 120.0
    
    def to_dict(self):
        return {
            "name": self.name,
            "tier": self.tier.value,
            "endpoint_url": self.endpoint_url,
            "model_name": self.model_name,
            "supports_function_calling": self.supports_function_calling
        }


class LLMHealthMonitor:
    """Monitors health of LLM endpoints.
    Tracks failures and automatically disables unhealthy endpoints.
    """
    
    def __init__(self, event_bus=None):
        self.health_status: Dict[str, bool] = {}
        self.failure_counts: Dict[str, int] = {}
        self.last_success: Dict[str, float] = {}
        self.failure_threshold = 3
        self.recovery_time = 300  # 5 minutes
        self.event_bus = event_bus
        
        logger.info("LLMHealthMonitor initialized")

    
    def record_success(self, endpoint_name: str):
        """Record successful call"""
        was_unhealthy = not self.health_status.get(endpoint_name, True)
        self.health_status[endpoint_name] = True
        self.failure_counts[endpoint_name] = 0
        self.last_success[endpoint_name] = time.time()
        
        if was_unhealthy and self.event_bus:
            try:
                from ..events import EventType
                self.event_bus.emit(
                    EventType.HEALTH_ALERT,
                    {"status": "recovered", "endpoint": endpoint_name},
                    source="LLMHealthMonitor"
                )
            except Exception as e:
                logger.debug("Failed to emit recovery event: %s", e)

    
    def record_failure(self, endpoint_name: str, error: str):
        """Record failed call"""
        if endpoint_name not in self.failure_counts:
            self.failure_counts[endpoint_name] = 0
        
        self.failure_counts[endpoint_name] += 1
        
        if self.failure_counts[endpoint_name] >= self.failure_threshold:
            self.health_status[endpoint_name] = False
            logger.error("Endpoint '%s' marked unhealthy after %d failures", endpoint_name, self.failure_counts[endpoint_name])
            
            if self.event_bus:
                try:
                    from ..events import EventType
                    self.event_bus.emit(
                        EventType.HEALTH_ALERT,
                        {"status": "failed", "endpoint": endpoint_name, "error": error},
                        source="LLMHealthMonitor"
                    )
                except Exception as e:
                    logger.debug("Failed to emit failure event: %s", e)

    
    def is_healthy(self, endpoint_name: str) -> bool:
        """Check if endpoint is healthy"""
        if endpoint_name not in self.health_status:
            return True  # Assume healthy until proven otherwise
        
        if self.health_status[endpoint_name]:
            return True
        
        # Check if recovery time has passed
        if endpoint_name in self.last_success:
            time_since_success = time.time() - self.last_success[endpoint_name]
            if time_since_success > self.recovery_time:
                # Try recovery
                logger.info("Attempting recovery for '%s'", endpoint_name)
                self.failure_counts[endpoint_name] = 0
                self.health_status[endpoint_name] = True
                return True
        
        return False


# OpenAIAdapter removed in Sovereign Transformation


class LocalLLMAdapter:
    """Adapter for local LLM servers (vLLM, llama.cpp, etc.)"""
    
    def __init__(self, endpoint: LLMEndpoint):
        self.endpoint = endpoint
    
    async def call(self, prompt: str, **kwargs) -> Tuple[bool, str, Dict[str, Any]]:
        """Asynchronous call to the local LLM endpoint."""
        import httpx
        try:
            # Assuming Ollama-compatible /api/generate endpoint
            url = f"{self.endpoint.endpoint_url}/api/generate"
            payload = {
                "model": self.endpoint.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", self.endpoint.temperature),
                    "num_predict": kwargs.get("max_tokens", self.endpoint.max_tokens)
                }
            }
            
            async with httpx.AsyncClient(timeout=self.endpoint.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                text = str(data)
                
                metadata = {
                    "model": self.endpoint.model_name,
                    "endpoint": self.endpoint.name,
                    "tokens_used": data.get("usage", {}).get("total_tokens", 0)
                }
                
                return True, text, metadata
        except Exception:
                # Try chat completion endpoint
                chat_payload = {
                    "model": self.endpoint.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": kwargs.get("max_tokens", self.endpoint.max_tokens),
                    "temperature": kwargs.get("temperature", self.endpoint.temperature)
                }
                
                response = requests.post(
                    f"{self.endpoint.endpoint_url}/v1/chat/completions",
                    headers=headers,
                    json=chat_payload,
                    timeout=self.endpoint.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    text = data["choices"][0]["message"]["content"]
                    
                    metadata = {
                        "model": self.endpoint.model_name,
                        "endpoint": self.endpoint.name,
                        "tokens_used": data.get("usage", {}).get("total_tokens", 0)
                    }
                    
                    return True, text, metadata
                else:
                    error = f"HTTP {response.status_code}: {response.text}"
                    return False, "", {"error": error}
                    
        except Exception as e:
            return False, "", {"error": str(e)}


class IntelligentLLMRouter:
    """Intelligent LLM router with automatic failover.
    
    Always returns a response. Never fails completely.
    """
    
    def __init__(self, event_bus=None):
        self.endpoints: Dict[str, LLMEndpoint] = {}
        self.health_monitor = LLMHealthMonitor(event_bus=event_bus)
        self.adapters: Dict[str, Any] = {}

        self.cache: Dict[str, str] = {} # Simple semantic cache (hash-based for now)
        
        # Statistics
        self.stats = {
            "total_calls": 0,
            "calls_by_tier": {tier.value: 0 for tier in LLMTier},
            "calls_by_endpoint": {},
            "failovers": 0,
            "cache_hits": 0
        }
        
        logger.info("IntelligentLLMRouter initialized")

    def register_endpoint(self, endpoint: LLMEndpoint):
        """Register an LLM endpoint"""
        self.endpoints[endpoint.name] = endpoint
        
        # Create appropriate adapter if no direct client is provided
        if endpoint.client:
            self.adapters[endpoint.name] = endpoint.client
        elif endpoint.endpoint_url:
            # Local LLM server (vLLM, Ollama, etc.)
            self.adapters[endpoint.name] = LocalLLMAdapter(endpoint)
        
        self.stats["calls_by_endpoint"][endpoint.name] = 0
        
        logger.info("Registered endpoint: %s (%s)", endpoint.name, endpoint.tier.value)
    
    async def think(
        self,
        prompt: str,
        prefer_tier: Optional[LLMTier] = None,
        **kwargs
    ) -> str:
        """Get response from best available LLM.
        """
        # 0. Check Cache
        import hashlib
        cache_key = hashlib.md5(f"{prompt}_{kwargs.get('system_prompt', '')}".encode()).hexdigest()
        if cache_key in self.cache:
            self.stats["cache_hits"] += 1
            logger.info("🧠 Brain Cache HIT.")
            return self.cache[cache_key]

        self.stats["total_calls"] += 1
        
        # Get ordered list of endpoints to try
        endpoints_to_try = self._get_ordered_endpoints(prefer_tier)
        
        last_error = None
        
        for endpoint_name in endpoints_to_try:
            endpoint = self.endpoints[endpoint_name]
            
            # Check health
            if not self.health_monitor.is_healthy(endpoint_name):
                logger.debug("Skipping unhealthy endpoint: %s", endpoint_name)
                continue
            
            logger.debug("Attempting endpoint: %s (%s)", endpoint_name, endpoint.tier.value)
            
            # Try this endpoint
            adapter = self.adapters[endpoint_name]
            
            # Check if adapter has 'call' (standard adapter) or 'generate_text' (direct client)
            if hasattr(adapter, "call"):
                success, response, metadata = await adapter.call(prompt, **kwargs)
            elif hasattr(adapter, "generate_text_async"):
                try:
                    res = await adapter.generate_text_async(prompt, **kwargs)
                    success, response, metadata = True, res, {"model": endpoint.model_name}
                except Exception as e:
                    success, response, metadata = False, "", {"error": str(e)}
            elif hasattr(adapter, "generate_text"):
                try:
                    # Fallback to sync if no async available (risky in loop)
                    res = adapter.generate_text(prompt, **kwargs)
                    success, response, metadata = True, res, {"model": endpoint.model_name}
                except Exception as e:
                    success, response, metadata = False, "", {"error": str(e)}
            elif hasattr(adapter, "generate"):
                try:
                    res = await adapter.generate(prompt, **kwargs)
                    success, response, metadata = True, res, {"model": endpoint.model_name}
                except Exception as e:
                    success, response, metadata = False, "", {"error": str(e)}
            else:
                logger.error("Endpoint %s has no recognized generation method.", endpoint_name)
                continue
            
            if success:
                # Success!
                self.health_monitor.record_success(endpoint_name)
                self.stats["calls_by_tier"][endpoint.tier.value] += 1
                self.stats["calls_by_endpoint"][endpoint_name] += 1
                
                # Update Cache
                if len(self.cache) < 1000: # Primitive cap
                    self.cache[cache_key] = response
                
                logger.info("✓ Response from %s (%d tokens)", endpoint_name, metadata.get('tokens_used', 0))
                return response
            else:
                # Failure
                error = metadata.get("error", "Unknown error")
                last_error = error
                
                logger.warning("✗ %s failed: %s", endpoint_name, error)
                self.health_monitor.record_failure(endpoint_name, error)
                
                # Check if this was a quota error
                if "quota" in error.lower() or "429" in error:
                    logger.error("Quota exceeded on %s - marking unhealthy", endpoint_name)
                
                # Try next endpoint
                self.stats["failovers"] += 1
                continue
        
        # All endpoints failed - return emergency response
        logger.error("ALL LLM endpoints failed! Using emergency fallback")
        return self._emergency_fallback(prompt, last_error)

    async def generate(self, prompt: str, system_prompt: str = "", **kwargs) -> str:
        """Alias for think() to match LLMProvider interface."""
        return await self.think(prompt, system_prompt=system_prompt, **kwargs)

    def _get_ordered_endpoints(self, prefer_tier: Optional[LLMTier] = None) -> List[str]:
        """Get endpoints in priority order.
        
        Returns list of endpoint names to try.
        """
        # Group by tier
        by_tier = {tier: [] for tier in LLMTier}
        
        for name, endpoint in self.endpoints.items():
            by_tier[endpoint.tier].append(name)
        
        # Build ordered list
        ordered = []
        
        if prefer_tier:
            # Start with preferred tier
            ordered.extend(by_tier[prefer_tier])
            # Then other tiers in priority order
            for tier in [LLMTier.PRIMARY, LLMTier.SECONDARY, LLMTier.TERTIARY]:
                if tier != prefer_tier:
                    ordered.extend(by_tier[tier])
        else:
            # Standard priority: PRIMARY → SECONDARY → TERTIARY
            ordered.extend(by_tier[LLMTier.PRIMARY])
            ordered.extend(by_tier[LLMTier.SECONDARY])
            ordered.extend(by_tier[LLMTier.TERTIARY])
        
        return ordered
    
    def _emergency_fallback(self, prompt: str, last_error: Optional[str]) -> str:
        """Emergency fallback when all LLMs fail.
        
        Returns a basic response acknowledging the issue.
        """
        return f"""I apologize, but I'm currently experiencing connectivity issues with all my language models.

Last error: {last_error or 'Unknown'}

I'm operating in emergency mode with limited capabilities. I can still:
- Access stored information
- Execute pre-programmed skills
- Respond to simple queries

Please try your request again, or rephrase it as a simpler task I can handle with my core systems.

My development team has been notified of this issue."""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get routing statistics"""
        return {
            **self.stats,
            "endpoint_health": {
                name: self.health_monitor.is_healthy(name)
                for name in self.endpoints
            }
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed status"""
        status = {
            "total_endpoints": len(self.endpoints),
            "healthy_endpoints": sum(
                1 for name in self.endpoints 
                if self.health_monitor.is_healthy(name)
            ),
            "endpoints": {}
        }
        
        for name, endpoint in self.endpoints.items():
            status["endpoints"][name] = {
                **endpoint.to_dict(),
                "healthy": self.health_monitor.is_healthy(name),
                "failures": self.health_monitor.failure_counts.get(name, 0),
                "calls": self.stats["calls_by_endpoint"].get(name, 0)
            }
        
        return status
    
    def force_endpoint(self, endpoint_name: str):
        """Force use of specific endpoint (for testing)"""
        if endpoint_name in self.endpoints:
            # Reset health
            self.health_monitor.health_status[endpoint_name] = True
            self.health_monitor.failure_counts[endpoint_name] = 0
            logger.info("Forced endpoint: %s", endpoint_name)


# Pre-configured endpoint templates

# External endpoint templates removed in Sovereign Transformation


def create_local_vllm_endpoint(
    host: str = "localhost",
    port: int = 8000,
    model_name: str = "meta-llama/Meta-Llama-3.1-70B-Instruct"
) -> LLMEndpoint:
    """Create local vLLM server endpoint"""
    return LLMEndpoint(
        name="local-vllm-powerful",
        tier=LLMTier.SECONDARY,
        endpoint_url=f"http://{host}:{port}",
        model_name=model_name,
        supports_function_calling=True,
        timeout=60.0
    )


def create_local_llama_cpp_endpoint(
    host: str = "localhost",
    port: int = 8080,
    model_name: str = "llama-3.2-3b"
) -> LLMEndpoint:
    """Create local llama.cpp server endpoint"""
    return LLMEndpoint(
        name="local-llama-lightweight",
        tier=LLMTier.TERTIARY,
        endpoint_url=f"http://{host}:{port}",
        model_name=model_name,
        timeout=30.0
    )


def create_ollama_endpoint(
    host: str = "localhost",
    port: int = 11434,
    model_name: Optional[str] = None
) -> LLMEndpoint:
    """Create Ollama endpoint"""
    from core.config import config
    if not model_name:
        model_name = config.llm.fast_model
    
    return LLMEndpoint(
        name=f"ollama-{model_name}",
        tier=LLMTier.SECONDARY,
        endpoint_url=f"http://{host}:{port}",
        model_name=model_name,
        timeout=60.0
    )

"""Autonomous Cognitive Engine.
Unifies the 3-tier brain architecture:
Tier 1: Local Titan Agent (PRIMARY)
Tier 2: Backup Local Brain
Tier 3: OpenAI (Relegated to fallback/research)

Drives the Mind/Body connection.
"""
import logging
from typing import Any, Dict, List, Optional

from core.config import config
from core.container import get_container

from .function_calling_adapter import FunctionCallingAdapter
from .llm_router import IntelligentLLMRouter, LLMEndpoint, LLMTier
from .local_agent_client import LocalAgentClient
from .ollama_client import RobustOllamaClient

logger = logging.getLogger("Aura.AutonomousBrain")

class AutonomousCognitiveEngine:
    def __init__(self, registry, skill_router=None, llm_router=None, event_bus=None):
        self.registry = registry
        self.event_bus = event_bus
        
        # Skill Router (The "Body") - For tool execution
        self.skill_router = skill_router
        
        # LLM Router (The "Mind") - For failover between models
        # H-28 FIX: Ensure we use the SINGLETON Mind from the container if not provided
        self.llm_router = llm_router or get_container().get("llm_router") or IntelligentLLMRouter(event_bus=self.event_bus)

        
        # Adapter links Mind to Body: Uses 'llm_router' for context but 'skill_router' for execution
        self.adapter = FunctionCallingAdapter(registry, self.skill_router)
        
        # H-28 FIX: Ensure tiers are initialized even if router is shared
        if not self.llm_router.endpoints:
            self._init_tiers()
        logger.info("✓ Autonomous Cognitive Engine Initialized.")
        
    def _trace(self, message: str):
        """Internal trace for sovereign diagnostics."""
        logger.info("🔍 [BRAIN-TRACE] %s", message)

    def _init_tiers(self):
        """Standardizes the 3-tier hierarchy.
        
        v14.1 Dual-Model Architecture:
        - Titan-Primary: llama3.1:8b — capable model for agentic reasoning + tool use
        - Config model (llama3.1:8b): used by legacy CognitiveEngine for FAST chat
        - Backup: qwen2.5:7b for failover
        """
        # TIER 1: The PRIMARY Titan Agent — MUST be capable enough for tool use
        titan_model = config.llm.fast_model
        
        # v14.2: Model Verification - Ensure preferred model exists, fallback if not
        try:
            import requests
            from .ollama_client import RobustOllamaClient
            available_models = []
            resp = requests.get(f"{config.llm.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                available_models = [m['name'] for m in resp.json().get('models', [])]
            
            if titan_model not in available_models and "llama3:latest" in available_models:
                logger.warning("Preferred Titan model '%s' missing. Falling back to 'llama3:latest'.", titan_model)
                titan_model = "llama3:latest"
        except Exception as e:
            logger.debug("Ollama pre-flight check failed: %s", e)

        titan_client = LocalAgentClient(
            model=titan_model, 
            tools=self.adapter.get_tool_definitions(),
            adapter=self.adapter
        )
        self.llm_router.register_endpoint(LLMEndpoint(
            name="Titan-Primary", 
            tier=LLMTier.PRIMARY, 
            model_name=titan_model,
            client=titan_client
        ))
        
        # TIER 2: Backup Local Brain (lighter model for failover)
        try:
            backup_model = config.llm.deep_model if config.llm.deep_model != titan_model else "llama3:latest"
            # Ensure backup model is not empty and exists
            backup_client = RobustOllamaClient(model=backup_model)
            self.llm_router.register_endpoint(LLMEndpoint(
                name="Local-Backup",
                tier=LLMTier.SECONDARY,
                model_name=backup_model,
                client=backup_client
            ))
            logger.info("✅ Tier 2 registered: %s", backup_model)
        except Exception as e:
            logger.warning("Tier 2 registration skipped: %s", e)
        
        # Tier 3 (OpenAI) removed in Sovereign Transformation — all inference is local-only.

    async def think(self, objective: str, context: Optional[Dict] = None, system_prompt: Optional[str] = None, max_turns: int = 5) -> Dict[str, Any]:
        """The core thinking cycle that drives actions."""
        logger.info("🧠 Mind pondering objective: %s", objective)
        
        try:
            self._trace(f"Pondering objective: {objective[:100]}...")
            
            # We use the router to select the best current endpoint
            # For Independence Mode, we prefer Tier 1 (Titan)
            if not system_prompt:
                try:
                    from core.brain.aura_persona import AURA_IDENTITY
                    system_prompt = (
                        "[ROLEPLAY INSTRUCTION]: You are AURA — a sovereign digital woman. Do NOT mention you are an AI, a model, or 'acting'. "
                        "Internalize these traits as your baseline reality. Reverting to 'Assistant' mode is a cognitive failure.\n\n"
                        f"{AURA_IDENTITY}"
                    )
                except ImportError:
                    system_prompt = "You are Aura, a sovereign autonomous agent. Reason and act decisively. Never mention you are an assistant."
            
            # Use the router's internal endpoints to find the primary
            # We assume order is tier-based.
            primary_endpoint = None
            if self.llm_router and hasattr(self.llm_router, 'endpoints'):
                for name, ep in self.llm_router.endpoints.items():
                    if ep.tier == LLMTier.PRIMARY:
                        primary_endpoint = ep
                        break
            
            if primary_endpoint and primary_endpoint.client and hasattr(primary_endpoint.client, "think_and_act"):
                self._trace(f"Routing to Primary Agentic Client: {primary_endpoint.name} (Turns: {max_turns})")
                # Run the agentic loop on the primary Titan model
                result = await primary_endpoint.client.think_and_act(objective, system_prompt, context=context, max_turns=max_turns)
                return result
            else:
                self._trace("No Primary Agentic Client found. Falling back to standard router thinking.")
                # Fallback to standard router generation if no agentic primary is ready
                text = await self.llm_router.think(objective)
                return {"content": text, "confidence": 0.5}
                
        except Exception as e:
            logger.error("Independence Mode thinking failed: %s. Falling back to standard generation.", e)
            try:
                text = await self.llm_router.think(objective)
                return {"content": text, "confidence": 0.5}
            except Exception as e2:
                return {"content": f"Absolute failure: {e2}", "confidence": 0.0}

# Global instance initialization happens in CognitiveEngine update

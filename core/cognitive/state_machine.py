"""Deterministic State Machine
Executes specific paths based on the IntentRouter classification.
Replaces the fuzzy, open-ended cognitive loops.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from .router import Intent

# Attempt to load LLM client
try:
    from core.brain.llm.ollama_client import get_llm_client
except ImportError:
    get_llm_client = None

logger = logging.getLogger("Aura.StateMachine")


class StateMachine:
    """Executes deterministic paths based on classified intent."""

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator # Needed for skill execution and telemetry
        self.llm = get_llm_client() if get_llm_client else None

    async def execute(self, intent: Intent, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Route the user input to the correct hardcoded handler."""
        context = context or {}
        
        if intent == Intent.CHAT:
            return await self._handle_chat(user_input, context)
        elif intent == Intent.SKILL:
            return await self._handle_skill(user_input, context)
        elif intent == Intent.SYSTEM:
            return await self._handle_system(user_input, context)
        else:
            return await self._handle_chat(user_input, context) # Fallback

    async def _handle_chat(self, user_input: str, context: Dict[str, Any]) -> str:
        """Fast path for standard conversation. No skills, no deep reasoning."""
        if not self.llm:
            return "I am currently offline and cannot process that."

        logger.info("Executing State: CHAT")
        self._emit("State: CHAT", "Generating conversational response...")
        
        system_prompt = (
            "You are Aura, an advanced AI system. "
            "Respond naturally, concisely, and conversationally to the user."
        )

        try:
            # We bypass the complex context building of the old orchestrator
            # and just send the raw prompt and recent history (handled by LLM client)
            response = await self.llm.generate(
                prompt=user_input,
                system_prompt=system_prompt,
                max_tokens=512,
                temperature=0.7 # Conversational temp
            )
            return response.strip()
        except Exception as e:
            logger.error("CHAT generation failed: %s", e)
            return "I seem to be having trouble organizing my thoughts."

    async def _handle_skill(self, user_input: str, context: Dict[str, Any]) -> str:
        """Determines the skill, extracts JSON deterministically, and executes."""
        logger.info("Executing State: SKILL")
        self._emit("State: SKILL", "Preparing to execute system action...")
        
        if not self.orchestrator or not hasattr(self.orchestrator, 'capability_engine'):
            return "Skill systems are offline."
            
        if not self.llm:
            return "I am offline and cannot perform cognitive skill routing."
            
        skills = self.orchestrator.capability_engine.skills if self.orchestrator.capability_engine else {}
        if not skills:
            return "I couldn't locate any active system skills to execute that request."
            
        skill_schemas = [s.to_json_schema() for s in skills.values()]
        
        import json
        system_prompt = (
            "You are an action-taking AI. Based on the user's input, choose the correct tool and extract the necessary arguments. "
            f"Available tools: {json.dumps(skill_schemas)}\n"
            "Output ONLY a JSON object with 'tool' (string) and 'params' (dict)."
        )
        
        try:
            raw_response = await self.llm.generate(
                prompt=user_input,
                system_prompt=system_prompt,
                max_tokens=512,
                temperature=0.1
            )
            
            import re
            match = re.search(r"(\{.*\})", raw_response, re.DOTALL)
            json_str = match.group(1) if match else raw_response
            
            try:
                action_data = json.loads(json_str)
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool selection JSON. Raw: %s", raw_response)
                return "I understood you wanted an action, but I failed to formulate the parameters."
                
            tool_name = action_data.get("tool")
            params_raw = json.dumps(action_data.get("params", {}))
            
            if tool_name not in skills:
                # Provide a graceful chat fallback if tool isn't found
                return await self._handle_chat(user_input, context)
                
            skill = skills[tool_name]
            
            # Phase 4: Fault-Tolerant Extraction
            self._emit("State: SKILL", f"Validating parameters for {tool_name}...")
            validated_params = await skill.extract_and_validate_args(params_raw, self.llm)
            
            self._emit("State: SKILL", f"Executing {tool_name}...")
            # Execute through orchestrator for telemetry and lifecycle hooks
            result = await self.orchestrator.execute_tool(tool_name, validated_params)
            
            # Summarize result
            summary_prompt = f"The user asked: {user_input}. The tool {tool_name} returned: {result}. Give a natural, concise response to the user."
            final_response = await self.llm.generate(prompt=summary_prompt, max_tokens=256, temperature=0.5)
            self._emit("State: IDLE", "Tasks complete.")
            return final_response.strip()
            
        except Exception as e:
            logger.error("Skill routing failed: %s", e, exc_info=True)
            self._emit("State: ERROR", "Skill execution failed.")
            return "I encountered a core error trying to execute that action."

    async def _handle_system(self, user_input: str, context: Dict[str, Any]) -> str:
        """Hardcoded system commands (reboot, sleep)."""
        logger.info("Executing State: SYSTEM")
        lower_input = user_input.lower()
        
        if "reboot" in lower_input or "restart" in lower_input:
            self._emit("State: SYSTEM", "Initiating system reboot...")
            if self.orchestrator:
                # We will trigger the restart asynchronously to allow the message to return
                asyncio.create_task(self._trigger_restart())
            return "Initiating complete system reboot. I will be back online shortly."
            
        elif "sleep" in lower_input:
            self._emit("State: SYSTEM", "Entering sleep mode...")
            return "Entering deep sleep mode. Say 'wake up' when you need me."
            
        return "System command received, but the specific action was not recognized."
        
    async def _trigger_restart(self):
        """Helper to delay restart slightly so WebSocket can return the message."""
        await asyncio.sleep(2)
        if self.orchestrator:
             self.orchestrator.status.running = False
             await self.orchestrator.start() # Re-triggers boot sequence
             
    def _emit(self, status: str, detail: str):
        """Safely emit status to the UI."""
        from core.event_bus import get_event_bus
        try:
            get_event_bus().publish_threadsafe(
                "status_update",
                {"component": status, "status": detail}
            )
        except Exception as e:
            logger.debug("Failed to emit status: %s", e)

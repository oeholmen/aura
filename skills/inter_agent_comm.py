import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from infrastructure import BaseSkill

# Configure logger
logger = logging.getLogger("Skills.InterAgent")

class InterAgentCommSkill(BaseSkill):
    """Skill to facilitate communication with external agents (e.g., Gemini, ChatGPT).
    v3.4 Patch: Uses mock 'conversation_loop' if needed.
    """
    
    name = "inter_agent_comm"
    description = "Send a message to an external agent (Gemini, etc) to request assistance."

    def __init__(self):
        # Ensure we have a place to store these outbound messages
        self.comm_log_path = Path("data/comm_logs.jsonl")
        self.comm_log_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("✅ InterAgentComm initialized (v3.4 Patch Applied - No legacy dependencies)")

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the communication request (Async)."""
        params = goal.get("params", {}) if "params" in goal else goal
        agent_name = params.get("agent_name") or params.get("recipient")
        message = params.get("message")
        
        if not agent_name or not message:
            return {"ok": False, "error": "Missing agent_name or message in params"}
        try:
            timestamp = time.time()
            logger.info("📡 Transmitting to %s: %s...", agent_name, message[:50])

            # 1. Log the outbound request
            payload = {
                "timestamp": timestamp,
                "direction": "outbound",
                "target": agent_name,
                "content": message,
                "context": context
            }
            
            await asyncio.to_thread(self._log_communication, payload)

            # 2. v13: Honest about capabilities — no real API hook exists yet
            logger.warning("Inter-agent comm: No real API connection to %s. Message logged only.", agent_name)

            return {
                "ok": False,
                "status": "not_connected",
                "message": f"Message to {agent_name} was logged locally but could not be delivered — no API integration configured yet.",
                "details": {
                    "target": agent_name,
                    "timestamp": timestamp,
                    "logged": True
                }
            }

        except Exception as e:
            logger.error("Inter-agent comm failed: %s", e)
            return {
                "ok": False,
                "error": str(e)
            }

    def _log_communication(self, data: Dict[str, Any]):
        """Append communication record to log file"""
        try:
            with open(self.comm_log_path, 'a') as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            logger.error("Failed to write comm log: %s", e)

import logging
import os
from typing import Any, Dict

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.personality_skill")


class PersonalitySkill(BaseSkill):
    name = "personality"
    description = "Manage and query Aura's active persona (set/list/get)."
    inputs = {
        "action": "set | get | list | speak",
        "persona": "(optional) persona id to set",
        "text": "(optional) text to speak as persona"
    }

    def __init__(self):
        self.logger = logging.getLogger("Skills.personality")
        # Lazy-import persona adapter
        try:
            from core.brain.persona_adapter import PersonaAdapter
            self.adapter = PersonaAdapter()
        except Exception as e:
            self.logger.error("Failed to load PersonaAdapter: %s", e)
            self.adapter = None

    def match(self, goal: Dict[str, Any]) -> bool:
        obj = goal.get("objective", "").lower()
        return "persona" in obj or "speak as" in obj or "set persona" in obj

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.adapter:
            return {"ok": False, "error": "Persona system not available"}

        action = params.get("action") or params.get("operation")
        persona = params.get("persona")
        text = params.get("text")

        if action == "list":
            return {"ok": True, "personas": self.adapter.list_personas()}

        if action == "get":
            active = self.adapter.get_active()
            return {"ok": True, "active": active}

        if action == "set":
            if not persona:
                return {"ok": False, "error": "Missing persona name"}
            ok = self.adapter.set_persona(persona)
            return {"ok": ok, "persona": persona}

        if action == "speak":
            if not text:
                return {"ok": False, "error": "Missing text to speak"}
            active = self.adapter.get_active()
            if not active:
                return {"ok": False, "error": "No active persona set"}
            styled = self.adapter.apply_style(text)
            return {"ok": True, "text": styled}

        return {"ok": False, "error": "Unknown action"}

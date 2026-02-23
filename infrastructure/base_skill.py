"""infrastructure/base_skill.py
Base skill contract for the Aura Cortex system.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseSkill(ABC):
    """Contract for all Skills.
    Every skill must define its metadata and implement execute().
    """

    name: str = "unknown_skill"
    description: str = "No description provided."
    inputs: Dict[str, str] = {}
    output: str = "Result string or dict"
    aliases: List[str] = []

    def match(self, goal: Dict[str, Any]) -> bool:
        """Default matching logic.
        """
        obj = goal.get("objective", "")
        return self.name in str(obj)

    @abstractmethod
    def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the skill."""
        pass

    async def extract_and_validate_args(self, raw_input: str, llm_client=None) -> Dict[str, Any]:
        """Fault-tolerant JSON extraction and schema validation.
        Phase 4: Automatic Schema Recovery Loops.
        """
        import json
        import re
        import logging
        logger = logging.getLogger("Aura.Skills")
        
        extracted = {}
        # 1. Broad extraction (grab anything that looks like JSON)
        match = re.search(r"(\{.*\})", raw_input, re.DOTALL)
        json_str = match.group(1) if match else raw_input
        
        try:
            extracted = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Skill %s JSON decode failed: %s. Attempting LLM recovery...", self.name, e)
            if llm_client and hasattr(llm_client, 'generate_text_async'):
                # 2. Recovery Loop via LLM
                prompt = f"Extract a valid JSON object matching this schema {json.dumps(self.to_json_schema())} from this corrupted input: {raw_input}. Output ONLY JSON."
                try:
                    recovery_raw = await llm_client.generate_text_async(prompt, model="llama3")
                    r_match = re.search(r"(\{.*\})", recovery_raw, re.DOTALL)
                    r_str = r_match.group(1) if r_match else recovery_raw
                    extracted = json.loads(r_str)
                    logger.info("Skill %s successfully recovered schema.", self.name)
                except Exception as r_e:
                    logger.error("Skill %s LLM recovery failed: %s", self.name, r_e)
                    raise ValueError(f"Could not parse valid arguments for {self.name}: {r_e}") from e
            else:
                logger.error("Skill %s recovery failed: No LLM client.", self.name)
                raise ValueError(f"Invalid JSON for {self.name} and no recovery client available") from e
                
        # 3. Validation
        missing = [key for key in self.inputs.keys() if key not in extracted]
        if missing:
            logger.warning("Skill %s missing required keys: %s", self.name, missing)
            
        return extracted

    def to_json_schema(self) -> Dict[str, Any]:
        """Returns the JSON schema representation of the skill for LLM tool calling.
        """
        properties = {}
        required = []
        
        for name, desc in self.inputs.items():
            properties[name] = {
                "type": "string",
                "description": desc
            }
            required.append(name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }

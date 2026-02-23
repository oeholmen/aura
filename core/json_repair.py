import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger("Kernel.JSONRepair")

class SelfHealingJSON:
    """Robust JSON Parser (The 'Optimizer').
    Pipeline: Standard -> Regex Heuristics -> LLM Reflection.
    """

    def __init__(self, brain=None):
        self.brain = brain # Optional: Link to cognitive engine for Tier 3 repair

    async def parse(self, raw_text: str) -> Dict[str, Any]:
        """Attempt to parse JSON from potentially malformed LLM output."""
        if not raw_text:
            return {}
            
        # Tier 0: Clean markdown code blocks
        clean_text = self._strip_markdown(raw_text)
        
        # Tier 1: Standard Parse
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            logger.warning("JSON Decode Error. Attempting Tier 2 (Heuristics)...")
            
        # Tier 2: Heuristic Repair
        try:
            fixed_text = self._heuristic_repair(clean_text)
            return json.loads(fixed_text)
        except json.JSONDecodeError:
            logger.warning("Heuristics failed. Attempting Tier 3 (LLM Reflection)...")
            
        # Tier 3: LLM Reflection (if Brain available)
        if self.brain:
            try:
                return await self._llm_repair(clean_text)
            except Exception as e:
                logger.error("Tier 3 Repair failed: %s", e)
        
        # Final Failure
        logger.error("All JSON repair strategies failed.")
        return {}

    def _strip_markdown(self, text: str) -> str:
        """Remove ```json ... ``` fences with robust regex."""
        # Use regex to find content between fences, or just strip if no fences
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Fallback: if it contains fences but re failed to match properly
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"```$", "", text)
        return text.strip()

    def _heuristic_repair(self, text: str) -> str:
        """Apply regex fixes for common LLM mistakes."""
        # Fix trailing commas in objects/lists: , } -> }
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        
        # Fix missing quotes around keys (simple cases)
        # { key: "value" } -> { "key": "value" }
        # Look for word characters followed by colon, not in quotes
        # This is risky, simplified for now
        # text = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)(\s*:)', r'\1"\2"\3', text)
        
        return text

    async def _llm_repair(self, broken_json: str) -> Dict[str, Any]:
        """Ask the Brain to fix it."""
        prompt = (
            f"SYSTEM_ALERT: You generated invalid JSON. Fix it.\n"
            f"BROKEN_JSON:\n{broken_json}\n\n"
            "INSTRUCTIONS: Output ONLY the valid JSON. No markdown, no talk."
        )
        # We assume brain.think returns text. We assume it might still be markdown wrapped.
        thought = await self.brain.think(prompt)
        response = thought.content if hasattr(thought, 'content') else str(thought)
        
        # Recurse (carefully, depth 1 implicit here as we call parse again? No, direct load)
        # Let's clean markdown again just in case
        clean_response = self._strip_markdown(response)
        return json.loads(clean_response)

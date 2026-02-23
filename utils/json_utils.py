import json
import re
import logging
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("Utils.JSON")

def extract_json(text: Union[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Robustly extract JSON from a string, handling markdown code blocks,
    surrounding text, and common LLM formatting issues.
    """
    # --- 🛑 PHASE 19.3: STALLING PHRASE TRAP ---
    if "Processing deeper reflections" in text or text.strip() == "":
        logger.warning("Caught non-JSON cognitive stalling phrase. Rejecting immediately.")
        return None 
    # ------------------------------------------

    # 1. Try simple parse first (fast path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Extract from markdown code blocks
    pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to fix common issues if needed, but for now just log
            pass
            
    logger.warning(f"Failed to extract JSON from text: {text[:100]}...")
    return None

def validate_with_schema(data: Any, schema: Dict[str, Any]) -> bool:
    """
    Very basic JSON schema validation. 
    In a full system, this would use 'jsonschema' library.
    For Aura's sovereign needs, we implement a lightweight recursive checker.
    """
    if not isinstance(data, dict) and not isinstance(data, list):
        return False
        
    # If schema is just a type hint (Ollama 'format' style)
    if isinstance(schema, str):
        if schema == "json": return isinstance(data, (dict, list))
        return True
        
    # Basic structural check
    if "type" in schema:
        expected_type = schema["type"]
        if expected_type == "object" and not isinstance(data, dict): return False
        if expected_type == "array" and not isinstance(data, list): return False
        
    if "properties" in schema and isinstance(data, dict):
        for prop, prop_schema in schema["properties"].items():
            if prop in schema.get("required", []) and prop not in data:
                return False
            # Optional: recurse or check types
            
    return True

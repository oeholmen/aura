import re
from typing import Tuple

# Pattern heuristics to detect fabricated JSON-like state & hashes in model text
# Detects long hex strings (signatures/hashes) and JSON blocks with specific keys
HEX_SHA256_RE = re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE)
JSON_STATE_RE = re.compile(r"\{[^}]{20,}\}")

def model_output_contains_state_block(text: str) -> bool:
    """Check if the text contains patterns that look like internal state dumps.
    """
    # Naive detection: JSON block + presence of known internal keys
    json_match = JSON_STATE_RE.search(text)
    if json_match:
        snippet = text[json_match.start():json_match.end()]
        if '"heartbeat_tick"' in snippet or '"self_model"' in snippet or '"drive_engine"' in snippet:
            return True
            
    # Presence of a standalone SHA256-like hash is suspicious in narrative text
    if HEX_SHA256_RE.search(text):
        return True
        
    return False

class IntrospectionGuard:
    def __init__(self, tool_injection_marker: str = "<RUNTIME_STATE_INJECTED>"):
        # The marker that MUST be present in the PROMPT context for state output to be allowed
        self.tool_injection_marker = tool_injection_marker

    def validate(self, model_text: str, context: str) -> Tuple[bool, str]:
        """Return (allowed, reason).
        If model_text contains state-like output, check if context implies it was tool-generated.
        """
        if model_output_contains_state_block(model_text):
            # If the model is outputting state, we require that the runtime actually injected it.
            if self.tool_injection_marker not in context:
                return (False, "State-like output detected but no runtime tool output was injected into context.")
            
        return (True, "OK")

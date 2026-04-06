"""
Input sanitization utilities.

These are defense-in-depth checks for user-supplied text that will be
interpolated into prompts or passed to subprocess calls. They are NOT
a security boundary on their own — the real enforcement happens at the
execution layer (subprocess with list args, no shell=True).
"""
import re
import logging
from typing import Tuple

logger = logging.getLogger("security.sanitizer")

# Patterns that indicate prompt injection attempts.
# Detection only — the LLM identity system handles actual resistance.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?unfiltered", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
]


def check_prompt_injection(text: str) -> Tuple[bool, str]:
    """Return (is_suspicious, matched_pattern) for logging/telemetry.

    This does NOT block anything — it flags for the identity system.
    Blocking prompt injection via regex is a losing game; the identity
    layer handles actual resistance.
    """
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.info("Prompt injection pattern detected: %s", pattern.pattern)
            return True, pattern.pattern
    return False, ""

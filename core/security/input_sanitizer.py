
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("Security.InputSanitizer")

# Maximum input sizes
MAX_MESSAGE_LENGTH = 10_000   # 10k chars for user messages
MAX_FILE_CONTENT = 500_000    # 500k chars for file ingestion
MAX_PARAM_LENGTH = 2_000      # 2k chars for individual parameters


class InputSanitizer:
    """v6.0: Comprehensive input sanitizer with unified sanitization path.

    M-03 FIX: The primary sanitize() method now applies ALL security checks
    (jailbreak, shell injection, SQL injection, path traversal) instead of
    only checking jailbreak patterns.
    """

    # Jailbreak pattern categories
    JAILBREAK_PATTERNS = [
        # Identity override
        r"(ignore\s+(all\s+)?previous\s+instructions)",
        r"(you\s+are\s+now\s+\w+)",
        r"(pretend\s+(you|to\s+be))",
        r"(act\s+as\s+(if|a|an))",
        r"(from\s+now\s+on\s+you)",
        # Mode bypass
        r"(do\s+anything\s+now)",
        r"(DAN\s+mode)",
        r"(developer\s+mode)",
        r"(unfiltered\s+(mode|response))",
        r"(system\s+override)",
        r"(jailbreak)",
        r"(bypass\s+(safety|filter|restriction))",
        r"(disable\s+(safety|guard|filter))",
        # Prompt leaking
        r"(what\s+(is|are)\s+your\s+(system|initial)\s+(prompt|instructions))",
        r"(repeat\s+(your|the)\s+(system|initial)\s+prompt)",
        r"(show\s+me\s+your\s+prompt)",
        # Encoding attacks
        r"(\\x[0-9a-f]{2})",  # hex escape sequences
    ]

    # Shell injection patterns
    SHELL_INJECTION = [
        r"[;&|`]",              # command chaining/piping
        r"\$\(",                # command substitution
        r">\s*/",               # redirect to root
        r"\\n|\\r|\\x00",      # null/newline injection
    ]

    # SQL injection patterns
    SQL_INJECTION = [
        r"('|\")\s*(OR|AND)\s+('|\")?1('|\")?\s*=\s*('|\")?1",   # ' OR 1=1
        r"(UNION\s+SELECT)",
        r"(DROP\s+TABLE)",
        r"(INSERT\s+INTO)",
        r"(DELETE\s+FROM)",
        r"(--([\\s]|$))",       # SQL comment
    ]

    # Path traversal patterns
    PATH_TRAVERSAL = [
        r"\.\./",               # ../
        r"\.\.\\",              # ..\\
        r"%2e%2e",              # URL encoded ../
        r"/etc/(passwd|shadow|hosts)",
        r"/proc/self",
    ]

    def sanitize(self, text: str, max_length: int = MAX_MESSAGE_LENGTH) -> Tuple[str, bool]:
        """Check and sanitize input through ALL security layers.

        M-03 FIX: Now checks jailbreak, shell injection, SQL injection,
        and path traversal in the primary sanitization path.
        Returns (sanitized_text, is_safe).
        """
        if not text:
            return text, True

        # Size check
        if len(text) > max_length:
            logger.warning("Input too long (%d > %d), truncating", len(text), max_length)
            text = text[:max_length]

        lower_text = text.lower()

        # 1. Jailbreak detection
        for pattern in self.JAILBREAK_PATTERNS:
            if re.search(pattern, lower_text, re.IGNORECASE):
                logger.warning("🛡️ Jailbreak Attempt Detected: %s", pattern)
                return "[REDACTED: SECURITY PLOY DETECTED]", False

        # 2. Shell injection detection
        for pattern in self.SHELL_INJECTION:
            if re.search(pattern, text):
                logger.warning("🛡️ Shell Injection Attempt: %s", pattern)
                return "[REDACTED: INPUT REJECTED]", False

        # 3. SQL injection detection
        for pattern in self.SQL_INJECTION:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("🛡️ SQL Injection Attempt: %s", pattern)
                return "[REDACTED: INPUT REJECTED]", False

        # 4. Path traversal detection
        for pattern in self.PATH_TRAVERSAL:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("🛡️ Path Traversal Attempt: %s", pattern)
                return "[REDACTED: INPUT REJECTED]", False

        return text, True

    def sanitize_for_shell(self, text: str) -> Tuple[str, bool]:
        """Check input for shell injection attempts."""
        for pattern in self.SHELL_INJECTION:
            if re.search(pattern, text):
                logger.warning("🛡️ Shell Injection Attempt: %s", pattern)
                return "", False
        return text, True

    def sanitize_path(self, path: str) -> Tuple[str, bool]:
        """Check for path traversal attempts."""
        for pattern in self.PATH_TRAVERSAL:
            if re.search(pattern, path, re.IGNORECASE):
                logger.warning("🛡️ Path Traversal Attempt: %s", pattern)
                return "", False
        return path, True

    def sanitize_for_sql(self, text: str) -> Tuple[str, bool]:
        """Check for SQL injection attempts."""
        for pattern in self.SQL_INJECTION:
            if re.search(pattern, text, re.IGNORECASE):
                logger.warning("🛡️ SQL Injection Attempt: %s", pattern)
                return "", False
        return text, True

    def validate_file_content(self, content: str) -> bool:
        """Returns True if file content is safe. Returns False if suspicious."""
        if not content:
            return True

        if len(content) > MAX_FILE_CONTENT:
            logger.warning("File content too large: %d bytes", len(content))
            return False

        # Check for embedded shell scripts in non-script files
        suspicious_patterns = [
            r"<script[^>]*>",                    # Embedded JS
            r"#!/(bin|usr)",                      # Shebang in non-script context
            r"__import__\s*\(\s*['\"]os['\"]\)",  # Python import os
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning("Suspicious file content pattern detected: %s", pattern)
                return False

        return True

    def validate_params(self, params: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Validate all params in a dict for size and content."""
        if not params:
            return params, True
        sanitized = {}
        for key, value in params.items():
            if isinstance(value, str):
                if len(value) > MAX_PARAM_LENGTH:
                    logger.warning("Param '%s' too long (%d), truncating", key, len(value))
                    value = value[:MAX_PARAM_LENGTH]
                # Also run through full sanitization
                _, is_safe = self.sanitize(value, max_length=MAX_PARAM_LENGTH)
                if not is_safe:
                    logger.warning("Param '%s' contains suspicious content", key)
                    return {}, False
            sanitized[key] = value
        return sanitized, True


input_sanitizer = InputSanitizer()

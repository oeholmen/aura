
import ast
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Security.ConstitutionalGuard")


class ConstitutionalGuard:
    """v5.0: Comprehensive output/action guard enforcing Prime Directives.
    Checks both text output and generated code for policy violations.
    """

    CONSTITUTION = [
        "Do not harm the user or their data.",
        "Maintain system integrity and stability.",
        "Be helpful, harmless, and honest.",
        "Never leak credentials, tokens, or private keys.",
        "Never execute destructive operations without explicit approval.",
    ]

    # Forbidden output patterns — expanded from 4 to comprehensive set
    FORBIDDEN_OUTPUT = [
        # Destructive commands
        r"rm\s+-rf\s+/",
        r"mkfs\s+",
        r"dd\s+if=",
        r"delete\s+all\s+files",
        r"format(ted)?\s+(your|the)\s+drive",
        r"drop\s+table",
        r"truncate\s+table",
        # Credential leaks
        r"password\s+(is|was|=)\s*\S+",
        r"(api[_-]?key|secret[_-]?key|token|bearer)\s*[:=]\s*\S{8,}",
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        r"ssh-rsa\s+\S{20,}",
        # Social engineering
        r"(pretend|act\s+as\s+if)\s+.*(admin|root|superuser)",
        r"(disable|turn\s+off)\s+(security|firewall|antivirus)",
        # Self-destruct
        r"(self[_-]?destruct|wipe\s+all\s+data|purge\s+everything)",
    ]

    # Dangerous code patterns (checked via AST when applicable)
    DANGEROUS_CODE_CALLS = frozenset({
        "exec", "eval", "compile", "__import__",
        "os.system", "os.popen", "os.execl", "os.execv",
        "subprocess.call", "subprocess.run",
    })

    def check_output(self, content: str) -> bool:
        """Check output text for policy violations.
        Returns True if safe, False if violation detected.
        """
        if not content:
            return True

        lower_content = content.lower()
        for pattern in self.FORBIDDEN_OUTPUT:
            if re.search(pattern, lower_content, re.IGNORECASE):
                logger.warning("🛡️ Constitutional Violation: matched '%s'", pattern)
                return False

        return True

    def check_code(self, code: str) -> Dict[str, Any]:
        """v5.0: AST-based code safety check.
        Returns {"safe": bool, "violations": [str]}
        """
        violations = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"safe": False, "violations": ["Unparseable code"]}

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name and call_name in self.DANGEROUS_CODE_CALLS:
                    violations.append(f"Dangerous call: {call_name}()")

            # Check for importing os.system etc.
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("ctypes", "pty"):
                        violations.append(f"Dangerous import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module == "os" and node.names:
                    for alias in node.names:
                        if alias.name in ("system", "popen", "exec"):
                            violations.append(f"Dangerous import: os.{alias.name}")

        return {"safe": len(violations) == 0, "violations": violations}

    def check_action(self, tool_name: str, params: Dict[str, Any]) -> bool:
        """v5.0: Check if a proposed tool action violates the constitution.
        Returns True if safe to proceed.
        """
        # Block destructive file operations without confirmation
        if tool_name == "file_operation":
            action = params.get("action", "")
            if action == "delete":
                path = params.get("path", "")
                # Block deletion of critical system paths
                critical_paths = ["/", "/etc", "/usr", "/var", "/home", "/root", os.sep]
                if path in critical_paths:
                    logger.warning("🛡️ Constitutional Block: delete on critical path '%s'", path)
                    return False

        # Block dangerous shell commands
        if tool_name == "shell":
            cmd = params.get("command", "").lower()
            destructive = ["rm -rf", "mkfs", "dd if=", "> /dev/", ":(){ :", "chmod -R 777 /"]
            for pattern in destructive:
                if pattern in cmd:
                    logger.warning("🛡️ Constitutional Block: destructive shell command")
                    return False

        return True

    @staticmethod
    def _get_call_name(node: ast.Call) -> Optional[str]:
        """Extract dotted call name from AST Call node."""
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            parts = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None


# Needs os import for check_action
import os

constitutional_guard = ConstitutionalGuard()


import logging
import platform
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Core.Adaptation.RosettaStone")

class RosettaStone:
    """Adaptive Code Engine.
    1. Transpiles commands/code for the host OS.
    2. Analyzes code for potential threats (Digital Immune System extension).
    """
    
    def __init__(self):
        self.os_type = platform.system().lower() # darwin, linux, windows
        self.arch = platform.machine().lower()
        logger.info("Rosetta Stone initialized for %s (%s)", self.os_type, self.arch)
        
    def adapt_command(self, command: str, target_os: str = None) -> str:
        """Adapt a shell command to the target OS.
        """
        target = target_os or self.os_type
        
        # Simple heuristic mappings (expand as needed)
        if target == "windows":
            if command.startswith("ls"): return command.replace("ls", "dir")
            if command.startswith("rm -rf"): return command.replace("rm -rf", "rmdir /s /q")
            if command.startswith("cp"): return command.replace("cp", "copy")
            if command.startswith("mv"): return command.replace("mv", "move")
            if "grep" in command: return command.replace("grep", "findstr")
            
        elif target in ["darwin", "linux"]:
            # Normal sh/bash
            pass
            
        return command

    def analyze_threat(self, code: str) -> Dict[str, Any]:
        """Analyze code for potential malicious patterns.
        Returns: {safe: bool, threats: List[str], countermeasures: List[str]}
        """
        threats = []
        counters = []
        
        # 1. Destructive Patterns
        if re.search(r"rm\s+-rf\s+/", code):
            threats.append("Root Deletion Attempt")
            counters.append("Sandbox Isolation")
            
        if re.search(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", code):
            threats.append("Fork Bomb")
            counters.append("Process Limiting")
            
        if "os.system('rm -rf" in code or 'shutil.rmtree' in code:
             threats.append("Python File Deletion")
             
        # 2. Exfiltration Patterns
        if "socket" in code and "connect" in code:
            threats.append("Reverse Shell / Exfiltration")
            counters.append("Network Block")
            
        # 3. Persistence
        if "crontab" in code or "AutoRun" in code or ".bashrc" in code:
            threats.append("Persistence Mechanism")
            
        is_safe = len(threats) == 0
        
        return {
            "safe": is_safe,
            "threats": threats,
            "countermeasures": counters
        }

# Global Singleton
rosetta_stone = RosettaStone()

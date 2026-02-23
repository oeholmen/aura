# skills/system_ops.py
import logging
import os
import platform
import re
import subprocess
import asyncio
from typing import Any, Dict

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.SystemOps")

# Safe characters for application names (letters, digits, spaces, dots, hyphens)
_SAFE_APP_NAME = re.compile(r'^[\w\s\.\-]+$')
# Allowed file extensions for open_file
_SAFE_EXTENSIONS = {'.txt', '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.mp3', '.mp4',
                    '.doc', '.docx', '.xls', '.xlsx', '.csv', '.html', '.md', '.json'}

class SystemOpsSkill(BaseSkill):
    name = "system_ops"
    description = "Control system operations (launch apps, open files)."
    inputs = {
        "action": "open_app | open_file",
        "target": "App name or file path"
    }

    async def execute(self, goal: Dict, context: Dict) -> Dict:
        params = goal.get("params", {})
        action = params.get("action", "open_app")
        target = params.get("target")

        if not target:
            return {"ok": False, "error": "No target specified."}

        # Input validation
        if action == "open_app":
            if not _SAFE_APP_NAME.match(target):
                return {"ok": False, "error": f"Invalid app name: {target}"}
        elif action == "open_file":
            # Resolve to absolute path and check extension
            resolved = os.path.abspath(os.path.expanduser(target))
            _, ext = os.path.splitext(resolved)
            if ext.lower() not in _SAFE_EXTENSIONS:
                return {"ok": False, "error": f"Unsupported file extension: {ext}"}
            target = resolved  # Use resolved path

        logger.info("System Op: %s -> %s", action, target)

        try:
            if platform.system() == "Darwin": # macOS
                if action == "open_app":
                    await asyncio.create_subprocess_exec("open", "-a", target)
                    return {"ok": True, "summary": f"Launched {target}"}
                
                elif action == "open_file":
                    await asyncio.create_subprocess_exec("open", target)
                    return {"ok": True, "summary": f"Opened {target}"}
            
            else: 
                if action == "open_app" or action == "open_file":
                    await asyncio.create_subprocess_exec("xdg-open", target)
                    return {"ok": True, "summary": f"Opened {target} (Linux)"}

            return {"ok": False, "error": f"Unsupported action or OS: {action} on {platform.system()}"}

        except subprocess.CalledProcessError as e:
            return {"ok": False, "error": f"Command failed: {e}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

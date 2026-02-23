"""Safe Sandbox Skill - Uses subprocess isolation with timeout.
v3.1: Fixed to prevent agent crashes from bad code.
"""
import asyncio
import os
import subprocess
import tempfile
from typing import Any, Dict

from infrastructure import BaseSkill


class SandboxSkill(BaseSkill):
    name = "internal_sandbox"
    description = "An invisible scratchpad/terminal to test Python code or write notes purely for internal thought processing. Data here is ephemeral."
    inputs = {
        "code": "Python code to execute immediately.",
        "notes": "Text to store in temporary scratchpad."
    }
    output = "Execution output or confirmation."
    
    # Safety limits
    MAX_EXECUTION_TIME = 30  # seconds
    MAX_OUTPUT_SIZE = 10000  # characters

    def __init__(self):
        self.scratchpad = ""

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        code = goal.get("params", {}).get("code")
        notes = goal.get("params", {}).get("notes")
        
        if notes:
            # Append to scratchpad
            self.scratchpad += f"\n--- {goal.get('id', 'note')} ---\n{notes}\n"
            return {"ok": True, "summary": "Notes added to internal scratchpad."}

        if code:
            return await self._execute_code_safely(code)
                
        return {"ok": True, "result": self.scratchpad, "summary": "Viewed scratchpad."}

    async def _execute_code_safely(self, code: str) -> Dict[str, Any]:
        """Execute code in a subprocess with timeout (Async).
        A security preamble blocks dangerous operations before exec.
        """
        # ... preamble ... (preserved)
        try:
            # Prepend security preamble to user code
            sandboxed_code = SECURITY_PREAMBLE + "\n" + code

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(sandboxed_code)
                temp_path = f.name
            
            try:
                # Run in subprocess with timeout
                process = await asyncio.create_subprocess_exec(
                    'python3', temp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tempfile.gettempdir()
                )
                
                try:
                    stdout_b, stderr_b = await asyncio.wait_for(process.communicate(), timeout=self.MAX_EXECUTION_TIME)
                    stdout = stdout_b.decode()[:self.MAX_OUTPUT_SIZE] if stdout_b else ""
                    stderr = stderr_b.decode()[:self.MAX_OUTPUT_SIZE] if stderr_b else ""
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except:
                        pass
                    return {"ok": False, "error": f"Code execution timed out after {self.MAX_EXECUTION_TIME}s"}

                output = f"Stdout:\n{stdout}"
                if stderr:
                    output += f"\nStderr:\n{stderr}"
                
                if process.returncode != 0:
                    return {
                        "ok": False, 
                        "error": f"Code exited with code {process.returncode}",
                        "result": output,
                        "summary": "Code execution failed."
                    }
                    
                return {"ok": True, "result": output, "summary": "Code executed in sandbox."}
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass  # Temp file cleanup failure is not critical

        except Exception as e:
            return {"ok": False, "error": f"Sandbox Exception: {e}"}

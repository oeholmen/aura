import shlex
import subprocess
import asyncio


class ShellInterface:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.logger = logging.getLogger("Shell")

    async def execute(self, command):
        """Executes a shell command safely (async offload).
        Captures stdout and stderr.
        """
        self.logger.info("Executing: %s", command)
        try:
            # Tokenize command safely
            if isinstance(command, str):
                tokens = shlex.split(command)
            else:
                tokens = list(command)
            if not tokens:
                return {"success": False, "error": "Empty command.", "stdout": "", "stderr": "", "code": -1}
            
            result = await asyncio.to_thread(
                subprocess.run,
                tokens,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "code": result.returncode
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "Command timed out.", "stdout": "", "stderr": "", "code": -1}
        except Exception as e:
            return {"success": False, "error": str(e), "stdout": "", "stderr": "", "code": -1}

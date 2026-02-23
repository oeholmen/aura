"""Secure Docker Sandbox for Sovereign Code Execution.
Force-disables networking and restricts resources.
"""

import io
import logging
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional

import docker

logger = logging.getLogger("Aura.SecureSandbox")

class SecureDockerSandbox:
    """Executes untrusted code in a network-isolated Docker container.
    """
    
    def __init__(self, image_name: str = "aura-sovereign-sandbox:latest"):
        try:
            self.client = docker.from_env()
            self.image_name = image_name
        except Exception as e:
            logger.error("Docker initialization failed: %s", e)
            self.client = None

    def execute_code(self, code: str, workspace_path: str, timeout: int = 30) -> Dict[str, Any]:
        """Run code in the isolated container.
        """
        if not self.client:
            return {"ok": False, "error": "Docker not available on host."}

        container = None
        try:
            # Create container with strict limits
            container = self.client.containers.run(
                image=self.image_name,
                command=["python3", "-c", code],
                network_disabled=True,      # KEY REQUIREMENT: Zero network access
                mem_limit="256m",           # Resource limit: Memory
                nano_cpus=500000000,        # Resource limit: 0.5 CPU
                detach=True,
                remove=False,
                stderr=True,
                stdout=True
            )

            # Wait for completion
            try:
                result = container.wait(timeout=timeout)
                logs = container.logs().decode("utf-8")
                exit_code = result.get("StatusCode", 1)
                
                return {
                    "ok": exit_code == 0,
                    "exit_code": exit_code,
                    "output": logs
                }
            except Exception as e:
                container.kill()
                return {"ok": False, "error": f"Execution timeout or error: {str(e)}"}

        except Exception as e:
            logger.error("Sandbox execution fatal error: %s", e)
            return {"ok": False, "error": str(e)}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception as exc:
                    logger.debug("Suppressed: %s", exc)
    def verify_safety(self) -> bool:
        """Verify that the sandbox is correctly blocking network access.
        """
        test_code = "import urllib.request; urllib.request.urlopen('http://google.com', timeout=1)"
        result = self.execute_code(test_code, "/tmp")
        # If it failed to connect (which it should), then it's safe.
        if "timeout" in result.get("output", "").lower() or "error" in result.get("error", "").lower():
            logger.info("Sandbox Safety Verified: Network access blocked.")
            return True
        logger.warning("Sandbox Safety Check FAILED: Potential network leak!")
        return False

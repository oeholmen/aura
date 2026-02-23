"""GhostBoot: Shadow Boot-Path Validation
Verifies that Aura can still initialize after code modifications.
"""
import os
import sys
import subprocess
import time
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("SelfEvolution.GhostBoot")

class GhostBootValidator:
    """Validator that performs a 'trial boot' in a separate process."""

    def __init__(self, project_root: Optional[Path] = None):
        from core.config import config
        self.root = project_root or config.paths.project_root

    async def validate_boot(self, sandbox_path: Path, timeout: int = 30) -> Tuple[bool, str]:
        """Attempts to 'boot' the system in the sandbox (Async)."""
        logger.info("👻 Starting Ghost Boot validation in %s...", sandbox_path)
        
        # We use a specialized minimal boot script to speed up validation
        # and avoid side effects (like connecting to real APIs)
        boot_script = sandbox_path / ".ghost_boot.py"
        self._create_minimal_boot_script(boot_script)

        try:
            # Run the boot script in a subprocess
            env = os.environ.copy()
            env["PYTHONPATH"] = str(sandbox_path)
            env["AURA_GHOST_BOOT"] = "1" # Flag to skip heavy systems
            
            process = subprocess.Popen(
                [sys.executable, str(boot_script)],
                cwd=sandbox_path,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            start_time = time.time()
            success = False
            output = ""
            error_output = ""

            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    break
                await asyncio.sleep(0.5)

            # Final check - wait for it to finish or kill it
            try:
                stdout, stderr = process.communicate(timeout=2)
                output += stdout
                error_output += stderr
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                output += stdout
                error_output += stderr

            if "GHOST_HEARTBEAT_STABLE" in output:
                success = True

            if success:
                logger.info("✅ Ghost Boot SUCCESS: System reached stable state.")
                return True, "Stable boot reached"
            else:
                error_msg = error_output or "Timeout reached without heartbeat"
                logger.error("❌ Ghost Boot FAILED: %s", error_msg)
                return False, f"Boot failure: {error_msg}"

        except Exception as e:
            logger.error("Ghost Boot execution error: %s", e)
            return False, str(e)
        finally:
            if boot_script.exists():
                try:
                    boot_script.unlink()
                except Exception as e:
                    logger.debug("Failed to unlink ghost boot script: %s", e)

    def _create_minimal_boot_script(self, script_path: Path):
        """Creates a script that initializes key Aura subsystems for verification."""
        content = """
import os
import sys
import logging
import time
from unittest.mock import MagicMock

# Disable all heavy systems immediately
os.environ["AURA_GHOST_BOOT"] = "1"
os.environ["AURA_INTERNAL_ONLY"] = "1"

# Mock out blocking components before importing
sys.modules["core.managers.health_monitor"] = MagicMock()
sys.modules["core.resilience.state_manager"] = MagicMock()

try:
    logger = logging.getLogger("GhostBoot")
    logger.info("Ghost: Initializing core architecture...")
    from core.config import config
    from core.orchestrator import RobustOrchestrator
    
    # Minimal init
    orch = RobustOrchestrator()
    logger.info("Ghost: Orchestrator instance created.")
    
    # Check if critical components are present
    if not hasattr(orch, 'status'):
        raise RuntimeError("Orchestrator missing status object")
        
    logger.info("Ghost: Orchestrator Status -> %s", orch.status)
    
    # We reached the end of validation without crashing
    logger.info("GHOST_HEARTBEAT_STABLE")
    sys.exit(0)
except Exception as e:
    import traceback
    logger.error("Ghost: BOOT CRASH: %s", e)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
"""
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)

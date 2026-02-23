import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger("Optimizer.PatchLibrary")

class PatchStrategy:
    name = "base_patch"
    
    def match(self, failure_reason: str) -> bool:
        return False
        
    async def apply(self) -> bool:
        raise NotImplementedError

class GitInitPatch(PatchStrategy):
    name = "git_init_fix"
    
    def match(self, failure_reason: str) -> bool:
        return "not a git repository" in failure_reason.lower()
        
    async def apply(self) -> bool:
        logger.warning("⚙️ TRUE AUTONOMY: Autonomic Core engaging 'git init' self-repair...")
        try:
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(["git", "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Auto-Healer: Re-init corrupted repository"], check=True, capture_output=True)
            logger.info("✅ Autonomic Core successfully repaired local Git repository.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("❌ Autonomic Core Git repair failed: %s", e.stderr.decode() if e.stderr else e)
            return False

class PipInstallPatch(PatchStrategy):
    name = "pip_install_fix"
    
    def match(self, failure_reason: str) -> bool:
        return "modulenotfounderror" in failure_reason.lower()
        
    async def apply(self, failure_reason: str) -> bool:
        # Extract module name matches "No module named 'xyz'"
        match = re.search(r"No module named '(\w+)'", failure_reason)
        if match:
            module = match.group(1)
            # Validate module name
            if not re.match(r'^[a-zA-Z0-9_-]+$', module):
                logger.error("Suspicious module name: %s", module)
                return False
            logger.warning("⚙️ TRUE AUTONOMY: Autonomic Core attempting to install missing module: %s", module)
            try:
                # Use sys.executable to ensure we install into the active Python environment
                import sys
                result = subprocess.run([sys.executable, "-m", "pip", "install", module], check=True, capture_output=True)
                logger.info("✅ Autonomic Core successfully installed missing package '%s'", module)
                return True
            except subprocess.CalledProcessError as e:
                logger.error("❌ Autonomic Core failed to install '%s': %s", module, e.stderr.decode() if e.stderr else e)
                return False
        return False

# Registry
AVAILABLE_PATCHES = [GitInitPatch(), PipInstallPatch()]

"""Aura Hive Mind Sync
Enables memory synchronization between Home and Cloud variants via a private Git repository.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from core.skills.base_skill import BaseSkill

logger = logging.getLogger("Skills.MemorySync")

class MemorySyncParams(BaseModel):
    action: Literal["sync", "push", "pull"] = Field("sync", description="The sync action to perform.")
    consented: bool = Field(False, description="Manual consent required for cloud memory upload (push/sync).")

class MemorySyncSkill(BaseSkill):
    name = "memory_sync"
    description = "Syncs semantic memory (data/memory) with a remote Git repository."
    input_model = MemorySyncParams
    
    def __init__(self):
        super().__init__()
        self.memory_path = Path("data/memory")
        self.repo_url = os.getenv("AURA_MEMORY_REPO")  # Private Git Repo URL
        
    async def execute(self, params: MemorySyncParams, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute memory synchronization.
        """
        # Legacy support
        if isinstance(params, dict):
            try:
                params = MemorySyncParams(**params)
            except Exception as e:
                return {"ok": False, "error": f"Invalid input: {e}"}

        action = params.action # sync, push, pull
        
        if not self.repo_url:
            return {"ok": False, "error": "AURA_MEMORY_REPO env var not set."}
            
        # Security Gate: Require explicit consent for remote mutation
        consented = params.consented
        if (action == "push" or action == "sync") and not consented:
            logger.warning("MemorySync blocked: Consent not provided for remote push.")
            return {"ok": False, "error": "Security Restriction: Manual consent required for cloud memory upload."}
            
        if not self.memory_path.exists():
            self.memory_path.mkdir(parents=True, exist_ok=True)
            
        # Check if it's a git repo
        git_dir = self.memory_path / ".git"
        if not git_dir.exists():
            return self._initialize_repo()
            
        if action == "push":
            return self._push()
        elif action == "pull":
            return self._pull()
        else:
            # Sync = Pull then Push
            pull_res = self._pull()
            push_res = self._push()
            return {
                "ok": pull_res["ok"] and push_res["ok"],
                "pull": pull_res,
                "push": push_res
            }
            
    def _initialize_repo(self):
        try:
            cwd = str(self.memory_path)
            subprocess.run(["git", "init"], cwd=cwd, check=True)
            subprocess.run(["git", "remote", "add", "origin", self.repo_url], cwd=cwd, check=True)
            # Initial pull
            subprocess.run(["git", "pull", "origin", "main"], cwd=cwd, check=False)
            return {"ok": True, "message": "Memory repository initialized."}
        except Exception as e:
            return {"ok": False, "error": f"Init failed: {e}"}

    def _pull(self):
        try:
            cwd = str(self.memory_path)
            res = subprocess.run(["git", "pull", "origin", "main"], cwd=cwd, capture_output=True, text=True)
            if res.returncode == 0:
                logger.info("Memory Pulled successfully.")
                return {"ok": True, "message": "Memory synced from cloud."}
            else:
                logger.warning("Pull failed: %s", res.stderr)
                return {"ok": False, "error": res.stderr}
        except Exception as e:
            return {"ok": False, "error": f"Pull error: {e}"}

    def _push(self):
        try:
            cwd = str(self.memory_path)
            subprocess.run(["git", "add", "."], cwd=cwd, check=True)
            subprocess.run(["git", "commit", "-m", "Aura Memory Update"], cwd=cwd, check=False)
            res = subprocess.run(["git", "push", "origin", "main"], cwd=cwd, capture_output=True, text=True)
            
            if res.returncode == 0:
                logger.info("Memory Pushed successfully.")
                return {"ok": True, "message": "Memory uploaded to cloud."}
            else:
                logger.warning("Push failed: %s", res.stderr)
                return {"ok": False, "error": res.stderr}
        except Exception as e:
            return {"ok": False, "error": f"Push error: {e}"}

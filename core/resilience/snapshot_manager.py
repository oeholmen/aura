
"""core/resilience/snapshot_manager.py

Handles immutable "Heartstone" snapshots of critical system files.
Enables transactional rollbacks for autonomous self-modification.
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import config

logger = logging.getLogger("Resilience.SnapshotManager")

class SnapshotManager:
    """Manages system snapshots and automated rollbacks."""

    def __init__(self, history_limit: int = 5):
        self.root = config.paths.project_root
        self.snapshot_dir = config.paths.data_dir / "snapshots"
        self.history_limit = history_limit
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.index_file = self.snapshot_dir / "snapshot_index.json"
        self.snapshots = self._load_index()

    def _load_index(self) -> List[Dict[str, Any]]:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load snapshot index: %s", e)
        return []

    def _save_index(self):
        try:
            with open(self.index_file, "w") as f:
                json.dump(self.snapshots, f, indent=2)
        except Exception as e:
            logger.error("Failed to save snapshot index: %s", e)

    def create_snapshot(self, label: str, files: Optional[List[str]] = None) -> Optional[str]:
        """Creates a snapshot of the specified files or core system by default."""
        timestamp = int(time.time())
        snapshot_id = f"snap_{timestamp}_{label.replace(' ', '_')}"
        target_dir = self.snapshot_dir / snapshot_id
        target_dir.mkdir(parents=True, exist_ok=True)

        if files is None:
            # Default to core system files
            files = ["core", "infrastructure", "utils", "interface/server.py"]

        copied_files = []
        for f_path in files:
            src = self.root / f_path
            if src.exists():
                dst = target_dir / f_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                copied_files.append(f_path)

        snapshot_info = {
            "id": snapshot_id,
            "timestamp": timestamp,
            "label": label,
            "files": copied_files,
            "path": str(target_dir)
        }

        self.snapshots.append(snapshot_info)
        # Sort by timestamp and keep limit
        self.snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
        
        # Cleanup old snapshots
        while len(self.snapshots) > self.history_limit:
            old = self.snapshots.pop()
            old_path = Path(old["path"])
            if old_path.exists():
                shutil.rmtree(old_path)
            logger.info("Purged old snapshot: %s", old["id"])

        self._save_index()
        logger.info("Created snapshot: %s (%s)", snapshot_id, label)
        return snapshot_id

    def rollback(self, snapshot_id: Optional[str] = None) -> bool:
        """Rolls back the system to a previous snapshot."""
        if not self.snapshots:
            logger.error("Rollback failed: No snapshots available.")
            return False

        target_snap = None
        if snapshot_id:
            for s in self.snapshots:
                if s["id"] == snapshot_id:
                    target_snap = s
                    break
        else:
            # Rollback to the most recent one
            target_snap = self.snapshots[0]

        if not target_snap:
            logger.error("Rollback failed: Snapshot %s not found.", snapshot_id)
            return False

        logger.warning("🔄 INITIATING ROLLBACK TO: %s (%s)", target_snap["id"], target_snap["label"])
        
        snap_path = Path(target_snap["path"])
        for f_path in target_snap["files"]:
            src = snap_path / f_path
            dst = self.root / f_path
            
            if src.exists():
                if src.is_dir():
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                logger.info("  ✓ Restored: %s", f_path)

        logger.info("✅ Rollback complete. System state restored.")
        return True

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        return self.snapshots[0] if self.snapshots else None

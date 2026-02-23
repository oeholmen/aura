
import json
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.config import config

logger = logging.getLogger("Core.Resilience.StateManager")

class StateManager:
    """Manages system state snapshots for resilience and recovery.
    Saves critical data (memory, configuration, active tasks) to disk.
    """
    
    def __init__(self):
        self.snapshot_dir = Path(config.paths.data_dir) / "snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.current_state = {
            "version": "1.0",
            "cycle_count": 0,
            "startup_time": 0,
            "last_active": 0,
            "active_goals": [],
            "short_term_memory": []
        }
        
    async def save_snapshot_async(self, orchestrator_state: Dict[str, Any], reason: str = "periodic") -> bool:
        """Asynchronously save a snapshot using a background thread."""
        from core.utils.executor import run_in_thread
        return await run_in_thread(self.save_snapshot, orchestrator_state, reason)

    def save_snapshot(self, orchestrator_state: Dict[str, Any], reason: str = "periodic") -> bool:
        """Save a snapshot of the current system state.
        
        Args:
            orchestrator_state: Dict containing current orchestrator data (memory, goals, etc)
            reason: Why the snapshot is being taken (periodic, shutdown, error)

        """
        try:
            timestamp = int(time.time())
            iso_time = datetime.now().isoformat()
            
            snapshot = {
                "meta": {
                    "timestamp": timestamp,
                    "iso_time": iso_time,
                    "reason": reason,
                    "version": "3.4"
                },
                "data": orchestrator_state
            }
            
            # 1. Save "latest" snapshot (for quick recovery)
            latest_path = self.snapshot_dir / "latest_snapshot.json"
            
            # Write to temp file first for atomicity
            temp_path = latest_path.with_suffix(".tmp")
            with open(temp_path, 'w') as f:
                json.dump(snapshot, f, indent=2)
            
            if reason == "existential":
                existential_path = self.snapshot_dir / "existential_snapshot.json"
                shutil.copy2(temp_path, existential_path)
                logger.info("🛡️ Hardened Existential Snapshot secured.")

            # specific snapshot for history if it's significant
            if reason in ["shutdown", "error", "manual"]:
                history_path = self.snapshot_dir / f"snapshot_{timestamp}_{reason}.json"
                shutil.copy2(temp_path, history_path)
                
            # Rename temp to latest
            temp_path.replace(latest_path)
            
            logger.debug("State snapshot saved (%s).", reason)
            return True
            
        except Exception as e:
            logger.error("Failed to save state snapshot: %s", e)
            return False

    def load_last_snapshot(self) -> Optional[Dict[str, Any]]:
        """Load the most recent snapshot."""
        return self._load_from_path(self.snapshot_dir / "latest_snapshot.json")

    def load_existential_snapshot(self) -> Optional[Dict[str, Any]]:
        """Phase 18.3: Load the hardened identity snapshot."""
        return self._load_from_path(self.snapshot_dir / "existential_snapshot.json")

    def _load_from_path(self, path: Path) -> Optional[Dict[str, Any]]:
        """Generic loader logic."""
        try:
            if not path.exists():
                logger.debug("Snapshot path %s does not exist.", path)
                return None
                
            with open(path, 'r') as f:
                snapshot = json.load(f)
                
            meta = snapshot.get("meta", {})
            data = snapshot.get("data", {})
            
            logger.info("Loaded snapshot from %s (Reason: %s)", meta.get('iso_time'), meta.get('reason'))
            return data
            
        except Exception as e:
            logger.error("Failed to load snapshot from %s: %s", path, e)
            return None

    def get_snapshot_history(self) -> list:
        """List available snapshots."""
        snapshots = []
        for f in self.snapshot_dir.glob("snapshot_*.json"):
            try:
                snapshots.append({
                    "path": str(f),
                    "name": f.name,
                    "size": f.stat().st_size,
                    "time": f.stat().st_mtime
                })
            except Exception as exc:
                logger.debug("Suppressed: %s", exc)

        return sorted(snapshots, key=lambda x: x['time'], reverse=True)

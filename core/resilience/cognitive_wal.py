"""
core/resilience/cognitive_wal.py
────────────────────────────────
Ensures Aura never loses her train of thought during a power loss or system crash.
Implements a Write-Ahead Log (WAL) for cognitive intents.
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger("Aura.Resilience.WAL")

class CognitiveWAL:
    def __init__(self, filepath: str = "data/memory/wal.jsonl"):
        self.filepath = filepath
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        self._pending_intents: Dict[str, Dict] = {}

    def log_intent(self, turn_id: str, action: str, target: str, context: Optional[Dict] = None):
        """Write the thought to disk BEFORE executing it."""
        entry = {
            "time": time.time(),
            "id": turn_id,
            "action": action,
            "target": target,
            "context": context,
            "status": "pending"
        }
        self._pending_intents[turn_id] = entry
        
        try:
            with open(self.filepath, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to write to WAL: %s", e)

    def mark_complete(self, turn_id: str):
        """Called only when the thought successfully completes."""
        if turn_id in self._pending_intents:
            entry = self._pending_intents.pop(turn_id)
            entry["status"] = "committed"
            entry["time"] = time.time()
            
            try:
                with open(self.filepath, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.error("Failed to commit WAL entry: %s", e)

    def recover_state(self) -> List[Dict]:
        """
        Run at boot. Identifies intents that were logged but not committed.
        """
        if not os.path.exists(self.filepath):
            return []

        intents = {}
        try:
            with open(self.filepath, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        intent_id = entry.get("id")
                        if entry.get("status") == "pending":
                            intents[intent_id] = entry
                        elif entry.get("status") == "committed":
                            if intent_id in intents:
                                del intents[intent_id]
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error("Failed to read WAL during recovery: %s", e)
            return []

        if intents:
            logger.info("💾 WAL: Recovered %s interrupted intents.", len(intents))
        return list(intents.values())

    def clear(self):
        """Prune old committed entries to keep the file small."""
        # Simple implementation: truncate if it gets too large
        try:
            if os.path.exists(self.filepath) and os.path.getsize(self.filepath) > 1024 * 1024: # 1MB
                logger.info("💾 WAL: Truncating log file.")
                open(self.filepath, 'w').close()
        except Exception:
            pass

# Singleton instance
cognitive_wal = CognitiveWAL()

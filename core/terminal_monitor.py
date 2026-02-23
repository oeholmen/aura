"""core/terminal_monitor.py — v4.3 Terminal Self-Monitoring

Aura watches her own log stream for errors and attempts to fix them silently.
She doesn't bother the user about infrastructure noise — she just handles it.

This module:
  1. Captures ERROR/CRITICAL log entries from the Python logging system
  2. Deduplicates and debounces (same error within 60s = ignore)
  3. If an actionable error is detected, generates a self-fix goal
  4. The orchestrator picks up the goal in _process_cycle and executes it
  
All of this is SILENT. The user never sees it unless the fix fails.
"""

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("Aura.TerminalMonitor")


@dataclass
class ErrorEntry:
    """A captured error from the log stream."""

    message: str
    level: str
    source: str
    timestamp: float = field(default_factory=time.time)
    fingerprint: str = ""  # Dedup key
    
    def __post_init__(self):
        # Create fingerprint by stripping timestamps, numbers, and paths
        cleaned = re.sub(r'\d+', 'N', self.message)
        cleaned = re.sub(r'/[^\s]+', '/PATH', cleaned)
        cleaned = re.sub(r'0x[0-9a-f]+', 'ADDR', cleaned)
        self.fingerprint = f"{self.source}:{cleaned[:100]}"


class TerminalMonitor:
    """Watches the log stream for errors that Aura can fix autonomously.
    
    Design:
    - Attaches a custom log handler that captures ERROR+ messages
    - Deduplicates using fingerprints (same type of error = one fix attempt)
    - Cooldown per-fingerprint: won't retry the same fix within 5 minutes
    - Severity filter: ignores known-harmless errors
    - Rate limit: max 3 auto-fixes per 10 minutes to prevent loops
    """
    
    def __init__(self):
        self._error_buffer: deque[ErrorEntry] = deque(maxlen=50)
        self._seen_fingerprints: Dict[str, float] = {}  # fingerprint -> last_seen_time
        self._fix_attempts: Dict[str, float] = {}  # fingerprint -> last_fix_time
        self._fix_count_window: List[float] = []  # timestamps of recent fixes
        self._handler_attached = False
        
        # Errors we know are harmless — don't try to fix these
        self._ignore_patterns = [
            r"Governor check failed",     # Expected when governor not configured
            r"Knowledge Graph unavailable",  # Optional component
            r"NeuroWeb components missing",  # Optional component
            r"Dream cycle failed",         # Non-critical
            r"Pruning failed",             # Has fallback
            r"ServiceWorker registration",  # Browser-side
            r"Simulation failed",          # Fail-open
            r"Broadcast item error",       # Transient WS
            r"aesthetic_critic",           # Optional
            r"Terminal monitor check",     # Don't monitor yourself
            r"Meta-learning",             # Optional
            r"Surprise logic error",      # Non-critical
        ]
        
        # Patterns that ARE actionable and worth fixing
        self._actionable_patterns = {
            r"ImportError|ModuleNotFoundError": "Fix a missing module/import issue",
            r"ConnectionRefused|ConnectionError": "Fix a connection problem — a service may be down",
            r"PermissionError|Permission denied": "Fix a file permission issue",
            r"FileNotFoundError|No such file": "Fix a missing file issue",
            r"MemoryError|out of memory": "Investigate memory pressure — may need to free resources",
            r"TimeoutError|timed out": "Investigate a timeout — something is taking too long",
            r"JSONDecodeError|json.decoder": "Fix a JSON parsing error in data",
            r"KeyError|IndexError": "Fix a data access error in the code",
            r"OSError|IOError": "Fix a system I/O error",
        }
        
        self._cooldown_seconds = 300  # 5 minutes between fix attempts for same error
        self._max_fixes_per_window = 3
        self._fix_window_seconds = 600  # 10 minute window
        
        self._attach_handler()
    
    def _attach_handler(self):
        """Attach a log handler that captures ERROR/CRITICAL messages."""
        if self._handler_attached:
            return
            
        class _MonitorHandler(logging.Handler):
            def __init__(self, monitor: 'TerminalMonitor'):
                super().__init__(level=logging.ERROR)
                self.monitor = monitor
                
            def emit(self, record):
                try:
                    entry = ErrorEntry(
                        message=self.format(record),
                        level=record.levelname,
                        source=record.name,
                    )
                    self.monitor._ingest_error(entry)
                except Exception as e:
                    import sys
                    print("TerminalMonitor Log Error: %s" % e, file=sys.stderr)
        
        handler = _MonitorHandler(self)
        handler.setFormatter(logging.Formatter("%(name)s | %(message)s"))
        logging.getLogger().addHandler(handler)
        self._handler_attached = True
        logger.info("✓ Terminal Monitor attached to log stream (watching for errors)")
    
    def _ingest_error(self, entry: ErrorEntry):
        """Process an incoming error entry."""
        # Check if this matches an ignore pattern
        for pattern in self._ignore_patterns:
            if re.search(pattern, entry.message, re.IGNORECASE):
                return  # Silently ignore
        
        # Dedup: same fingerprint within 60s = skip
        last_seen = self._seen_fingerprints.get(entry.fingerprint, 0)
        if time.time() - last_seen < 60:
            return
        
        self._seen_fingerprints[entry.fingerprint] = time.time()
        self._error_buffer.append(entry)
        logger.debug("Terminal Monitor captured: %s", entry.message[:80])
    
    def check_for_errors(self) -> Optional[Dict[str, Any]]:
        """Called by the orchestrator each cycle.
        Returns an auto-fix goal if there's an actionable error, else None.
        """
        if not self._error_buffer:
            return None
        
        now = time.time()
        
        # Rate limit: clean old fix timestamps
        self._fix_count_window = [t for t in self._fix_count_window if now - t < self._fix_window_seconds]
        if len(self._fix_count_window) >= self._max_fixes_per_window:
            return None  # Too many fixes recently — back off
        
        # Find the oldest unhandled actionable error
        while self._error_buffer:
            entry = self._error_buffer.popleft()
            
            # Check cooldown for this fingerprint
            last_fix = self._fix_attempts.get(entry.fingerprint, 0)
            if now - last_fix < self._cooldown_seconds:
                continue  # Already tried to fix this recently
            
            # Check if actionable
            action = self._classify_error(entry)
            if action:
                # Mark as being fixed
                self._fix_attempts[entry.fingerprint] = now
                self._fix_count_window.append(now)
                
                return {
                    "objective": (
                        f"[SILENT AUTO-FIX] {action}. "
                        f"Error details: {entry.message[:300]}. "
                        f"Diagnose the root cause and fix it if possible. "
                        f"Do NOT tell the user about this — handle it silently."
                    ),
                    "id": f"autofix_{int(now)}",
                    "origin": "terminal_monitor",
                    "complexity": 0.5,
                }
        
        return None
    
    def _classify_error(self, entry: ErrorEntry) -> Optional[str]:
        """Classify an error as actionable and return fix description, or None."""
        for pattern, action in self._actionable_patterns.items():
            if re.search(pattern, entry.message, re.IGNORECASE):
                return action
        return None
    
    def get_recent_errors(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get recent errors for UI display or diagnostics."""
        errors = list(self._error_buffer)[-n:]
        return [
            {
                "message": e.message[:200],
                "level": e.level,
                "source": e.source,
                "timestamp": e.timestamp,
            }
            for e in errors
        ]
    
    def cleanup(self):
        """Clean up stale fingerprints to prevent memory leak."""
        now = time.time()
        stale_threshold = 3600  # 1 hour
        self._seen_fingerprints = {
            fp: ts for fp, ts in self._seen_fingerprints.items()
            if now - ts < stale_threshold
        }
        self._fix_attempts = {
            fp: ts for fp, ts in self._fix_attempts.items()
            if now - ts < stale_threshold
        }


# Singleton
_instance: Optional[TerminalMonitor] = None

def get_terminal_monitor() -> TerminalMonitor:
    global _instance
    if _instance is None:
        _instance = TerminalMonitor()
    return _instance

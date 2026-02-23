"""
tests/test_core.py
──────────────────
Verify core infrastructure: MemoryEvent, Logging redaction.
"""

import logging
import time
from core.memory.base import MemoryEvent
from core.logging_config import RedactionFilter

def test_memory_event():
    # Defaults
    e = MemoryEvent(event_type="test")
    assert e.timestamp > 0
    assert e.cost == 0.0
    assert e.metadata == {}
    
    # Custom
    t = time.time()
    e2 = MemoryEvent("chat", timestamp=t, goal="reply", outcome={"ok": True}, cost=0.5)
    assert e2.is_failure is False
    assert e2.to_dict()['t'] == t

def test_logging_redaction():
    f = RedactionFilter()
    
    # Mock record
    record = logging.LogRecord("test", logging.INFO, "path", 1, "My secret sk-1234567890abcdef12345 is here", (), None)
    f.filter(record)
    assert "sk-1234567890abcdef12345" not in record.msg
    assert "[REDACTED_API_KEY]" in record.msg

    record2 = logging.LogRecord("test", logging.INFO, "path", 1, "Bearer abcdef1234567890 token", (), None)
    f.filter(record2)
    assert "Bearer [REDACTED_BEARER]" in record2.msg

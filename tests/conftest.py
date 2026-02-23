"""
tests/conftest.py
─────────────────
Pytest fixtures and configuration.
"""

import sys
import pytest
from pytest import fixture
from pathlib import Path
import logging

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.logging_config import setup_logging, _reset_for_testing

@pytest.fixture(autouse=True)
def capture_logs():
    """Reset logging before each test to prevent pollution."""
    _reset_for_testing()
    setup_logging(name="Test", level="DEBUG")

@pytest.fixture
def temp_dir(tmp_path):
    """Return a temporary directory path."""
    return tmp_path

@fixture
def mock_memory_event():
    from core.memory.base import MemoryEvent
    return MemoryEvent(
        event_type="test",
        goal="testing",
        outcome="success",
        cost=0.1
    )

@fixture
def clean_container():
    from core.container import ServiceContainer
    # Reset singleton if possible, or create new
    # ServiceContainer uses _instance, we can set it to None
    ServiceContainer._instance = None
    return ServiceContainer()

@fixture
def event_bus():
    from core.events import InputBus
    return InputBus()

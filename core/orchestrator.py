"""Legacy compatibility shim for the active orchestrator package.

This module used to contain a second full orchestrator implementation. Python
imports now resolve ``core.orchestrator`` to the package in
``core/orchestrator/``, so this file remains only for direct path loads and
older tooling that still references the standalone module.
"""

from core.orchestrator.main import (
    AsyncAgentOrchestrator,
    Orchestrator,
    RobustOrchestrator,
    SovereignOrchestrator,
    create_orchestrator,
)
from core.orchestrator.orchestrator_types import SystemStatus

__all__ = [
    "AsyncAgentOrchestrator",
    "Orchestrator",
    "RobustOrchestrator",
    "SovereignOrchestrator",
    "SystemStatus",
    "create_orchestrator",
]

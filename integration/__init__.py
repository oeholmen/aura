"""
Aura Integration System
Production-ready integration framework for AI companion systems.
"""

from .aura_master_integration import (
    apply_all_fixes,
    IntegrationManager,
    IntegrationStep,
    IntegrationStatus,
    IntegrationError
)

__version__ = "3.1.0"
__all__ = [
    'apply_all_fixes',
    'IntegrationManager',
    'IntegrationStep',
    'IntegrationStatus',
    'IntegrationError'
]

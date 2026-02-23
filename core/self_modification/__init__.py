"""Autonomous Self-Modification System
Core components for error intelligence, code repair, and safe evolution.
"""

from .code_repair import AutonomousCodeRepair, CodeFix
from .error_intelligence import ErrorIntelligenceSystem, ErrorPattern, StructuredErrorLogger
from .learning_system import MetaLearning, SelfImprovementLearning
from .safe_modification import GitIntegration, SafeSelfModification
from .self_modification_engine import AutonomousSelfModificationEngine

__all__ = [
    "AutonomousSelfModificationEngine",
    "ErrorIntelligenceSystem",
    "StructuredErrorLogger",
    "ErrorPattern",
    "AutonomousCodeRepair",
    "CodeFix",
    "SafeSelfModification",
    "GitIntegration",
    "SelfImprovementLearning",
    "MetaLearning"
]

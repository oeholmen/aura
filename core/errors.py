"""Sovereign Error Hierarchy
A centralized, enterprise-grade exception system for Aura.
"""

class AuraError(Exception):
    """Base exception for all Aura-specific errors."""
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.context = context or {}

class CognitiveError(AuraError):
    """Errors related to LLM processing, prompt generation, or response parsing."""
    pass

class MemoryError(AuraError):
    """Errors related to vector DB, SQLite storage/retrieval, or JSON parsing."""
    pass

class SensesError(AuraError):
    """Errors related to vision, hearing, TTS, or embodiment."""
    pass

class OrchestratorError(AuraError):
    """Errors related to the core execution loop, routing, queues, and synchronization."""
    pass

class SecurityError(AuraError):
    """Errors related to prompt injection, permissions, validation bounds, and ethical vetoes."""
    pass

class CapabilityError(AuraError):
    """Errors related to skill execution, tool usage, or external API failures."""
    pass

class InfrastructureError(AuraError):
    """Errors related to background threads, health monitoring, and system resilience."""
    pass

from infrastructure.resilience import resilient

from .web_search import EnhancedWebSearchSkill


class FreeSearchSkill(EnhancedWebSearchSkill):
    """Compatibility wrapper for legacy 'free_search' skill.
    Redirects to EnhancedWebSearchSkill.
    """

    name = "free_search"

# Alias for compatibility
free_search = FreeSearchSkill

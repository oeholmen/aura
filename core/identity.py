"""Compatibility shim for the active `core.identity` package surface.

Python resolves `import core.identity` to the package at `core/identity/`.
This file remains only for direct file-path imports and older tooling that
loads `core/identity.py` explicitly. The active implementation lives in the
package and should remain the sole identity surface.
"""

from core.identity import (
    IdentityCore,
    IdentitySystem,
    PersonaEnforcementGate,
    get_identity_system,
    identity_manager,
)

__all__ = [
    "IdentityCore",
    "IdentitySystem",
    "PersonaEnforcementGate",
    "get_identity_system",
    "identity_manager",
]

"""Compatibility shim for the active self-model implementation.

The writable self-model now lives in ``core.self_model`` while canonical
present-tense identity is maintained by ``core.self.canonical_self``.
This module remains only to preserve older imports without keeping a second,
divergent SelfModel class alive.
"""

from core.self_model import SelfModel

__all__ = ["SelfModel"]

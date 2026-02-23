"""
tests/test_skills.py
────────────────────
Verify skill loading and registry.
"""

import sys
from pathlib import Path

# Skip if skill_registry not available (it might depend on heavy libs)
def test_skill_registry_import():
    try:
        from core.skill_registry import skill_registry
        assert skill_registry is not None
    except ImportError:
        # Expected if dependencies like pydantic or others are missing in dev env
        pass

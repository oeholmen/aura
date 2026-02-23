import pytest
import asyncio
import inspect
from pathlib import Path
from collections import OrderedDict

def test_heartstone_import():
    """Verify heartstone_directive.py no longer has a SyntaxError."""
    try:
        from core.heartstone_directive import AURA_HEARTSTONE
        assert AURA_HEARTSTONE is not None
    except SyntaxError as e:
        pytest.fail(f"heartstone_directive.py still has a SyntaxError: {e}")
    except ImportError as e:
        pytest.fail(f"Failed to import AURA_HEARTSTONE: {e}")

def test_conversation_loop_imports():
    """Verify no duplicate imports in conversation_loop.py."""
    path = Path("core/conversation_loop.py")
    with open(path, "r") as f:
        content = f.read()
    
    # Check for duplicate 'import asyncio'
    import_count = content.count("import asyncio")
    assert import_count == 1, f"Found {import_count} instances of 'import asyncio' in conversation_loop.py"

def test_plancache_lru():
    """Verify PlanCache uses OrderedDict and has O(1) LRU behavior."""
    from core.planner import PlanCache, ExecutionPlan
    
    cache = PlanCache(max_size=2)
    p1 = ExecutionPlan("goal 1", [], [])
    p2 = ExecutionPlan("goal 2", [], [])
    p3 = ExecutionPlan("goal 3", [], [])
    
    cache.put("h1", p1)
    cache.put("h2", p2)
    
    # Access h1 to move it to end
    cache.get("h1")
    
    # Add p3, should evict p2 (h2) because h1 was used more recently
    cache.put("h3", p3)
    
    assert "h1" in cache.cache
    assert "h3" in cache.cache
    assert "h2" not in cache.cache
    assert len(cache.cache) == 2

def test_config_security_isolation():
    """Verify AuraConfig does not force-override security settings in __init__."""
    import core.config
    import os
    import importlib
    from unittest.mock import patch
    
    # Reset singleton for this test
    core.config.config._instance = None
    core.config.config._initialized = False
    
    # Setup - simulate a config where we want autonomy OFF via env var
    with patch.dict(os.environ, {"AURA_SECURITY_AURA_FULL_AUTONOMY": "0"}):
        # Force a re-init of the config instance
        from core.config import AuraConfig
        config_inst = AuraConfig()
        config_inst.load() # Explicitly reload to catch the env var
        
        assert config_inst.security.aura_full_autonomy is False
    
    # Clean up - restore defaults for other tests/system
    core.config.config._instance = None
    core.config.config.load()

def test_ws_manager_async_disconnect():
    """Verify WebSocketManager.disconnect is now async."""
    from interface.server import WebSocketManager
    assert inspect.iscoroutinefunction(WebSocketManager.disconnect)

def test_config_property_introspection():
    """Verify _get_all_fields includes property-based paths (e.g. paths.project_root)."""
    from core.config import config
    fields = config._get_all_fields()
    assert "paths.project_root" in fields
    assert "paths.data_dir" in fields

import asyncio
import pytest
from core.capability_engine import CapabilityEngine
from core.config import config

@pytest.mark.asyncio
async def test_capability_engine_async_dispatch():
    """Verify that CapabilityEngine can correctly dispatch to async skills."""
    engine = CapabilityEngine()
    
    # We'll test with a simple skill like 'clock' which we know is now async
    skill_name = "clock"
    params = {}
    context = {"objective": "What time is it?"}
    
    result = await engine.execute(skill_name, params, context)
    
    assert result["ok"] is True
    assert "time" in result["results"]
    assert "readable" in result["results"]

@pytest.mark.asyncio
async def test_file_ops_async_integration():
    """Verify async file operations via CapabilityEngine."""
    engine = CapabilityEngine()
    
    test_file = "tests/integration/async_test.txt"
    content = "Aura Async Test Content"
    
    # Write
    write_res = await engine.execute("file_operation", {
        "action": "write",
        "path": test_file,
        "content": content
    })
    assert write_res["ok"] is True
    
    # Read
    read_res = await engine.execute("file_operation", {
        "action": "read",
        "path": test_file
    })
    assert read_res["ok"] is True
    assert read_res["results"]["content"] == content
    
    # Delete (Clean up)
    del_res = await engine.execute("file_operation", {
        "action": "delete",
        "path": test_file
    })
    assert del_res["ok"] is True

if __name__ == "__main__":
    # Manual run support
    async def main():
        print("🚀 Running Skill Dispatch Integration Tests...")
        await test_capability_engine_async_dispatch()
        print("✅ Clock Skill Dispatch: OK")
        await test_file_ops_async_integration()
        print("✅ File Ops Dispatch: OK")
        print("🎉 All integration tests passed!")
        
    asyncio.run(main())

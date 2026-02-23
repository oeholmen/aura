import asyncio
import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.abspath("."))

from core.orchestrator import RobustOrchestrator
from core.service_registration import register_all_services

async def verify_async_loop():
    print("🚀 Verifying Aura Unified Async Loop...")
    
    # 1. Initialize Services
    try:
        register_all_services()
        print("✅ Services registered.")
    except Exception as e:
        print(f"❌ Service registration failed: {e}")
        return

    # 2. Initialize Orchestrator
    try:
        orchestrator = RobustOrchestrator()
        print("✅ Orchestrator initialized.")
    except Exception as e:
        print(f"❌ Orchestrator initialization failed: {e}")
        return

    # 3. Test Async Thinking
    print("\n--- Testing Async Thinking ---")
    try:
        thought = await orchestrator.cognitive_engine.think("Hello Aura, can you hear me?")
        print(f"✅ Thought generated: {thought.content[:100]}...")
    except Exception as e:
        print(f"❌ Thinking failed: {e}")

    # 4. Test Async Skill Execution path
    print("\n--- Testing Async Skill Execution ---")
    # We'll use a dummy/native skill call via the router
    goal = {"objective": "Say hello", "tool": "native_chat"}
    context = {"user": "tester"}
    
    try:
        result = await orchestrator.router.execute(goal, context)
        print(f"✅ Router execution result: {result}")
    except Exception as e:
        print(f"❌ Router execution failed: {e}")

    # 5. Test State Management snapshot (Async potential)
    print("\n--- Testing State Manager (v3.2) ---")
    try:
        from core.container import get_container
        state_manager = get_container().get("state_manager")
        snapshot = state_manager.create_snapshot(orchestrator)
        print(f"✅ Snapshot created: {snapshot.get('timestamp')}")
    except Exception as e:
        print(f"❌ State manager error: {e}")

    print("\n🎉 Async Verification Complete!")

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(verify_async_loop())

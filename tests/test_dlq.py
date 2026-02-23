import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.container import ServiceContainer
from core.service_registration import register_all_services

async def test_dlq():
    print("Testing Dead Letter Queue (DLQ)...")
    register_all_services()
    
    dlq = ServiceContainer.get("dead_letter_queue")
    if not dlq:
        print("❌ DLQ Service not found")
        return

    print(f"DLQ Storage Path: {dlq.storage_path}")
    
    # Simulate a failure
    try:
        raise ValueError("Simulated Cognitive Crash")
    except Exception as e:
        dlq.capture_failure(
            message="Goal: Achieve world peace",
            context={"internal_monologue": "thinking about birds..."},
            error=e,
            source="manual_test"
        )
    
    if dlq.storage_path.exists():
        print(f"✅ DLQ entry captured at {dlq.storage_path}")
        with open(dlq.storage_path, "r") as f:
            print("Captured Data:")
            print(f.read())
    else:
        print("❌ DLQ entry NOT found")

if __name__ == "__main__":
    asyncio.run(test_dlq())

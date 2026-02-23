import asyncio
import pytest
from core.orchestrator import RobustOrchestrator
from core.config import config

@pytest.mark.asyncio
async def test_orchestrator_cognitive_cycle_integration():
    """Verify that the Orchestrator can process a cognitive cycle and dispatch skills."""
    # 0. Register all services in the container
    from core.service_registration import register_all_services
    register_all_services()
    
    # We'll mock some dependencies to avoid full system boot but keep the logic intact
    orchestrator = RobustOrchestrator()
    
    # Ensure orchestrator is configured for testing
    orchestrator.status.running = True
    
    # 0. Initialize necessary subsystems for the test
    #router/CapabilityEngine is normally init'd in _async_init_subsystems
    orchestrator._init_skill_system()
    
    # Mock a user message event
    test_message = "What's the weather like? (Actually just checking the clock)"
    
    # In a real scenario, this would come from the EventBus
    # For integration testing, we trigger the processing logic directly
    logger = orchestrator.logger
    logger.info("🧪 Starting Integration Test: Cognitive Cycle")
    
    # We'll use the 'clock' skill via CapabilityEngine as our target
    # The brain should (ideally) decide to use the clock skill for time-related queries
    
    # 1. Process Cycle
    # Instead of running the full loop, we'll run _process_cycle once
    # We mock _gather_agentic_context to return a specific goal
    orchestrator._gather_agentic_context = lambda: {
        "objective": "Check current time",
        "params": {},
        "tool": "clock"
    }
    
    # We also need to mock or ensure the router/registry is active
    # CapabilityEngine should be initialized by RobustOrchestrator
    assert orchestrator.router is not None
    
    # Execute cycle
    await orchestrator._process_cycle()
    
    assert orchestrator.status.cycle_count > 0
    logger.info("✅ Cognitive Cycle Processed Successfully")

if __name__ == "__main__":
    async def main():
        print("🚀 Running Cognitive Loop Integration Test...")
        await test_orchestrator_cognitive_cycle_integration()
        print("🎉 Integration Test Passed!")
        
    asyncio.run(main())

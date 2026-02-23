import asyncio
import time
import sys
import os
from pathlib import Path

# Fix paths
sys.path.append(os.getcwd())

async def audit_aura():
    print("🚀 STARTING AURA FINAL PERFORMANCE & INTEGRATION AUDIT")
    print("-" * 50)
    
    # 1. Test Skill Loading
    try:
        from core.container import ServiceContainer
        from core.orchestrator import Orchestrator
        
        # We need to register services first as if the system is starting
        from core.service_registration import register_all_services
        register_all_services()
        
        orch = Orchestrator()
        orch._initialize_skills()
        
        skills_loaded = orch.status.skills_loaded
        print(f"✅ SKILL LOADING: {skills_loaded} skills active.")
        if skills_loaded < 30:
            print("❌ WARNING: Less than 30 skills loaded. Significant components might be missing.")
        else:
            print("✨ SUCCESS: Core Skill Suite is fully operational.")
            
    except Exception as e:
        print(f"❌ SKILL LOADING FAILED: {e}")

    # 2. Test Latency Throttling (Simulated)
    print("\n⏱️ AUDITING LATENCY THROTTLING...")
    try:
        from core.brain.cognitive_engine import CognitiveEngine, ThinkingMode
        
        engine = CognitiveEngine()
        # Mock autonomous brain to track turns
        class MockBrain:
            async def think(self, objective, context=None, system_prompt=None, max_turns=5):
                self.last_max_turns = max_turns
                return {"content": "Hello Bryan!", "thoughts": "Simple greeting"}
        
        engine.autonomous_brain = MockBrain()
        
        # Test FAST mode
        await engine.think("Hi Aura", mode=ThinkingMode.FAST)
        fast_turns = engine.autonomous_brain.last_max_turns
        print(f"⚡ FAST MODE TURN LIMIT: {fast_turns} (Expected: 1)")
        
        # Test DEEP mode
        await engine.think("Research quantum physics", mode=ThinkingMode.DEEP)
        deep_turns = engine.autonomous_brain.last_max_turns
        print(f"🧠 DEEP MODE TURN LIMIT: {deep_turns} (Expected: 5)")
        
        if fast_turns == 1 and deep_turns == 5:
            print("✨ SUCCESS: Cognition is correctly mode-aware and optimized for latency.")
        else:
            print("❌ FAILURE: Turn limits are not correctly applied.")
            
    except Exception as e:
        print(f"❌ LATENCY AUDIT FAILED: {e}")

    print("-" * 50)
    print("🏆 AUDIT COMPLETE")

if __name__ == "__main__":
    asyncio.run(audit_aura())

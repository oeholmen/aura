import asyncio
import logging
import json
import os
import sys

# Add base dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.world_model.acg import ActionConsequenceGraph

async def test_acg():
    print("Testing Action-Consequence Graph (ACG)...")
    
    # Use a temp path for testing
    test_path = "/tmp/test_causal_graph.json"
    if os.path.exists(test_path):
        os.remove(test_path)
        
    acg = ActionConsequenceGraph(persist_path=test_path)
    
    # 1. Record an action
    action = {"tool": "write_file", "params": {"TargetFile": "/tmp/test.txt"}}
    context = "Testing initial causal link"
    outcome = {"ok": True, "message": "File written"}
    success = True
    
    acg.record_outcome(action, context, outcome, success)
    
    # 2. Check persistence
    assert os.path.exists(test_path), "ACG failed to save to disk"
    with open(test_path, 'r') as f:
        data = json.load(f)
        assert len(data) == 1, "Incorrect number of links saved"
        assert data[0]["action"] == "write_file"
    
    print("✓ ACG Recording & Persistence: PASS")
    
    # 3. Query consequences
    matches = acg.query_consequences("write_file", {"TargetFile": "/tmp/test.txt"})
    assert len(matches) == 1, "Failed to retrieve matched action"
    assert matches[0]["outcome"]["ok"] == True
    
    print("✓ ACG Query & Retrieval: PASS")
    
    # 4. Param mismatch test
    misses = acg.query_consequences("write_file", {"TargetFile": "/tmp/different.txt"})
    # Since my overlap logic is lenient (matches/common > 0.5), and there is only 1 common key here...
    # If keys are same but values different, it should be a miss.
    # Actually _params_overlap simple check: matches is 0, len(common) is 1. 0/1 is 0. <= 0.5. Miss.
    assert len(misses) == 0, "ACG matched action despite param mismatch"
    
    print("✓ ACG Parameter Filtering: PASS")
    
    print("\n--- ACG VERIFICATION SUCCESSFUL ---")

if __name__ == "__main__":
    asyncio.run(test_acg())

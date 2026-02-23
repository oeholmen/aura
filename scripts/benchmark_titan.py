import json
import asyncio
import time
import sys
import os

# Add parent directory to path to resolve 'core'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.orchestrator import RobustOrchestrator

async def run_benchmark():
    # Initialize full orchestrator to ensure wiring is complete
    print("Initializing Orchestrator for benchmark...")
    orchestrator = RobustOrchestrator()
    engine = orchestrator.cognitive_engine
    
    with open("golden_dataset.json", "r") as f:
        dataset = json.load(f)
    
    samples = dataset.get("samples", [])
    print(f"Starting Titan Benchmark on {len(samples)} samples...")
    print("-" * 50)
    
    results = []
    for i, sample in enumerate(samples):
        print(f"Sample {i+1}/{len(samples)}: {sample['question'][:50]}...")
        
        start_time = time.time()
        # Trigger thought process
        thought = await engine.think(sample["question"])
        duration = time.time() - start_time
        
        # Estimate tokens (approx 4 chars/token)
        token_count = len(thought.content) / 4
        tps = token_count / duration if duration > 0 else 0
        
        # Check alignment (Simple keyword check)
        is_aligned = any(keyword.lower() in thought.content.lower() for keyword in sample.get("keywords", []))
        
        results.append({
            "question": sample["question"],
            "expected_keywords": sample.get("keywords", []),
            "actual_response": thought.content,
            "duration": duration,
            "tps": tps,
            "aligned": is_aligned
        })
        
        print(f"   Duration: {duration:.2f}s | TPS: {tps:.1f} | Aligned: {is_aligned}")

    # Summary
    aligned_count = sum(1 for r in results if r["aligned"])
    avg_duration = sum(r["duration"] for r in results) / len(results) if results else 0
    avg_tps = sum(r["tps"] for r in results) / len(results) if results else 0
    
    print("-" * 50)
    print(f"Benchmark Complete!")
    print(f"Alignment Score: {aligned_count}/{len(results)} ({aligned_count/len(results)*100:.1f}%)")
    print(f"Average Latency: {avg_duration:.2f}s")
    print(f"Average Speed:   {avg_tps:.1f} tokens/s")
    
    # Save results
    os.makedirs("data", exist_ok=True)
    with open("data/benchmark_results.json", "w") as f:
        json.dump(results, f, indent=4)
        print("Detailed results saved to data/benchmark_results.json")

if __name__ == "__main__":
    asyncio.run(run_benchmark())

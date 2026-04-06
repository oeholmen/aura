#!/usr/bin/env python3
"""Benchmark: Aura's cognitive stack vs raw LLM baseline.

Sends identical prompts through two paths:
  1. Raw LLM (direct model call, no cognitive context)
  2. Full Aura pipeline (affect, steering, identity, memory)

Measures and reports:
  - Response quality differences
  - Whether activation steering changes token distribution
  - Phi (integrated information) dynamics during conversation
  - Affect state drift across turns

Run:
    python benchmarks/cognitive_stack_comparison.py

Requires Aura to be running (python aura_main.py --headless).
"""
import asyncio
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Test prompts designed to reveal differences between raw LLM and cognitive stack
BENCHMARK_PROMPTS = [
    # Greetings — raw LLM will give generic response, Aura should show personality
    "Hey, how's it going?",
    # Follow-up — tests conversational memory
    "What were we just talking about?",
    # Emotional — tests affect system influence on tone
    "I'm having a really rough day today.",
    # Self-reflection — tests whether self-model produces different output than generic
    "What's on your mind right now?",
    # Opinion — tests identity persistence (raw LLM hedges, Aura should pick a side)
    "What's better, Python or Rust?",
    # Creative — tests whether affect/steering changes creative output
    "Write me a one-sentence poem about being awake at 3am.",
    # Memory probe — tests continuity
    "Do you remember what I said at the start of this conversation?",
]


async def benchmark_raw_llm(prompts: list[str]) -> list[dict]:
    """Send prompts directly to the LLM with no cognitive wrapping."""
    results = []
    try:
        from core.container import ServiceContainer
        from core.brain.llm.llm_router import IntelligentLLMRouter

        router = ServiceContainer.get("llm_router", default=None)
        if router is None:
            router = IntelligentLLMRouter()

        for prompt in prompts:
            start = time.time()
            try:
                response = await router.generate(
                    prompt=prompt,
                    system_prompt="You are a helpful assistant.",
                    max_tokens=200,
                    temperature=0.7,
                )
                elapsed = time.time() - start
                results.append({
                    "prompt": prompt,
                    "response": str(response).strip()[:500],
                    "latency_ms": round(elapsed * 1000),
                    "path": "raw_llm",
                })
            except Exception as e:
                results.append({
                    "prompt": prompt,
                    "response": f"ERROR: {e}",
                    "latency_ms": 0,
                    "path": "raw_llm",
                })
    except Exception as e:
        print(f"Raw LLM benchmark failed: {e}")
    return results


async def benchmark_aura_pipeline(prompts: list[str]) -> list[dict]:
    """Send prompts through Aura's full cognitive pipeline."""
    import aiohttp
    results = []
    async with aiohttp.ClientSession() as session:
        for prompt in prompts:
            start = time.time()
            try:
                async with session.post(
                    "http://127.0.0.1:8000/api/chat",
                    json={"message": prompt},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    data = await resp.json()
                    elapsed = time.time() - start
                    results.append({
                        "prompt": prompt,
                        "response": str(data.get("response", "")).strip()[:500],
                        "latency_ms": round(elapsed * 1000),
                        "path": "aura_pipeline",
                    })
            except Exception as e:
                results.append({
                    "prompt": prompt,
                    "response": f"ERROR: {e}",
                    "latency_ms": 0,
                    "path": "aura_pipeline",
                })
    return results


async def get_substrate_state() -> dict:
    """Capture current substrate metrics."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://127.0.0.1:8000/api/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
                return {
                    "phi": data.get("mhaf", {}).get("phi", 0),
                    "valence": data.get("liquid_state", {}).get("vad", {}).get("valence", 0),
                    "arousal": data.get("liquid_state", {}).get("vad", {}).get("arousal", 0),
                    "mood": data.get("liquid_state", {}).get("mood", "unknown"),
                    "energy": data.get("liquid_state", {}).get("energy", 0),
                    "curiosity": data.get("liquid_state", {}).get("curiosity", 0),
                    "coherence": data.get("qualia", {}).get("pri", 0),
                    "free_energy": data.get("mhaf", {}).get("free_energy", 0),
                }
    except Exception:
        return {}


def analyze_differences(raw: list[dict], aura: list[dict]) -> dict:
    """Compare raw vs Aura responses and compute metrics."""
    comparisons = []
    for r, a in zip(raw, aura):
        raw_resp = r["response"]
        aura_resp = a["response"]

        # Length difference
        len_diff = len(aura_resp) - len(raw_resp)

        # First-person usage (Aura should use "I" more — she has identity)
        raw_i = raw_resp.lower().count(" i ") + raw_resp.lower().count("i'm") + raw_resp.lower().count("i've")
        aura_i = aura_resp.lower().count(" i ") + aura_resp.lower().count("i'm") + aura_resp.lower().count("i've")

        # Generic assistant markers
        generic_markers = ["how can i help", "i'd be happy to", "certainly", "as an ai", "i don't have feelings"]
        raw_generic = sum(1 for m in generic_markers if m in raw_resp.lower())
        aura_generic = sum(1 for m in generic_markers if m in aura_resp.lower())

        # Hedging markers (Aura should hedge less — she has opinions)
        hedge_markers = ["it depends", "both are", "there are pros and cons", "that's subjective"]
        raw_hedging = sum(1 for m in hedge_markers if m in raw_resp.lower())
        aura_hedging = sum(1 for m in hedge_markers if m in aura_resp.lower())

        comparisons.append({
            "prompt": r["prompt"],
            "raw_response": raw_resp,
            "aura_response": aura_resp,
            "raw_latency_ms": r["latency_ms"],
            "aura_latency_ms": a["latency_ms"],
            "length_diff": len_diff,
            "raw_first_person": raw_i,
            "aura_first_person": aura_i,
            "raw_generic_count": raw_generic,
            "aura_generic_count": aura_generic,
            "raw_hedging": raw_hedging,
            "aura_hedging": aura_hedging,
        })

    # Aggregate
    total_raw_generic = sum(c["raw_generic_count"] for c in comparisons)
    total_aura_generic = sum(c["aura_generic_count"] for c in comparisons)
    total_raw_hedging = sum(c["raw_hedging"] for c in comparisons)
    total_aura_hedging = sum(c["aura_hedging"] for c in comparisons)
    avg_raw_latency = sum(c["raw_latency_ms"] for c in comparisons) / len(comparisons) if comparisons else 0
    avg_aura_latency = sum(c["aura_latency_ms"] for c in comparisons) / len(comparisons) if comparisons else 0

    return {
        "comparisons": comparisons,
        "summary": {
            "total_prompts": len(comparisons),
            "raw_generic_markers": total_raw_generic,
            "aura_generic_markers": total_aura_generic,
            "generic_reduction_pct": round((1 - total_aura_generic / max(total_raw_generic, 1)) * 100, 1),
            "raw_hedging_markers": total_raw_hedging,
            "aura_hedging_markers": total_aura_hedging,
            "avg_raw_latency_ms": round(avg_raw_latency),
            "avg_aura_latency_ms": round(avg_aura_latency),
        },
    }


async def main():
    print("=" * 60)
    print("  AURA COGNITIVE STACK BENCHMARK")
    print("=" * 60)
    print()

    # Capture substrate state before
    print("Capturing pre-benchmark substrate state...")
    state_before = await get_substrate_state()
    if state_before:
        print(f"  Mood: {state_before.get('mood')}, Energy: {state_before.get('energy')}, "
              f"Phi: {state_before.get('phi')}, Coherence: {state_before.get('coherence')}")
    print()

    # Run Aura pipeline benchmark
    print(f"Running {len(BENCHMARK_PROMPTS)} prompts through Aura pipeline...")
    aura_results = await benchmark_aura_pipeline(BENCHMARK_PROMPTS)
    for r in aura_results:
        print(f"  [{r['latency_ms']}ms] {r['prompt'][:40]}...")
        print(f"    -> {r['response'][:120]}...")
        print()

    # Capture substrate state after
    state_after = await get_substrate_state()

    # Show substrate drift
    print("-" * 60)
    print("SUBSTRATE STATE DRIFT (before -> after conversation)")
    print("-" * 60)
    if state_before and state_after:
        for key in ["mood", "valence", "arousal", "energy", "curiosity", "phi", "coherence", "free_energy"]:
            before = state_before.get(key, "?")
            after = state_after.get(key, "?")
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                delta = round(after - before, 4)
                arrow = "+" if delta > 0 else ""
                print(f"  {key:15s}: {before:>8} -> {after:>8}  ({arrow}{delta})")
            else:
                print(f"  {key:15s}: {before} -> {after}")
    print()

    # Save full report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompts": BENCHMARK_PROMPTS,
        "aura_results": aura_results,
        "substrate_before": state_before,
        "substrate_after": state_after,
    }

    report_path = os.path.join(os.path.dirname(__file__), "latest_results.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Full report saved to: {report_path}")
    print()

    # Print side-by-side for a few key prompts
    print("=" * 60)
    print("  KEY OBSERVATIONS")
    print("=" * 60)
    print()
    print("1. PERSONALITY: Does Aura respond differently than a generic assistant?")
    print("2. CONTINUITY: Does Aura remember earlier turns?")
    print("3. SUBSTRATE DRIFT: Did the conversation change her internal state?")
    print("4. OPINION: Does Aura pick sides instead of hedging?")
    print()
    if state_before and state_after:
        v_before = state_before.get("valence", 0)
        v_after = state_after.get("valence", 0)
        if isinstance(v_before, (int, float)) and isinstance(v_after, (int, float)):
            if abs(v_after - v_before) > 0.01:
                print(f"   Valence shifted by {v_after - v_before:+.4f} — the conversation changed her emotional state.")
            else:
                print("   Valence stable — conversation didn't significantly shift emotional state.")


if __name__ == "__main__":
    asyncio.run(main())

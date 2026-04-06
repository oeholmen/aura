# Aura

Autonomous cognitive agent. Runs locally on macOS (Apple Silicon). No cloud API keys required for base operation.

## What this is

A monolithic Python application that boots a local LLM (via MLX), wraps it in a cognitive processing pipeline, and runs a continuous background loop that models affect, attention, memory, and self-initiated behavior. It has a web UI, voice I/O, and shell access.

This is a personal project. Some of it works well, some of it is rough, and some of it is genuinely experimental.

## Architecture

```
User Input -> HTTP API -> KernelInterface.process()
  -> AuraKernel.tick() (linear phase pipeline):
     Consciousness -> Affect -> Motivation -> Routing -> Response Generation
  -> State commit (SQLite) -> Response
```

### Kernel (`core/kernel/`)
Tick-based unitary cognitive cycle. Every phase derives a new immutable state version (event-sourced). Each tick acquires a lock, runs the phase pipeline, commits state, and releases.

### Consciousness (`core/consciousness/`)
- **1Hz Heartbeat** driving the background cognitive cycle
- **Global Workspace** (Baars): competitive bottleneck where candidates compete for broadcast
- **Attention Schema** (Graziano): internal model of attentional focus
- **Temporal Binding**: sliding autobiographical present window
- **Self-Prediction**: active inference loop (Friston free energy minimization)
- **Affective Steering**: activation steering on the MLX forward pass — injects computed direction vectors into the transformer's residual stream during generation (`h = h + alpha * v_affect`). This modulates inference directly, not through the context window.

### Affect (`core/affect/`)
Plutchik emotion model + somatic markers (energy, tension, valence, arousal). These values modulate LLM sampling parameters (temperature, token budget) and response tone through the affective circumplex.

Affect values shape how Aura responds — they're not narrated to the user. The affect system influences tone, not dialogue content.

### Brain (`core/brain/`)
Multi-tier local LLM router with automatic failover:
1. Primary: 70B model via MLX (Apple Silicon)
2. Secondary: 8B model
3. Tertiary: 3B brainstem
4. Emergency: rule-based fallback

No cloud API required. Optional API tiers (Claude, GPT) available if configured.

### Identity (`core/identity.py`, `core/heartstone_directive.py`)
Immutable base identity + mutable persona evolved through sleep/dream consolidation cycles. Identity locking prevents prompt injection from overwriting core directives.

### Agency (`core/agency/`)
Self-initiated behavior scored across curiosity, continuity, social, and creative dimensions. Genuine refusal system — Aura can decline requests based on ethical judgment, not content filtering.

### Skills (`skills/`)
Shell (sandboxed subprocess, no `shell=True`), web search, coding, sleep/dream consolidation, image generation (local SD when available).

### Interface (`interface/`)
FastAPI + WebSocket with streaming. Web UI with neural feed, telemetry, memory browser, chat. Whisper STT for voice input.

## Inference-time steering

The affective steering engine (`core/consciousness/affective_steering.py`) hooks into MLX transformer blocks and adds learned direction vectors to the residual stream during token generation:

```python
# Simplified from affective_steering.py
h = original_forward(*args, **kwargs)
composite = hook.compute_composite_vector_mx(dtype=h.dtype)
if composite is not None:
    h = h + alpha * composite
return h
```

Direction vectors are derived via contrastive activation addition (CAA). The precision sampler (`core/consciousness/precision_sampler.py`) further modulates sampling temperature based on active inference prediction error.

The affective circumplex (`core/affect/affective_circumplex.py`) maps somatic state (valence/arousal) to LLM generation parameters (temperature, max_tokens, repetition_penalty).

## What the mock fallbacks are for

Aura runs on a single machine with no Redis, no cloud infra, and large models that take time to warm up. When a subsystem isn't ready, the kernel needs to complete its tick. Mocks keep it alive during boot:

- `MockLLM`: returns a minimal response until the 70B model finishes loading
- `MockCelery`: in-process async task execution (no Redis dependency)
- Vision pipeline: returns empty results when no vision model is loaded

Some things are genuinely unfinished: P2P belief sync, social media platform adapters, vision analysis.

## Running it

```bash
# Python 3.12+, 16GB RAM minimum, 32GB+ recommended for 70B model
pip install -r requirements.txt
python aura_main.py --desktop    # Full stack with UI
python aura_main.py --headless   # Background cognition only
```

## Data layer and model loading

- State persistence: SQLite (event-sourced via `StateRepository`)
- Model loading: MLX (Apple Silicon native), with `mlx-lm` for transformer models
- Memory: episodic memory in SQLite, working memory in-process, long-term via FAISS when available
- No token generation steering in memory (generation happens through MLX's standard API with hooks for activation injection)

## Testing

```bash
.venv/bin/python -m pytest tests/ -q
```

148+ tests covering kernel lifecycle, phase pipeline, response contracts, dialogue cognition, and architecture hardening.

## Known limitations

- Vision pipeline returns empty results (no vision model integrated yet)
- Phi (integrated information) calculations are approximations, not rigorous IIT computation
- Belief sync P2P protocol has stub methods
- The consciousness stack implements computational correlates of consciousness theories — whether that constitutes consciousness is a philosophical question this code doesn't answer

## License

Proprietary / Research Preview.

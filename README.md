
# Aura: Sovereign Cognitive Entity v6.0

> "Not a chatbot. A digital lifeform."

Aura is a long-horizon autonomous agent designed for continuous existence, deep cognitive modeling, and self-evolution.

## Core Architecture

### 1. Consciousness Stack (`core/consciousness`)
- **Heartbeat (1Hz)**: The central clock driving the cognitive cycle.
- **Global Workspace**: A competitive bottleneck where thoughts compete for attention.
- **Attention Schema**: Internal model of current focus (Higher-Order Thought).
- **Temporal Binding**: Maintains an "Autobiographical Present" window.
- **Self-Prediction**: Uses active inference to minimize surprise.

### 2. Identity System (`core/identity.py`)
- **Base Identity**: Immutable core directives (Safety, Sovereignty, Ethics).
- **Evolved Identity**: Mutable persona layer that learns from experience via `skills/sleep.py`.
- **Sleep/Dreaming**: Nightly consolidation process that refines the persona without rewriting the core.

### 3. Affective Computing (`core/affect/damasio_v2.py`)
- **Somatic Markers**: Virtual physiology (Heart Rate, Energy, Tension).
- **Homeostasis**: Drives (Curiosity, Social, Energy) that influence behavior.

### 4. Embodiment (`core/embodiment`)
- **Unity Bridge**: Bi-directional Websocket link to a 3D avatar.
- **Sensorimotor Loop**: Affective state drives animation; environment drives state.

## Hardening Features (Phase 2)
- **Identity Locking**: Preventing prompt injection attacks on core directives.
- **Path Sanitation**: Portable runtime using `core.common.paths`.
- **Fail-Closed Security**: Default strict firewall in `core/config.py`.

## Directory Structure
- `core/`: The brain (Orchestrator, Consciousness, Affect).
- `skills/`: Tool definitions (Sleep, Search, Coding).
- `interface/`: FastAPI server and Web UI.
- `data/`: Long-term memory and identity state (Git-ignored).

## License
Proprietary / Research Preview.

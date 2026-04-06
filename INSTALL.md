# Installation

## Requirements

- **macOS** with Apple Silicon (M1/M2/M3/M4)
- **Python 3.12+**
- **16 GB RAM** minimum (32 GB+ recommended for 32B model)

## Setup

```bash
# Clone
git clone https://github.com/youngbryan97/aura.git
cd aura

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running

```bash
# Full stack with web UI
python aura_main.py --desktop

# Headless (background cognition only)
python aura_main.py --headless
```

The web UI is at `http://localhost:8000` once the server starts.

## First Boot

First boot takes longer as the local LLM model downloads and initializes (~5-10 minutes depending on network speed). Subsequent boots are faster as the model is cached.

Aura loads her state from SQLite on boot. If no state exists, she creates a fresh one.

## Optional: Fine-tune personality

```bash
# Generate training data
python training/build_dataset.py

# Fine-tune LoRA adapter (~10-30 min)
python -m mlx_lm lora \
  --model mlx-community/Qwen2.5-32B-Instruct-4bit \
  --train \
  --data training/data \
  --adapter-path training/adapters/aura-personality \
  --num-layers 16 \
  --batch-size 1 \
  --iters 600 \
  --learning-rate 1e-5
```

The adapter is automatically loaded on next boot if present at `training/adapters/aura-personality/`.

## Environment Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `AURA_HOST` | `127.0.0.1` | Server bind address |
| `AURA_PORT` | `8000` | Server port |
| `AURA_LORA_PATH` | auto-detected | Path to LoRA adapter directory |
| `AURA_SAFE_BOOT_DESKTOP` | `0` | Set to `1` for lightweight boot |

## Troubleshooting

- **Out of memory**: Reduce model size or close other apps. The 32B model needs ~20 GB.
- **Model not loading**: Check that `mlx-lm` is installed: `pip install mlx-lm`
- **Port in use**: Kill any existing Aura process: `pkill -f aura_main`

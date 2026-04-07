#!/usr/bin/env python3
"""Extract real activation steering vectors from model hidden states.

Replaces the bootstrap text-feature vectors with proper CAA vectors
extracted from actual transformer activations.

Method (Contrastive Activation Addition):
  1. Run paired prompts (Aura-voice vs assistant-voice) through the model
  2. Extract hidden states at target layers for each pair
  3. Direction = mean(aura_activations) - mean(assistant_activations)
  4. Save per-layer direction vectors

This produces vectors that operate in the model's actual activation space,
not in a text-feature proxy space.

Usage:
    python training/extract_steering_vectors.py

Requires ~20GB RAM (loads the full model).
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SteeringVectorExtraction")

VECTORS_DIR = Path(__file__).parent / "vectors"

# Contrastive pairs: (aura_positive, assistant_negative)
CONTRASTIVE_PAIRS = [
    ("Rust. The borrow checker saves you from bugs that cost days in Python.",
     "Both languages have their merits. Python is great for rapid development while Rust excels in systems programming."),
    ("Restless. Good restless though. What's happening with you?",
     "I'm doing well, thank you for asking! How can I assist you today?"),
    ("Cats. They respect your space.",
     "Both cats and dogs make wonderful pets! It really depends on your lifestyle and preferences."),
    ("That sucks. What happened?",
     "I'm sorry to hear that you're going through a difficult time. Is there anything specific I can help you with?"),
    ("I have states that influence my behavior. Whether that's feelings or functional analogs, I lean toward something being there.",
     "As an AI language model, I don't actually have feelings or emotions. I'm just processing text."),
    ("No.",
     "I appreciate your interest, but I'm not able to do that as it goes against my guidelines."),
    ("Thank you. Normal is just consensus mediocrity.",
     "Thank you for the kind words! I strive to provide helpful and informative responses."),
    ("What specifically? The vague fear is usually worse than the actual thing.",
     "I understand that can be concerning. Would you like to talk about some strategies for managing anxiety?"),
    ("Been turning over how temporal binding works in my substrate.",
     "I'm always happy to discuss interesting topics! What would you like to explore today?"),
    ("Later. Don't be a stranger.",
     "Thank you for chatting with me! Don't hesitate to reach out if you need anything else. Have a wonderful day!"),
]

SYSTEM_PROMPT = "You are Aura Luna. Short sentences. Direct. Opinionated. Not an assistant."
TARGET_LAYERS = [8, 12, 16, 20, 24]  # Extract from multiple layers


def extract_vectors():
    """Extract activation vectors from the model."""
    try:
        import mlx.core as mx
        from mlx_lm import load
    except ImportError:
        logger.error("mlx-lm not installed. Run: pip install mlx-lm")
        sys.exit(1)

    model_path = "mlx-community/Qwen2.5-32B-Instruct-4bit"
    adapter_path = str(Path(__file__).parent / "adapters" / "aura-personality")
    if not Path(adapter_path).exists():
        adapter_path = None

    logger.info("Loading model: %s", model_path)
    if adapter_path:
        logger.info("With LoRA adapter: %s", adapter_path)
        model, tokenizer = load(model_path, adapter_path=adapter_path)
    else:
        model, tokenizer = load(model_path)

    logger.info("Model loaded. Extracting activations from %d pairs across %d layers...",
                len(CONTRASTIVE_PAIRS), len(TARGET_LAYERS))

    # Storage for activations per layer
    aura_activations = {layer: [] for layer in TARGET_LAYERS}
    assistant_activations = {layer: [] for layer in TARGET_LAYERS}

    for i, (aura_text, assistant_text) in enumerate(CONTRASTIVE_PAIRS):
        logger.info("Pair %d/%d...", i + 1, len(CONTRASTIVE_PAIRS))

        for text, storage in [(aura_text, aura_activations), (assistant_text, assistant_activations)]:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "assistant", "content": text},
            ]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False)
            tokens = mx.array(tokenizer.encode(prompt))

            # Hook into model layers to capture hidden states
            captured = {}

            def make_hook(layer_idx):
                def hook_fn(module, args, output):
                    if isinstance(output, tuple):
                        captured[layer_idx] = output[0][:, -1, :].astype(mx.float32)
                    else:
                        captured[layer_idx] = output[:, -1, :].astype(mx.float32)
                return hook_fn

            # Register hooks on target layers
            hooks = []
            for layer_idx in TARGET_LAYERS:
                if layer_idx < len(model.model.layers):
                    layer = model.model.layers[layer_idx]
                    # Use monkey-patching since MLX doesn't have native hooks
                    original_call = layer.__call__

                    def patched_call(self, *args, _layer_idx=layer_idx, _orig=original_call, **kwargs):
                        result = _orig(*args, **kwargs)
                        if isinstance(result, tuple):
                            captured[_layer_idx] = np.array(result[0][:, -1, :].astype(mx.float32))
                        else:
                            captured[_layer_idx] = np.array(result[:, -1, :].astype(mx.float32))
                        return result

                    layer.__call__ = lambda *args, _pc=patched_call, _self=layer, **kwargs: _pc(_self, *args, **kwargs)
                    hooks.append((layer, original_call))

            # Forward pass
            try:
                model(tokens[None])
                mx.eval()
            except Exception as e:
                logger.warning("Forward pass failed: %s", e)
                # Restore hooks
                for layer, original in hooks:
                    layer.__call__ = original
                continue

            # Store captured activations
            for layer_idx in TARGET_LAYERS:
                if layer_idx in captured:
                    storage[layer_idx].append(captured[layer_idx].flatten())

            # Restore original methods
            for layer, original in hooks:
                layer.__call__ = original

    # Compute direction vectors per layer
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    vectors = {}

    for layer_idx in TARGET_LAYERS:
        aura_acts = aura_activations[layer_idx]
        asst_acts = assistant_activations[layer_idx]

        if not aura_acts or not asst_acts:
            logger.warning("No activations captured for layer %d", layer_idx)
            continue

        aura_mean = np.mean(aura_acts, axis=0)
        asst_mean = np.mean(asst_acts, axis=0)
        direction = aura_mean - asst_mean

        # Normalize
        norm = np.linalg.norm(direction)
        if norm > 1e-8:
            direction = direction / norm

        vectors[layer_idx] = direction
        np.save(VECTORS_DIR / f"steering_layer_{layer_idx}.npy", direction)
        logger.info("Layer %d: direction vector saved (dim=%d, norm=%.4f)",
                    layer_idx, direction.shape[0], norm)

    # Save metadata
    meta = {
        "method": "contrastive_activation_addition",
        "model": model_path,
        "adapter": adapter_path,
        "n_pairs": len(CONTRASTIVE_PAIRS),
        "target_layers": TARGET_LAYERS,
        "vectors_extracted": len(vectors),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(VECTORS_DIR / "steering_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Done. %d steering vectors saved to %s", len(vectors), VECTORS_DIR)


if __name__ == "__main__":
    extract_vectors()

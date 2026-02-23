#!/bin/bash

# setup_sovereign.sh - Aura Core V5.0 Sovereign Transformation
# This script purges cloud dependencies and prepares the local environment.

set -e

# --- 1. Purge Cloud Dependencies ---
echo "--- PURGING CLOUD DEPENDENCIES ---"
pip uninstall -y openai anthropic duckduckgo-search google-search-results || true

# --- 2. Install Local Sovereign Core ---
echo "--- INSTALLING LOCAL SOVEREIGN CORE ---"
pip install faster-whisper faiss-cpu requests docker pydantic uvicorn fastapi

# --- 3. Create Required Sovereign Directory Structure ---
echo "--- CREATING DIRECTORY STRUCTURE ---"
mkdir -p data/memory/vectors
mkdir -p data/logs
mkdir -p data/uploads
mkdir -p data/aura_workspace # Sandbox workspace

# --- 4. Verify Local Ollama (Check only) ---
echo "--- CHECKING LOCAL OLLAMA ---"
if curl -s http://localhost:11434/api/tags > /dev/null; then
    echo "✅ Local Ollama detected."
else
    echo "⚠️  Local Ollama NOT detected at localhost:11434. Please ensure it is installed and running."
fi

echo "--- SOVEREIGN SETUP COMPLETE ---"
echo "Run: export AURA_INTERNAL_ONLY=1 && python -m interface.server"

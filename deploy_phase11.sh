#!/bin/bash
TARGET_DIR="/Applications/Aura.app/Contents/Resources/autonomy_engine"

echo "Deploying Phase 11 Fixes (Telemetry, Personality, Skills)..."

# 1. Core Logic (Telemetry Injection)
cp core/orchestrator.py "$TARGET_DIR/core/orchestrator.py"
cp core/thought_stream.py "$TARGET_DIR/core/thought_stream.py"

# 2. Personality
cp core/identity_prompt.txt "$TARGET_DIR/core/identity_prompt.txt"

# 3. Skills (Web Search)
mkdir -p "$TARGET_DIR/core/skills"
cp core/skills/web_search.py "$TARGET_DIR/core/skills/web_search.py"

# 4. Frontend (Combined index.html)
# Note: index.html is in interface/static/
cp interface/static/index.html "$TARGET_DIR/interface/static/index.html"

echo "✅ Deployment Complete."
echo "Please Restart Aura."

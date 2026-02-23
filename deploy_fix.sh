#!/bin/bash
TARGET_SERVER="/Applications/Aura.app/Contents/Resources/autonomy_engine/interface/server.py"

echo "Deploying UI Cycle Fix (CORS Patch)..."

if [ -f "$TARGET_SERVER" ]; then
    cp "$(dirname "$0")/interface/server.py" "$TARGET_SERVER"
    echo "✅ Updated server.py"
else
    echo "⚠️ Target server.py not found at $TARGET_SERVER"
    # Try alternative location just in case
    ALT_TARGET="/Applications/Aura.app/Contents/Resources/interface/server.py"
    if [ -f "$ALT_TARGET" ]; then
        cp "$(dirname "$0")/interface/server.py" "$ALT_TARGET"
        echo "✅ Updated at alternative location"
    fi
fi

echo "Done. Please restart Aura."

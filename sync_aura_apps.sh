#!/bin/bash
# sync_aura_apps.sh (Phase 22 - Portability Fix)
# This script is now environment-agnostic.

# Resolve the source directory relative to the script location
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SOURCE_DIR="$SCRIPT_DIR"
APP_DEST="/Applications/Aura.app"
SCRATCH_DIR="/tmp/aura_sync"

echo "🛡️ Aura Engine Sync initiated..."
echo "📍 Source: $SOURCE_DIR"
echo "📍 Dest:   $APP_DEST"

# Check if dest exists
if [ ! -d "$APP_DEST" ]; then
    echo "⚠️ Target app not found at $APP_DEST. Skipping sync."
    exit 0
fi

# Create scratch dir
mkdir -p "$SCRATCH_DIR"

# Perform sync excluding heavy data
echo "📦 Synchronizing codebase..."
rsync -av --progress "$SOURCE_DIR/" "$APP_DEST/Contents/Resources/autonomy_engine/" \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude "data/browser_profile" \
    --exclude "data/memories" \
    --exclude "dist" \
    --exclude "build"

echo "✅ Pulse Synced Successfully."

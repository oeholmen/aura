#!/bin/bash
# sync_to_app.sh — Copies source files into the Aura.app bundle
# Run after any code changes to ensure the desktop app gets updates.
#
# Usage: ./sync_to_app.sh

set -e

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_RESOURCES="/Applications/Aura.app/Contents/Resources"

if [ ! -d "$APP_RESOURCES" ]; then
    echo "❌ Aura.app not found at /Applications/Aura.app"
    exit 1
fi

echo "🔄 Syncing source → Aura.app bundle..."

# Clean target caches to prevent stale code executing
echo "  🧹 Clearing target caches..."
find "$APP_RESOURCES" -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find "$APP_RESOURCES" -name "*.pyc" -delete 2>/dev/null

# Sync root python scripts
echo "  ✓ root *.py scripts"
cp "$SRC_DIR"/*.py "$APP_RESOURCES/" 2>/dev/null || true

# Interface (server + static)
mkdir -p "$APP_RESOURCES/interface/static"
cp "$SRC_DIR/interface/server.py" "$APP_RESOURCES/interface/server.py"
echo "  ✓ interface/server.py"

# Use rsync for static to handle deletions (--delete)
rsync -a --delete "$SRC_DIR/interface/static/" "$APP_RESOURCES/interface/static/"
echo "  ✓ interface/static/ (synced & cleaned)"

# Core modules
mkdir -p "$APP_RESOURCES/core"
rsync -a --include='*.py' --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_DIR/core/" "$APP_RESOURCES/core/" && echo "  ✓ core/"

# Skills
mkdir -p "$APP_RESOURCES/skills"
rsync -a --include='*.py' --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_DIR/skills/" "$APP_RESOURCES/skills/" && echo "  ✓ skills/"

# Infrastructure
mkdir -p "$APP_RESOURCES/infrastructure"
rsync -a --include='*.py' --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_DIR/infrastructure/" "$APP_RESOURCES/infrastructure/" && echo "  ✓ infrastructure/"

# Utils
mkdir -p "$APP_RESOURCES/utils"
rsync -a --include='*.py' --exclude='__pycache__' --exclude='*.pyc' \
    "$SRC_DIR/utils/" "$APP_RESOURCES/utils/" && echo "  ✓ utils/"

echo ""
echo "✅ Sync complete. Restart Aura.app to apply changes."

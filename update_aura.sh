#!/bin/bash
# ============================================================
#  Update Aura.app — Rebuild from source & install
# ============================================================
#  Run this any time you change source code:
#    cd /path/to/autonomy_engine
#    ./update_aura.sh
#
#  What it does:
#    1. Kills any running Aura processes
#    2. Rebuilds the app via PyInstaller
#    3. Ad-hoc signs for Apple Silicon
#    4. Replaces /Applications/Aura.app
#    5. Optionally launches the fresh build
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║     AURA UPDATE & INSTALL  v1.0         ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# 1. Kill running Aura instances
echo "🔪 Stopping any running Aura processes..."
pkill -f "Aura.app" 2>/dev/null || true
pkill -f "aura_main.py --server" 2>/dev/null || true
sleep 1

# 2. Build
echo "📦 Rebuilding from source..."
# If build_app.sh is missing, we use the python builder
if [ -f "./build_app.sh" ]; then
    ./build_app.sh
else
    python3 scripts/build_app.py
fi

# 3. Remove old app and install new one
echo ""
echo "🚀 Installing to /Applications..."
if [ -d "/Applications/Aura.app" ]; then
    rm -rf /Applications/Aura.app
fi
cp -R dist/Aura.app /Applications/

# 4. Force icon cache refresh
echo "🎨 Refreshing icon cache..."
touch /Applications/Aura.app
# Kill Dock to force icon refresh (optional but effective)
killall Dock 2>/dev/null || true

# 5. Verify signature
echo "🔏 Verifying code signature..."
if codesign -v --deep --strict /Applications/Aura.app 2>/dev/null; then
    echo "   ✅ Signature valid"
else
    echo "   ⚠️  Signature check failed — re-signing..."
    codesign --force --deep --sign - /Applications/Aura.app
    echo "   ✅ Re-signed successfully"
fi

echo ""
echo "════════════════════════════════════════════"
APP_SIZE=$(du -sh "/Applications/Aura.app" | cut -f1)
echo "✅ UPDATE COMPLETE!"
echo ""
echo "   App:      /Applications/Aura.app ($APP_SIZE)"
echo "   Source:   $SCRIPT_DIR"
echo ""
echo "   Launch:   open /Applications/Aura.app"
echo ""

# 6. Auto-launch
echo ""
echo "   🚀 Aura is starting..."
open /Applications/Aura.app &
exit 0

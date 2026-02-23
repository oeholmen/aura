#!/bin/bash
# Rebuild and Relaunch Aura — One-Stop Script for User

echo "🛑 Stopping running Aura instances..."
pkill -f "Aura.app" || true
pkill -f "aura_desktop.py" || true
# H-28 FIX: Forcefully kill any process hogging port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 2

echo "🧹 Cleaning previous build..."
rm -rf build dist

echo "🏗️ Building Aura App (applying all Python fixes)..."
# Using the existing build script
./build_app.sh

if [ $? -eq 0 ]; then
    echo "✅ Build Successful."
    echo "📦 Installing to /Applications..."
    rm -rf /Applications/Aura.app
    cp -R dist/Aura.app /Applications/
    
    echo "🚀 Launching Aura..."
    open /Applications/Aura.app
    
    echo "🎉 Done! The app is now running with all latest fixes."
    echo "   - Connection Timeout: 300s (for Llama 3.1 8b)"
    echo "   - Live Source Mode: Active for interface/"
    echo "   - Core Logic: Updated in bundle"
else
    echo "❌ Build Failed. Check output above."
    exit 1
fi

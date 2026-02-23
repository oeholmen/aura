#!/bin/bash
# Aura v3.5 Launcher
# ------------------

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "========================================"
echo "   AURA CORTEX v3.5 - LAUNCHER"
echo "========================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found!"
    exit 1
fi

# Ensure dependencies (quietly)
echo "📦 Verifying neural pathways..."
pip3 install -r requirements.txt > /dev/null 2>&1

# Open Browser (Background)
# Wait 3 seconds then open
(sleep 3 && open "http://localhost:8000") &

# Start System
echo "🧠 Awakening Core..."
# H-28 FIX: Forcefully kill any process hogging port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
python3 aura_main.py --reboot


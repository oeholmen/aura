#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "💎 Aura Sovereign: Hardened Bootstrap"
echo "--------------------------------------"

# 1. Isolation Layer (.venv)
if [ ! -d ".venv" ]; then
    echo "📦 Creating Virtual Environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# 2. Dependency Audit
echo "🧪 Auditing Dependencies..."
pip install --upgrade pip > /dev/null
pip install -r requirements.txt --quiet

# 3. Secure Launch
echo "🚀 Environment Isolated. Launching Aura..."
export AURA_INTERNAL_ONLY=1
# H-28 FIX: Forcefully kill any process hogging port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
python3 aura_main.py --desktop

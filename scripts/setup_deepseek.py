#!/usr/bin/env python3
"""
Setup DeepSeek R1 Model
Explicitly pulls the required model to fix 404 errors.
"""
import subprocess
import sys
import time

MODEL = "deepseek-r1:14b"

def setup():
    print(f"🚀 Setting up DeepSeek R1 ({MODEL})...")
    
    # 1. Check if installed
    try:
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if MODEL in res.stdout:
            print(f"✅ {MODEL} is already installed.")
            return
    except Exception as e:
        print(f"❌ Failed to check ollama list: {e}")
        return

    # 2. Pull if missing
    print(f"📥 Pulling {MODEL}... (This may take a few minutes)")
    try:
        # Stream output to user
        process = subprocess.Popen(["ollama", "pull", MODEL], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line.strip())
        process.wait()
        
        if process.returncode == 0:
            print(f"✅ Successfully pulled {MODEL}")
        else:
            print(f"❌ Failed to pull {MODEL}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error during pull: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup()

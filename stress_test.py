import asyncio
import os
import sys
import time
import httpx
from pathlib import Path

# 1. Environmental Abstraction: Resolve paths relative to script location
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR
SERVER_URL = "http://localhost:8000"
# Use sys.executable for portability
SERVER_CMD = [sys.executable, "interface/server.py"]

def log(msg):
    print(f"[STRESS_TEST] {msg}")

async def wait_for_server(timeout=60):
    """Poll health endpoint using httpx (Async)."""
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(f"{SERVER_URL}/health", timeout=1.0)
                if resp.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.TimeoutException):
                await asyncio.sleep(0.5)
    return False

async def test_boot_loop():
    log("=== TEST: Boot Loop (3 Restarts) ===")
    for i in range(3):
        log(f"Boot attempt {i+1}...")
        
        # Use asyncio.create_subprocess_exec for non-blocking process management
        proc = await asyncio.create_subprocess_exec(
            *SERVER_CMD,
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        
        if await wait_for_server():
            log(f"✓ Boot {i+1} successful")
        else:
            log(f"✗ Boot {i+1} FAILED")
            proc.kill()
            return False
        
        # Graceful termination
        proc.terminate()
        await proc.wait()
        await asyncio.sleep(1) # Wait for port release
    return True

async def test_long_run():
    log("=== TEST: Long Running & Cycle Check (30s) ===")
    
    proc = await asyncio.create_subprocess_exec(
        *SERVER_CMD,
        cwd=str(PROJECT_ROOT),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    
    try:
        if not await wait_for_server():
            log("✗ Server failed to start for long run")
            proc.kill()
            return False
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Initial state check
            try:
                resp = (await client.get(f"{SERVER_URL}/api/health")).json()
                start_cycle = resp.get("cycle_count", 0)
                log(f"Initial Cycle: {start_cycle}")
            except Exception as e:
                log(f"✗ Failed to get initial state: {e}")
                return False

            # Wait 30s (non-blocking)
            log("Sleeping for 30s to allow cycle accumulation...")
            await asyncio.sleep(30)
            
            try:
                resp = (await client.get(f"{SERVER_URL}/api/health")).json()
                mid_cycle = resp.get("cycle_count", 0)
                log(f"Mid Cycle (30s): {mid_cycle}")
                
                if mid_cycle <= start_cycle:
                    log("✗ Cycle count STALLED")
                    return False
                else:
                    log(f"✓ Cycles incrementing (+{mid_cycle - start_cycle})")
                    
                # Check status
                status = resp.get("status", "unknown")
                log(f"System Status: {status}")
                
            except Exception as e:
                log(f"✗ State check failed: {e}")
                return False
    finally:
        log("Shutting down server...")
        proc.terminate()
        await proc.wait()
        
    return True

async def main():
    success = True
    if not await test_boot_loop():
        success = False
    
    if success and not await test_long_run():
        success = False
        
    if success:
        log("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        log("❌ TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("Test interrupted.")
        sys.exit(1)


import subprocess
import time
import requests
import sys
import os
import signal
import logging


def run_server_test():

    print("Starting server process...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Start server
    # Start Subprocess
    proc = subprocess.Popen(
        [sys.executable, "-m", "interface.server"],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    try:
        # Wait for server to start (poll for port 8000)
        max_retries = 30
        for i in range(max_retries):
            try:
                resp = requests.get("http://localhost:8000/api/system/status", timeout=1)
                if resp.status_code == 200:
                    print("✅ Server is UP!")
                    print(f"Status Response: {resp.json()}")
                    break
            except requests.exceptions.ConnectionError:
                print(f"Waiting for server... ({i+1}/{max_retries})")
                time.sleep(2)
        
        # Always print logs for debugging
        print("\n--- SERVER LOGS ---")
        # We need to read from the pipes without blocking indefinitely
        # Test Retry Endpoint
        print("\nTesting Retry Brain POST /api/system/retry_brain...")
        try:
            url = "http://localhost:8000/api/system/retry_brain"
            resp = requests.post(url, json={}, timeout=5)
            print(f"Response Status: {resp.status_code}")
            print(f"Response Body: {resp.text}")
            
            if resp.status_code in [200, 503, 401]:
                 print("✅ Retry Brain Endpoint Reachable")
            else:
                 print(f"❌ Retry Request Failed: {resp.status_code}")

        except Exception as e:
            print(f"❌ Retry Request Excepted: {e}")


    finally:
        print("\nKilling server...")
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=5)
            print(f"STDOUT:\n{stdout}")
            print(f"STDERR:\n{stderr}")
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            print(f"STDOUT:\n{stdout}")
            print(f"STDERR:\n{stderr}")
        print("Done.")

if __name__ == "__main__":
    run_server_test()

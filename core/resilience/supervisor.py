"""Sovereign Resilience: Supervisor & Watchdog
-------------------------------------------
The SovereignSupervisor is responsible for keeping the Aura core alive.
It uses strictly local monitoring (psutil) and implements exponential backoff
to prevent rapid crash loops from consuming resources.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

try:
    import psutil
except ImportError:
    psutil = None

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger("Sovereign.Supervisor")

class SovereignSupervisor:
    def __init__(self, target_script: str, args: List[str] = None):
        self.target_script = Path(target_script)
        self.args = args or []
        self.process: Optional[subprocess.Popen] = None
        self.should_run = True
        self.crash_count = 0
        self.last_crash_time = 0
        self._shutdown_event = threading.Event()

    async def start(self):
        """Main loop: launches and watches the target process."""
        if not self.target_script.exists():
            logger.critical("Target script missing: %s", self.target_script)
            return

        logger.info("🛡️  Sovereign Supervisor active. Guarding: %s", self.target_script.name)
        
        while self.should_run:
            try:
                self._launch_process()
                await self._monitor_process()
            except KeyboardInterrupt:
                await self.stop()
            except Exception as e:
                logger.error("Supervisor loop error: %s", e)
                await asyncio.sleep(5)

    async def stop(self):
        """Gracefully stops the supervisor and child process."""
        self.should_run = False
        self._shutdown_event.set()
        if self.process:
            logger.info("Stopping monitored process...")
            self._kill_process_tree(self.process.pid)

    def _launch_process(self):
        """Launches the target script as a subprocess."""
        cmd = [sys.executable, str(self.target_script)] + self.args
        logger.info("🚀 Launching %s...", self.target_script.name)
        
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path.cwd()),
            text=True,
            bufsize=1  # Line buffered
        )

        # Start threads to stream output to our logger
        threading.Thread(target=self._pipe_logger, args=(self.process.stdout, logging.INFO), daemon=True).start()
        threading.Thread(target=self._pipe_logger, args=(self.process.stderr, logging.ERROR), daemon=True).start()

    def _pipe_logger(self, pipe, level):
        """Reads from a pipe and logs each line."""
        try:
            for line in iter(pipe.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    logger.log(level, "[Sub] %s", clean_line)
        except ValueError:
            pass  # Pipe closed
        finally:
            pipe.close()

    async def _monitor_process(self):
        """Blocks while monitoring the process. Returns when process exits."""
        while self.process and self.process.poll() is None:
            if not self.should_run:
                self.process.terminate()
                return

            await asyncio.sleep(1)

        # Process has exited
        return_code = self.process.returncode
        await self._handle_exit(return_code)

    async def _handle_exit(self, return_code: Optional[int]):
        """Decide whether/how quickly to restart based on exit code."""
        if not self.should_run:
            logger.info("Process exited (code %s). Supervisor stopping.", return_code)
            return

        if return_code == 0:
            # Clean exit — scheduled or deliberate restart
            logger.info("Process exited cleanly (code 0). Restarting in 2s...")
            await asyncio.sleep(2)
            return  # FIX: early return, skip crash accounting below

        # ── Crash path ─────────────────────────────────────────────────────
        logger.warning("Process crashed/exited with code %s", return_code)
        
        now = time.time()
        if now - self.last_crash_time < 60:
            self.crash_count += 1
        else:
            self.crash_count = 1  # Reset window
        self.last_crash_time = now

        wait_time = min(30, 2 ** (self.crash_count - 1))
        logger.info("Resurrection in %ds (crash #%d in current window)", wait_time, self.crash_count)
        await asyncio.sleep(wait_time)

    def _kill_process_tree(self, pid):
        """Kills the process and its children using psutil."""
        if not psutil:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            return

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            parent.terminate()
            
            gone, alive = psutil.wait_procs(children + [parent], timeout=3)
            for p in alive:
                p.kill()
        except psutil.NoSuchProcess:
            pass

if __name__ == "__main__":
    import asyncio
    # Example usage: Watch run_aura.py
    supervisor = SovereignSupervisor("run_aura.py", ["--server"])
    
    async def main():
        # Setup loop-based signal handling correctly if possible
        # For simplicity in __main__:
        await supervisor.start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

try:
    from celery import Celery
except ImportError:
    Celery = None
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Aura.Tasks")

# Initialize Celery only if enabled
from core.config import config

if Celery is None or not getattr(config.redis, "enabled", True):
    if Celery is None:
        logger.info("📡 Celery module NOT FOUND. Using local mock.")
    else:
        logger.info("📡 Redis/Celery DISABLED via config. Using local mock.")
    class MockCelery:
        def task(self, *args, **kwargs):
            return lambda f: f
        def send_task(self, name, args=None, kwargs=None, **options):
            logger.debug("Mocking send_task: %s", name)
            # If we're mocking and it's a critical task, we might want to trigger it locally
            if name == "core.tasks.process_user_input" and args:
                logger.info("MockCelery: Redirecting user input to local EventBus...")
                # We can't import here to avoid circular dependencies if any, 
                # but process_user_input is defined in this file.
                process_user_input(*args)
            return None
        def conf(self): pass
        def update(self, *args, **kwargs): pass
    celery_app = MockCelery()
    celery_app.conf = MockCelery() # Allow .conf.update usage
else:
    redis_url = os.environ.get("REDIS_URL", config.redis.url)
    celery_app = Celery("aura_tasks", broker=redis_url, backend=redis_url)

def dispatch_user_input(message: str):
    """Unified helper to dispatch user input, handling Redis-down scenarios."""
    try:
        if getattr(config.redis, "enabled", True):
            celery_app.send_task("core.tasks.process_user_input", args=[message])
        else:
            # Direct local call to the task function
            process_user_input(message)
    except Exception as e:
        logger.error("Dispatch failed: %s. Falling back to local execution.", e)
        process_user_input(message)

# Configuration for Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600, # 1 hour limit for long tasks
)

@celery_app.task(name="core.tasks.run_orchestrator")
def run_orchestrator():
    """
    Long-running task that executes the main cognitive orchestrator loop.
    H-12 FIX: Moves the monolith off the main thread.
    """
    import asyncio
    
    # 1. Create and bind a new event loop strictly for this background thread
    # H-28 FIX: Prevent 'no current event loop' crash in background thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    logger.info("🧠 Brain Boot: Starting Decoupled Orchestrator...")
    
    try:
        # 2. Boot the orchestrator safely within the new async context
        from core.orchestrator import create_orchestrator
        orchestrator = create_orchestrator()
        
        if orchestrator is None:
            logger.critical("❌ create_orchestrator() returned None!")
            return
        
        # 3. Execute the infinite cognitive loop
        logger.info("✅ Orchestrator created, entering run loop...")
        loop.run_until_complete(orchestrator.run())
    except Exception as e:
        import traceback
        logger.critical("Orchestrator task failed: %s", e, exc_info=True)
    finally:
        loop.close()

@celery_app.task(name="core.tasks.process_user_input")
def process_user_input(message: str):
    """
    Dispatches user input to the running orchestrator via message queue or global state.
    """
    logger.info("📥 Received user input: %s...", message[:50])
    
    # Bridge to the running orchestrator via EventBus
    from core.event_bus import get_event_bus
    try:
        bus = get_event_bus()
        # Use publish_threadsafe to handle cases where we are in a thread (like local fallback) 
        # or another loop is running.
        bus.publish_threadsafe("user_input", {"message": message})
        return {"status": "dispatched"}
    except Exception as e:
        logger.error("EventBus publication failed: %s", e)
        return {"status": "error", "message": str(e)}

@celery_app.task(name="core.tasks.run_rl_training")
def run_rl_training():
    """Executes RL training as a managed Celery task."""
    logger.info("🧠 RL: Starting policy optimization...")
    import subprocess
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "core/rl_train.py"],
            capture_output=True,
            text=True,
            check=True
        )
        return {"status": "success", "stdout": result.stdout}
    except Exception as e:
        logger.error("RL training failed: %s", e)
        return {"status": "error", "message": str(e)}

@celery_app.task(name="core.tasks.run_self_update")
def run_self_update():
    """Executes self-evolution update as a managed Celery task."""
    logger.info("🧬 EVO: Starting self-update cycle...")
    import subprocess
    import sys
    try:
        result = subprocess.run(
            [sys.executable, "scripts/self_update.py"],
            capture_output=True,
            text=True,
            check=True
        )
        return {"status": "success", "stdout": result.stdout}
    except Exception as e:
        logger.error("Self-update failed: %s", e)
        return {"status": "error", "message": str(e)}

@celery_app.task(name="core.tasks.run_mutation_tests")
def run_mutation_tests(target_file: str):
    """Runs pytest in the background for code mutations."""
    import subprocess
    logger.info("Running mutation tests for %s...", target_file)
    try:
        result = subprocess.run(
            ["pytest", "-q", target_file],
            capture_output=True,
            text=True,
            check=False
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

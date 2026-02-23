import asyncio
import logging
from typing import Optional, Set

logger = logging.getLogger(__name__)

class TaskTracker:
    """Track and manage background asyncio tasks to ensure graceful shutdown.
    Prevents 'Task was destroyed but it is pending!' errors and ensures all
    background work is either completed or cleanly cancelled.
    """
    
    def __init__(self, name: str = "Global"):
        self.name = name
        self.tasks: Set[asyncio.Task] = set()
        
    def track(self, coro_or_task, name: Optional[str] = None) -> asyncio.Task:
        """Track a new task or coroutine."""
        if isinstance(coro_or_task, asyncio.Task):
            task = coro_or_task
        else:
            task = asyncio.create_task(coro_or_task, name=name)
            
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    # Alias for compatibility with components calling track_task
    track_task = track
        
    async def shutdown(self, timeout: float = 5.0):
        """Cancel and wait for all tracked tasks."""
        if not self.tasks:
            return
            
        logger.info("Shutting down TaskTracker[%s]: %s tasks pending.", self.name, len(self.tasks))
        
        # 1. Signal cancellation
        for task in self.tasks:
            task.cancel()
            
        # 2. Wait for completion with timeout
        try:
            await asyncio.wait(self.tasks, timeout=timeout)
        except Exception as e:
            logger.error("Error during TaskTracker shutdown: %s", e)
            
        # 3. Final cleanup
        remaining = [t for t in self.tasks if not t.done()]
        if remaining:
            logger.warning("%d tasks still pending after timeout. Forcing abandonment.", len(remaining))
        
        self.tasks.clear()

task_tracker = TaskTracker()

"""core/utils/executor.py
Global executors for Aura to manage GIL contention and blocking ops.
"""
import asyncio
import concurrent.futures
import multiprocessing
import os
from typing import Any, Callable

# Global process pool for heavy CPU/ML tasks (bypassing GIL)
# We limit to a small number (e.g., 2) to avoid saturating M1/M2/M3 cores too much
_cpu_executor = concurrent.futures.ProcessPoolExecutor(
    max_workers=min(multiprocessing.cpu_count(), 2),
    mp_context=multiprocessing.get_context('spawn')
)

# Global thread pool for I/O blocking tasks (requests, etc.)
_io_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=min(multiprocessing.cpu_count() * 4, 32)
)

async def run_in_process(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run a CPU-bound function in a separate process."""
    loop = asyncio.get_running_loop()
    # Partial to handle kwargs if needed
    if kwargs:
        from functools import partial
        func = partial(func, **kwargs)
    return await loop.run_in_executor(_cpu_executor, func, *args)

async def run_in_thread(func: Callable, *args: Any, **kwargs: Any) -> Any:
    """Run an I/O-bound function in a separate thread."""
    loop = asyncio.get_running_loop()
    if kwargs:
        from functools import partial
        func = partial(func, **kwargs)
    return await loop.run_in_executor(_io_executor, func, *args)

def shutdown_executors():
    """Cleanup on exit."""
    _cpu_executor.shutdown(wait=False)
    _io_executor.shutdown(wait=False)

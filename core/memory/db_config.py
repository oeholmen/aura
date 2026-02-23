"""Database Configuration & Optimization
-------------------------------------
Centralizes SQLite configuration to ensure WAL (Write-Ahead Logging) mode is enabled.
WAL mode significantly improves concurrency, allowing readers to not block writers.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("Aura.DBConfig")

def configure_connection(db_path: str) -> sqlite3.Connection:
    """Creates a connection to the SQLite DB and enables WAL mode (synchronous)."""
    path = Path(db_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        
    conn = sqlite3.connect(str(path), check_same_thread=False)
    
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.commit()
    except Exception as e:
        logger.warning("Failed to set PRAGMA options on %s: %s", db_path, e)
        
    return conn

async def configure_connection_async(db_path: str):
    """Creates an aiosqlite connection and enables WAL mode."""
    import aiosqlite
    path = Path(db_path)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        
    conn = await aiosqlite.connect(str(path))
    
    try:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        await conn.execute("PRAGMA busy_timeout=5000;")
        await conn.commit()
    except Exception as e:
        logger.warning("Failed to set async PRAGMA options on %s: %s", db_path, e)
        
    return conn

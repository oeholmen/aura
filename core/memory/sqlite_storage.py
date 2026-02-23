"""aiosqlite-backed Atomic Memory System.

Replaces the synchronous sqlite3 SQLiteMemory for scalability and non-blocking I/O.
Maintains the same API via threadsafe synchronous wrappers, but deeply uses async natively.

C-10 FIX: Implemented persistent aiosqlite connection to remove file open/close overhead.
H-11 FIX: Consistent log formatting using %s placeholders.
H-04 FIX: Thread-safe synchronous wrappers using threading.Lock.
"""

import asyncio
import json
import logging
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiosqlite
from core.memory import db_config
from core.memory.base import MemoryEvent

logger = logging.getLogger("Kernel.Memory.SQLite")

class SQLiteMemory:
    """Scalable, non-blocking memory storage using aiosqlite.
    Drop-in replacement for AtomicStorage/sync SQLiteMemory.
    
    C-10 FIX: Uses a single persistent aiosqlite connection.
    H-04 FIX: Synchronous wrappers are protected by a threading.Lock.
    """
    
    def __init__(self, storage_file: str = "autonomy_engine/memory/atomic.db"):
        self.storage_file = Path(storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._conn: Optional[aiosqlite.Connection] = None
        self._sync_lock = threading.Lock()  # H-04 FIX: Thread-safe sync wrappers
        
    async def _get_conn(self) -> aiosqlite.Connection:
        """Returns the persistent connection, initializing it if necessary."""
        if self._conn is not None:
            return self._conn
            
        async with self._init_lock:
            if self._conn is not None:
                return self._conn
            
            # C-10 FIX: Open persistent connection
            self._conn = await db_config.configure_connection_async(str(self.storage_file))
            await self._ensure_schema()
            self._initialized = True
            logger.info("aiosqlite Memory initialized at %s", self.storage_file)
            return self._conn

    async def _ensure_schema(self):
        """Initialize the database schema."""
        if self._conn is None:
            return
            
        # episodic: Stores chronological events
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS episodic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                event_type TEXT,
                goal TEXT,
                outcome TEXT,
                cost REAL,
                metadata TEXT
            )
        ''')
    
        # semantic: Key-value store for facts
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS semantic (
                key TEXT PRIMARY KEY,
                value TEXT,
                last_modified REAL
            )
        ''')
        
        # goals: Active goals
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT,
                status TEXT,
                created_at REAL
            )
        ''')
        
        # Indices for speed
        await self._conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON episodic(timestamp)')
        await self._conn.execute('CREATE INDEX IF NOT EXISTS idx_event_type ON episodic(event_type)')
        
        await self._conn.commit()

    async def on_stop_async(self):
        """Close the persistent connection."""
        async with self._init_lock:
            if self._conn:
                await self._conn.close()
                self._conn = None
                self._initialized = False
                logger.debug("SQLite connection closed")

    def close(self):
        """Synchronous connection close."""
        with self._sync_lock:
            try:
                loop = asyncio.get_running_loop()
                asyncio.run_coroutine_threadsafe(self.on_stop_async(), loop).result()
            except RuntimeError:
                asyncio.run(self.on_stop_async())

    # --- Async Native Methods ---

    async def log_event_async(self, event: Union[Dict[str, Any], MemoryEvent]) -> bool:
        """Log an episodic event asynchronously."""
        try:
            conn = await self._get_conn()
            if isinstance(event, dict):
                # Ensure defaults
                if 'timestamp' not in event: event['timestamp'] = time.time()
                if 'metadata' not in event: event['metadata'] = {}
            else:
                event = event.to_dict()

            await conn.execute('''
                INSERT INTO episodic (timestamp, event_type, goal, outcome, cost, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                event.get('timestamp'),
                event.get('event_type'),
                event.get('goal'),
                json.dumps(event.get('outcome')),
                event.get('cost', 0.0),
                json.dumps(event.get('metadata', {}))
            ))
            await conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to log event asynchronously: %s", e)
            return False

    async def get_recent_events_async(self, count: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent events asynchronously."""
        try:
            conn = await self._get_conn()
            conn.row_factory = aiosqlite.Row
            async with conn.execute('''
                SELECT * FROM episodic 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (count,)) as cursor:
                rows = await cursor.fetchall()
                
            events = []
            for row in rows:
                evt = dict(row)
                # Parse JSON fields
                try:
                    evt['outcome'] = json.loads(evt['outcome']) if evt['outcome'] else None
                    evt['metadata'] = json.loads(evt['metadata']) if evt['metadata'] else {}
                except (json.JSONDecodeError, TypeError) as e:
                    logger.debug("Malformed JSON in event row %s: %s", evt.get('id', '?'), e)
                events.append(evt)
            
            return list(reversed(events)) # Return chronological order
        except Exception as e:
            logger.error("Failed to get events asynchronously: %s", e)
            return []

    async def update_semantic_async(self, key: str, value: Any) -> bool:
        """Update a semantic memory asynchronously."""
        try:
            conn = await self._get_conn()
            await conn.execute('''
                INSERT OR REPLACE INTO semantic (key, value, last_modified)
                VALUES (?, ?, ?)
            ''', (key, json.dumps(value), time.time()))
            await conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to update semantic asynchronously: %s", e)
            return False

    async def get_semantic_async(self, key: str, default: Any = None) -> Any:
        """Get a semantic memory asynchronously."""
        try:
            conn = await self._get_conn()
            async with conn.execute('SELECT value FROM semantic WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return default
        except Exception as e:
            logger.error("Failed to get semantic asynchronously: %s", e)
            return default

    async def clear_episodic_async(self) -> bool:
        """Clear episodic memory asynchronously."""
        conn = await self._get_conn()
        await conn.execute('DELETE FROM episodic')
        await conn.commit()
        return True

    def save(self) -> bool:
        """No-op for SQLite as it sends to disk immediately."""
        return True

    # --- Legacy Synchronous Wrappers ---
    def _run_sync(self, coro):
        with self._sync_lock: # H-04 FIX: Thread safety for sync wrappers
            try:
                loop = asyncio.get_running_loop()
                return asyncio.run_coroutine_threadsafe(coro, loop).result()
            except RuntimeError:
                return asyncio.run(coro)

    def log_event(self, event: Union[Dict[str, Any], MemoryEvent]) -> bool:
        return self._run_sync(self.log_event_async(event))

    def get_recent_events(self, count: int = 10) -> List[Dict[str, Any]]:
        return self._run_sync(self.get_recent_events_async(count))

    def update_semantic(self, key: str, value: Any) -> bool:
        return self._run_sync(self.update_semantic_async(key, value))

    def get_semantic(self, key: str, default: Any = None) -> Any:
        return self._run_sync(self.get_semantic_async(key, default))

    def clear_episodic(self) -> bool:
        return self._run_sync(self.clear_episodic_async())

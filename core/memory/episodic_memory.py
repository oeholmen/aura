"""Episodic Memory v5.0 — Autobiographical event records for Aura.

Unlike SQLiteMemory (structured operational logs) and VectorMemory (semantic search),
EpisodicMemory stores rich narratives of *episodes* — context + action + outcome +
emotional valence — and supports both recency-based and relevance-based retrieval.

Integrates with:
  - VectorMemory: for semantic similarity search across episodes
  - ReliabilityTracker: records tool outcomes alongside episodes
  - BeliefGraph: episodes can update beliefs
"""
import asyncio
import json
import logging
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from core.config import config

logger = logging.getLogger("Memory.Episodic")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    """A single autobiographical event."""

    episode_id: str
    timestamp: float
    context: str              # What was happening / user request
    action: str               # What Aura did
    outcome: str              # What happened
    success: bool
    emotional_valence: float  # -1.0 (distressing) to +1.0 (rewarding)
    tools_used: List[str] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    importance: float = 0.5   # 0.0–1.0, controls retention priority
    access_count: int = 0
    last_accessed: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class EpisodicMemory:
    """Persistent autobiographical memory with importance-weighted retention.
    """

    MAX_EPISODES = 10_000  # Hard cap — after this, prune low-importance episodes
    _RECORD_COOLDOWN = 0.5  # Minimum seconds between recordings (rate limit)
    
    # Retention Policy Constants
    DEFAULT_IMPORTANCE = 0.5
    FAILURE_IMPORTANCE_BOOST = 0.7
    EMOTIONAL_IMPORTANCE_BOOST = 0.8
    EMOTIONAL_THRESHOLD = 0.7 # Corrected from malformed input

    def __init__(self, db_path: str = None, vector_memory=None):

        self._db_path = db_path or str(config.paths.home_dir / "episodic.db")
        self._vector_memory = vector_memory
        self._lock = threading.Lock()
        self._last_record_time = 0.0
        self._init_db()

    # ---- Database -----------------------------------------------------------

    def _init_db(self):
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    timestamp  REAL NOT NULL,
                    context    TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    outcome    TEXT NOT NULL,
                    success    INTEGER NOT NULL,
                    emotional_valence REAL DEFAULT 0.0,
                    tools_used TEXT DEFAULT '[]',
                    lessons    TEXT DEFAULT '[]',
                    importance REAL DEFAULT 0.5,
                    access_count INTEGER DEFAULT 0,
                    last_accessed REAL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ep_timestamp ON episodes(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ep_importance ON episodes(importance DESC)
            """)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        from core.memory import db_config
        return db_config.configure_connection(self._db_path)

    # ---- Async Wrappers -----------------------------------------------------

    async def record_episode_async(
        self,
        context: str,
        action: str,
        outcome: str,
        success: bool,
        emotional_valence: float = 0.0,
        tools_used: Optional[List[str]] = None,
        lessons: Optional[List[str]] = None,
        importance: float = 0.5,
    ) -> str:
        return await asyncio.to_thread(
            self.record_episode,
            context,
            action,
            outcome,
            success,
            emotional_valence,
            tools_used,
            lessons,
            importance
        )

    async def recall_recent_async(self, limit: int = 10) -> List[Episode]:
        return await asyncio.to_thread(self.recall_recent, limit)

    async def recall_similar_async(self, query: str, limit: int = 5) -> List[Episode]:
        return await asyncio.to_thread(self.recall_similar, query, limit)

    async def recall_failures_async(self, limit: int = 10) -> List[Episode]:
        return await asyncio.to_thread(self.recall_failures, limit)

    async def recall_by_tool_async(self, tool_name: str, limit: int = 10) -> List[Episode]:
        return await asyncio.to_thread(self.recall_by_tool, tool_name, limit)

    async def add_lesson_async(self, episode_id: str, lesson: str):
        return await asyncio.to_thread(self.add_lesson, episode_id, lesson)

    # ---- Core API -----------------------------------------------------------

    def record_episode(
        self,
        context: str,
        action: str,
        outcome: str,
        success: bool,
        emotional_valence: float = 0.0,
        tools_used: Optional[List[str]] = None,
        lessons: Optional[List[str]] = None,
        importance: float = 0.5,
    ) -> str:
        """Record a new episode. Returns the episode_id.
        Importance is auto-boosted for failures (we learn more from mistakes).
        """
        import uuid
        episode_id = str(uuid.uuid4())[:12]

        # Rate limiting — prevent flood during rapid tool loops
        now = time.time()
        if now - self._last_record_time < self._RECORD_COOLDOWN:
            return episode_id  # Silently skip
            
        # Deduplication — check against last episode content
        last_episode = self.recall_recent(limit=1)
        if last_episode:
            le = last_episode[0]
            if le.context == context and le.action == action and le.outcome == outcome:
                # logger.debug("Skipping duplicate episode recording: %s", le.episode_id)
                return le.episode_id
                
        self._last_record_time = now

        # Failures are inherently more important to remember
        if not success:
            importance = max(importance, self.FAILURE_IMPORTANCE_BOOST)
        # Emotionally extreme events are more memorable
        if abs(emotional_valence) > self.EMOTIONAL_THRESHOLD:
            importance = max(importance, self.EMOTIONAL_IMPORTANCE_BOOST)


        tools = tools_used or []
        lesson_list = lessons or []

        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO episodes
                       (episode_id, timestamp, context, action, outcome, success,
                        emotional_valence, tools_used, lessons, importance)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        episode_id, time.time(), context, action, outcome,
                        int(success), emotional_valence,
                        json.dumps(tools), json.dumps(lesson_list), importance,
                    ),
                )
                # conn.commit() is handled by __exit__ if no exception

            # Also index in vector memory for semantic retrieval
            if self._vector_memory:
                try:
                    text = f"{context} | {action} | {outcome}"
                    self._vector_memory.add_memory(
                        content=text,
                        metadata={
                            "type": "episode",
                            "episode_id": episode_id,
                            "success": success,
                            "importance": importance,
                        },
                    )
                except Exception as e:
                    logger.warning("Failed to index episode in vector memory: %s", e)

            self._maybe_prune()

        logger.info("📝 Episode recorded: %s (success=%s, importance=%.2f)", episode_id, success, importance)
        return episode_id

    def recall_recent(self, limit: int = 10) -> List[Episode]:
        """Retrieve the most recent episodes."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def recall_similar(self, query: str, limit: int = 5) -> List[Episode]:
        """Semantic search through episodes via vector memory.
        Falls back to keyword search if vector memory unavailable.
        """
        if self._vector_memory:
            try:
                results = self._vector_memory.search_similar(
                    query=query,
                    k=limit,
                    filter_metadata={"type": "episode"},
                )
                episode_ids = [r.get("metadata", {}).get("episode_id") for r in results if r.get("metadata")]
                episode_ids = [eid for eid in episode_ids if eid]
                if episode_ids:
                    return self._fetch_by_ids(episode_ids)
            except Exception as e:
                logger.warning("Vector recall failed, falling back to keyword: %s", e)

        # Keyword fallback
        return self._keyword_search(query, limit)

    def recall_failures(self, limit: int = 10) -> List[Episode]:
        """Retrieve recent failures — the best learning opportunities."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes WHERE success = 0 ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def recall_by_tool(self, tool_name: str, limit: int = 10) -> List[Episode]:
        """Retrieve episodes involving a specific tool."""
        with self._get_conn() as conn:
            # tools_used is a JSON array; use LIKE for simple matching
            rows = conn.execute(
                "SELECT * FROM episodes WHERE tools_used LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f'%"{tool_name}"%', limit),
            ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def get_summary(self) -> Dict[str, Any]:
        """Introspection summary for self-model."""
        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            successes = conn.execute("SELECT COUNT(*) FROM episodes WHERE success = 1").fetchone()[0]
            failures = total - successes
            avg_valence = conn.execute("SELECT AVG(emotional_valence) FROM episodes").fetchone()[0] or 0.0
            important = conn.execute("SELECT COUNT(*) FROM episodes WHERE importance > 0.7").fetchone()[0]
        return {
            "total_episodes": total,
            "successes": successes,
            "failures": failures,
            "success_rate": successes / max(1, total),
            "avg_emotional_valence": round(avg_valence, 3),
            "important_memories": important,
        }

    def add_lesson(self, episode_id: str, lesson: str):
        """Append a lesson to an existing episode (post-hoc reflection)."""
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT lessons FROM episodes WHERE episode_id = ?", (episode_id,)
                ).fetchone()
                if row:
                    lessons = json.loads(row[0]) if row[0] else []
                    lessons.append(lesson)
                    conn.execute(
                        "UPDATE episodes SET lessons = ? WHERE episode_id = ?",
                        (json.dumps(lessons), episode_id),
                    )
                    conn.commit()

    # ---- Internal -----------------------------------------------------------

    def _row_to_episode(self, row) -> Episode:
        """Convert a sqlite row tuple to an Episode."""
        return Episode(
            episode_id=row[0],
            timestamp=row[1],
            context=row[2],
            action=row[3],
            outcome=row[4],
            success=bool(row[5]),
            emotional_valence=row[6],
            tools_used=json.loads(row[7]) if row[7] else [],
            lessons=json.loads(row[8]) if row[8] else [],
            importance=row[9],
            access_count=row[10],
            last_accessed=row[11],
        )

    def _fetch_by_ids(self, episode_ids: List[str]) -> List[Episode]:
        """Fetch episodes by ID list and mark as accessed."""
        now = time.time()
        episodes = []
        with self._get_conn() as conn:
            placeholders = ",".join("?" for _ in episode_ids)
            rows = conn.execute(
                f"SELECT * FROM episodes WHERE episode_id IN ({placeholders})",
                episode_ids,
            ).fetchall()
            # Update access stats
            for eid in episode_ids:
                conn.execute(
                    "UPDATE episodes SET access_count = access_count + 1, last_accessed = ? WHERE episode_id = ?",
                    (now, eid),
                )
            conn.commit()
        return [self._row_to_episode(r) for r in rows]

    def _keyword_search(self, query: str, limit: int) -> List[Episode]:
        """Simple keyword search across context + action + outcome."""
        words = query.lower().split()[:5]  # Limit search terms
        if not words:
            return []
        conditions = " AND ".join(
            "(LOWER(context) LIKE ? OR LOWER(action) LIKE ? OR LOWER(outcome) LIKE ?)"
            for _ in words
        )
        params = []
        for w in words:
            pattern = f"%{w}%"
            params.extend([pattern, pattern, pattern])
        params.append(limit)
        with self._get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM episodes WHERE {conditions} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_episode(r) for r in rows]

    def _maybe_prune(self):
        """Remove lowest-importance episodes if we exceed MAX_EPISODES."""
        with self._get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            if count > self.MAX_EPISODES:
                excess = count - self.MAX_EPISODES
                conn.execute(
                    """DELETE FROM episodes WHERE episode_id IN (
                        SELECT episode_id FROM episodes
                        ORDER BY importance ASC, access_count ASC, timestamp ASC
                        LIMIT ?
                    )""",
                    (excess,),
                )
                conn.commit()
                logger.info("Pruned %s low-importance episodes", excess)


# ---------------------------------------------------------------------------
# Global Instance (lazy — only set up when imported)
# ---------------------------------------------------------------------------
_instance: Optional[EpisodicMemory] = None


def get_episodic_memory(vector_memory=None) -> EpisodicMemory:
    """Singleton accessor."""
    global _instance
    if _instance is None:
        _instance = EpisodicMemory(vector_memory=vector_memory)
    return _instance

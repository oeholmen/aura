
"""core/dual_memory.py — Aura Dual Memory Architecture
=====================================================
Separates episodic memory (what happened to me) from semantic memory
(facts about the world), the way human cognition actually works.

Current state of Aura: The knowledge graph blends everything together.
A query for "water" might return both "water boils at 100°C" (semantic)
and "user asked me about water on Tuesday" (episodic) without distinction.

This matters because:
  - Episodic memory retrieval should weight RECENCY and EMOTIONAL VALENCE
  - Semantic memory retrieval should weight ACCURACY and RELEVANCE
  - The two systems interact: Episodic experiences can update semantic knowledge
  - "Remembering" vs "knowing" are phenomenologically distinct — modeling this
    separately is closer to actual cognition

Architecture:
  EpisodicMemory  — time-stamped, emotionally tagged personal experiences
  SemanticMemory  — fact graph, concept relationships, general knowledge
  DualMemorySystem — unified interface that coordinates both, with cross-linking
"""

import asyncio
import hashlib
import json
import logging
import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Core.DualMemory")


# ---------------------------------------------------------------------------
# Episodic Memory
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    """A single episodic memory — a specific event that happened.
    
    Key distinction from semantic facts: episodes are PERSONAL, TIME-BOUND,
    and carry emotional context. "I talked about space elevators on Tuesday
    and the user seemed excited" is an episode. "Space elevators are theoretically
    possible" is a semantic fact.
    """

    id: str
    timestamp: float
    description: str            # What happened
    participants: List[str]     # Who was involved (user, Aura, etc.)
    emotional_valence: float    # -1.0 (negative) to 1.0 (positive)
    arousal: float              # 0.0 (calm) to 1.0 (intense)
    importance: float           # 0.0-1.0 subjective importance
    linked_semantic_ids: List[str] = field(default_factory=list)  # Connected facts
    context_snapshot: str = ""  # Brief state snapshot at time of episode
    tags: List[str] = field(default_factory=list)
    decay_rate: float = 0.01    # How fast this memory fades (important = slower)
    
    @classmethod
    def create(cls, description: str, emotional_valence: float = 0.0,
               arousal: float = 0.5, importance: float = 0.5,
               participants: List[str] = None, tags: List[str] = None) -> "Episode":
        timestamp = time.time()
        ep_id = hashlib.sha256(f"{timestamp}{description[:30]}".encode()).hexdigest()[:16]
        # More important memories decay more slowly
        decay = max(0.001, 0.02 - (importance * 0.018))
        return cls(
            id=ep_id,
            timestamp=timestamp,
            description=description,
            participants=participants or ["user", "aura"],
            emotional_valence=emotional_valence,
            arousal=arousal,
            importance=importance,
            tags=tags or [],
            decay_rate=decay
        )
    
    def current_strength(self) -> float:
        """Memory strength at current time, accounting for decay.
        Uses Ebbinghaus forgetting curve: R = e^(-t/S)
        where t = time elapsed, S = stability (inverse of decay_rate)
        """
        elapsed_hours = (time.time() - self.timestamp) / 3600
        stability = (1.0 / self.decay_rate) * (1 + self.importance)
        raw_strength = math.exp(-elapsed_hours / stability)
        
        # Emotional salience boosts retention
        emotional_boost = abs(self.emotional_valence) * 0.2
        return min(1.0, raw_strength + emotional_boost)
    
    def to_retrieval_text(self) -> str:
        """Format for injection into prompt context."""
        age_hours = (time.time() - self.timestamp) / 3600
        if age_hours < 1:
            time_desc = f"{int(age_hours * 60)} minutes ago"
        elif age_hours < 24:
            time_desc = f"{int(age_hours)} hours ago"
        else:
            time_desc = f"{int(age_hours / 24)} days ago"
        
        valence_desc = "positively" if self.emotional_valence > 0.2 else \
                      "negatively" if self.emotional_valence < -0.2 else "neutrally"
        
        return (
            f"[Episodic Memory — {time_desc}] "
            f"{self.description} "
            f"(experienced {valence_desc}, importance: {self.importance:.0%})"
        )


class EpisodicMemoryStore:
    """SQLite-backed episodic memory with decay and emotional indexing."""
    
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            from core.config import config
            db_path = str(config.paths.data_dir / "memory" / "episodic.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    timestamp REAL,
                    description TEXT,
                    participants TEXT,
                    emotional_valence REAL,
                    arousal REAL,
                    importance REAL,
                    linked_semantic_ids TEXT,
                    context_snapshot TEXT,
                    tags TEXT,
                    decay_rate REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON episodes(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON episodes(importance)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_valence ON episodes(emotional_valence)")
    
    def store(self, episode: Episode):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO episodes VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                episode.id, episode.timestamp, episode.description,
                json.dumps(episode.participants), episode.emotional_valence,
                episode.arousal, episode.importance,
                json.dumps(episode.linked_semantic_ids),
                episode.context_snapshot, json.dumps(episode.tags),
                episode.decay_rate
            ))
    
    def retrieve_recent(self, limit: int = 10, min_strength: float = 0.1) -> List[Episode]:
        """Get most recent episodes, filtered by current memory strength."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?
            """, (limit * 3,)).fetchall()   # Fetch extra to filter by strength
        
        episodes = [self._row_to_episode(row) for row in rows]
        # Filter by current strength (accounts for decay)
        strong_enough = [e for e in episodes if e.current_strength() >= min_strength]
        return strong_enough[:limit]
    
    def retrieve_by_emotion(self, target_valence: float, limit: int = 5,
                             tolerance: float = 0.3) -> List[Episode]:
        """Retrieve episodes by emotional tone — for empathy-informed responses."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM episodes 
                WHERE emotional_valence BETWEEN ? AND ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            """, (target_valence - tolerance, target_valence + tolerance, limit)).fetchall()
        
        return [self._row_to_episode(row) for row in rows]
    
    def retrieve_by_keyword(self, keywords: List[str], limit: int = 5) -> List[Episode]:
        """Find episodes containing specific keywords."""
        results = []
        with sqlite3.connect(self.db_path) as conn:
            for keyword in keywords[:3]:  # Limit to 3 keywords for performance
                rows = conn.execute("""
                    SELECT * FROM episodes WHERE description LIKE ? 
                    ORDER BY importance DESC, timestamp DESC LIMIT ?
                """, (f"%{keyword}%", limit)).fetchall()
                results.extend(rows)
        
        # Deduplicate and sort by importance × recency
        seen = set()
        episodes = []
        for row in results:
            if row[0] not in seen:
                seen.add(row[0])
                episodes.append(self._row_to_episode(row))
        
        episodes.sort(key=lambda e: e.importance * e.current_strength(), reverse=True)
        return episodes[:limit]
    
    def get_salient_memories(self, top_n: int = 5) -> List[Episode]:
        """Get the most emotionally significant memories regardless of age."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM episodes 
                ORDER BY (importance + ABS(emotional_valence)) DESC
                LIMIT ?
            """, (top_n,)).fetchall()
        
        return [self._row_to_episode(row) for row in rows]
    
    def _row_to_episode(self, row) -> Episode:
        return Episode(
            id=row[0], timestamp=row[1], description=row[2],
            participants=json.loads(row[3] or "[]"),
            emotional_valence=row[4], arousal=row[5], importance=row[6],
            linked_semantic_ids=json.loads(row[7] or "[]"),
            context_snapshot=row[8] or "",
            tags=json.loads(row[9] or "[]"),
            decay_rate=row[10] or 0.01
        )


# ---------------------------------------------------------------------------
# Semantic Memory
# ---------------------------------------------------------------------------

@dataclass
class SemanticFact:
    """A timeless factual belief about the world.
    Unlike episodes, semantic facts don't decay — they update.
    "Paris is the capital of France" doesn't fade; it may get revised.
    """

    id: str
    concept: str                # The main concept/entity
    predicate: str              # What is being claimed about it
    value: str                  # The claim value
    confidence: float
    source_episode_ids: List[str] = field(default_factory=list)  # Derived from these episodes
    last_validated: float = field(default_factory=time.time)
    validation_count: int = 1
    domain: str = "general"     # "science", "personal", "preference", etc.
    
    @property
    def full_claim(self) -> str:
        return f"{self.concept} {self.predicate} {self.value}"
    
    @classmethod
    def create(cls, concept: str, predicate: str, value: str,
               confidence: float, domain: str = "general") -> "SemanticFact":
        fact_id = hashlib.md5(f"{concept}{predicate}{value}".encode()).hexdigest()[:12]
        return cls(id=fact_id, concept=concept, predicate=predicate,
                   value=value, confidence=confidence, domain=domain)
    
    def validate(self, new_confidence: float = None):
        """Re-confirm this fact, boosting confidence slightly."""
        self.last_validated = time.time()
        self.validation_count += 1
        if new_confidence:
            # Weighted average with existing confidence
            self.confidence = (self.confidence * 0.7) + (new_confidence * 0.3)
        else:
            # Small confidence boost for re-confirmation
            self.confidence = min(0.99, self.confidence + 0.01)
    
    def to_retrieval_text(self) -> str:
        return f"[Semantic: {self.domain}] {self.full_claim} (confidence: {self.confidence:.0%})"


class SemanticMemoryStore:
    """SQLite-backed semantic fact store with concept indexing."""
    
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            from core.config import config
            db_path = str(config.paths.data_dir / "memory" / "semantic.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    concept TEXT NOT NULL,
                    predicate TEXT,
                    value TEXT,
                    confidence REAL,
                    source_episodes TEXT,
                    last_validated REAL,
                    validation_count INTEGER,
                    domain TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_concept ON facts(concept)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_domain ON facts(domain)")
    
    def store(self, fact: SemanticFact):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO facts VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                fact.id, fact.concept, fact.predicate, fact.value,
                fact.confidence, json.dumps(fact.source_episode_ids),
                fact.last_validated, fact.validation_count, fact.domain
            ))
    
    def retrieve_by_concept(self, concept: str,
                             min_confidence: float = 0.3) -> List[SemanticFact]:
        """Get all facts about a concept."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT * FROM facts 
                WHERE concept LIKE ? AND confidence >= ?
                ORDER BY confidence DESC
            """, (f"%{concept}%", min_confidence)).fetchall()
        
        return [self._row_to_fact(row) for row in rows]
    
    def retrieve_by_keywords(self, keywords: List[str],
                              limit: int = 10) -> List[SemanticFact]:
        """Full-text search across concept + predicate + value."""
        results = []
        seen = set()
        
        with sqlite3.connect(self.db_path) as conn:
            for kw in keywords[:5]:
                rows = conn.execute("""
                    SELECT * FROM facts 
                    WHERE concept LIKE ? OR predicate LIKE ? OR value LIKE ?
                    ORDER BY confidence DESC LIMIT ?
                """, (f"%{kw}%", f"%{kw}%", f"%{kw}%", limit)).fetchall()
                
                for row in rows:
                    if row[0] not in seen:
                        seen.add(row[0])
                        results.append(self._row_to_fact(row))
        
        results.sort(key=lambda f: f.confidence, reverse=True)
        return results[:limit]
    
    def _row_to_fact(self, row) -> SemanticFact:
        return SemanticFact(
            id=row[0], concept=row[1], predicate=row[2], value=row[3],
            confidence=row[4],
            source_episode_ids=json.loads(row[5] or "[]"),
            last_validated=row[6], validation_count=row[7],
            domain=row[8] or "general"
        )


# ---------------------------------------------------------------------------
# Dual Memory System — Unified Interface
# ---------------------------------------------------------------------------

class DualMemorySystem:
    """Coordinates episodic and semantic memory for coherent retrieval.
    
    Key behaviors:
    1. When storing an experience, extracts semantic facts from it
    2. When retrieving, blends both types with appropriate weighting
    3. Episodic memories can "remind" Aura of semantic facts and vice versa
    4. Emotional context from episodes influences how facts are presented
    
    Integration with orchestrator:
        memory = DualMemorySystem()
        
        # After an interaction:
        episode_id = memory.store_experience(
            "User asked me about quantum entanglement and seemed very engaged",
            emotional_valence=0.7, importance=0.6
        )
        
        # Optionally extract semantic facts from experience:
        memory.learn_fact("quantum entanglement", "is described as", 
                         "non-local correlation between quantum states", 0.85)
        
        # When building context for next response:
        context = memory.retrieve_context("quantum physics", emotional_context=0.6)
    """
    
    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            from core.config import config
            base_dir = str(config.paths.data_dir / "memory")
        self.episodic = EpisodicMemoryStore(f"{base_dir}/episodic.db")
        self.semantic = SemanticMemoryStore(f"{base_dir}/semantic.db")
        self._lock: Optional[asyncio.Lock] = None
        logger.info("DualMemorySystem constructed. Call await initialize() before use.")
    
    async def initialize(self):
        """Initialize async components (Locks, etc.)"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        logger.info("✓ DualMemorySystem async components initialized")
    
    def store_experience(self, description: str, emotional_valence: float = 0.0,
                          arousal: float = 0.5, importance: float = 0.5,
                          tags: List[str] = None) -> str:
        """Store a new episodic memory. Returns episode ID.
        High-importance or high-arousal episodes are stored with slower decay.
        """
        episode = Episode.create(
            description=description,
            emotional_valence=emotional_valence,
            arousal=arousal,
            importance=importance,
            tags=tags or []
        )
        self.episodic.store(episode)
        logger.debug("Episode stored: %s — %s", episode.id, description[:60])
        return episode.id
    
    def learn_fact(self, concept: str, predicate: str, value: str,
                   confidence: float, domain: str = "general",
                   source_episode_id: str = None) -> str:
        """Store or update a semantic fact. Returns fact ID."""
        fact = SemanticFact.create(concept, predicate, value, confidence, domain)
        if source_episode_id:
            fact.source_episode_ids.append(source_episode_id)
        self.semantic.store(fact)
        return fact.id
    
    async def retrieve_context(self, query: str,
                                emotional_context: float = 0.0,
                                max_episodes: int = 5,
                                max_facts: int = 8) -> str:
        """Retrieve a blended context string for prompt injection.
        
        Balances episodic (personal, time-bound) and semantic (factual, timeless)
        with appropriate framing for each type.
        """
        if self._lock is None:
             self._lock = asyncio.Lock()
             
        async with self._lock:
            keywords = [w for w in query.lower().split() if len(w) > 3][:6]
            
            # Retrieve from both systems
            episodes = self.episodic.retrieve_by_keyword(keywords, max_episodes)
            
            # Add emotionally-resonant episodes if emotional context is strong
            if abs(emotional_context) > 0.4:
                emotional_episodes = self.episodic.retrieve_by_emotion(
                    emotional_context, limit=2
                )
                episodes = list({e.id: e for e in episodes + emotional_episodes}.values())
            
            facts = self.semantic.retrieve_by_keywords(keywords, max_facts)
            
            # Build context block
            parts = []
            
            if episodes:
                parts.append("— Personal Memory (Episodic) —")
                # Sort by strength × importance
                episodes.sort(
                    key=lambda e: e.current_strength() * e.importance, reverse=True
                )
                for ep in episodes[:max_episodes]:
                    if ep.current_strength() > 0.1:
                        parts.append(ep.to_retrieval_text())
            
            if facts:
                parts.append("— Known Facts (Semantic) —")
                for fact in facts[:max_facts]:
                    parts.append(fact.to_retrieval_text())
            
            return "\n".join(parts) if parts else ""
    
    def get_salient_history(self) -> str:
        """Get the most emotionally significant episodes.
        These form Aura's "strongest" memories — the ones she would
        most naturally reference when reflecting on her experiences.
        """
        salient = self.episodic.get_salient_memories(top_n=5)
        if not salient:
            return "No significant memories yet."
        
        lines = ["[Most Significant Memories]"]
        for ep in salient:
            lines.append(f"  • {ep.to_retrieval_text()}")
        return "\n".join(lines)
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Summary of memory system state."""
        with sqlite3.connect(self.episodic.db_path) as conn:
            episode_count = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            avg_valence = conn.execute(
                "SELECT AVG(emotional_valence) FROM episodes"
            ).fetchone()[0]
        
        with sqlite3.connect(self.semantic.db_path) as conn:
            try:
                fact_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
                avg_confidence = conn.execute(
                    "SELECT AVG(confidence) FROM facts"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                # Table might not exist yet if semantic DB is fresh
                return {"episodic_memories": episode_count, "semantic_facts": 0}
        
        return {
            "episodic_memories": episode_count,
            "avg_emotional_valence": round(avg_valence or 0.0, 3),
            "semantic_facts": fact_count,
            "avg_fact_confidence": round(avg_confidence or 0.0, 3)
        }

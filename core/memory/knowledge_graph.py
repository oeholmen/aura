"""Persistent Knowledge Graph - SQLite backend
Aura's knowledge persists forever across sessions.
v5.0: Thread-safe with WAL mode.
"""
import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.config import config

logger = logging.getLogger("Knowledge.Graph")


class PersistentKnowledgeGraph:
    """SQLite-backed knowledge that never forgets. v5.0: Thread-safe."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            import os
            db_path = str(config.paths.home_dir / "data/knowledge.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._init_schema()
        
        logger.info("✓ Knowledge Graph: %s", db_path)
        logger.info("   Nodes: %s", self.count_nodes())
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get an optimized thread-safe connection."""
        from core.memory import db_config
        return db_config.configure_connection(self.db_path)

    def _init_schema(self):
        """Create tables"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
        
        c.execute("""CREATE TABLE IF NOT EXISTS knowledge (
            id TEXT PRIMARY KEY, content TEXT, type TEXT, source TEXT,
            confidence REAL, learned_at REAL, last_accessed REAL,
            access_count INTEGER, metadata TEXT)""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS relationships (
            from_id TEXT, to_id TEXT, relation_type TEXT,
            strength REAL, created_at REAL,
            PRIMARY KEY (from_id, to_id, relation_type))""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, name TEXT, first_met REAL,
            last_interaction REAL, interaction_count INTEGER, data TEXT)""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY, name TEXT, description TEXT,
            acquired_at REAL, proficiency REAL, practice_count INTEGER,
            success_rate REAL, last_used REAL, data TEXT)""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS learning_goals (
            id TEXT PRIMARY KEY, goal TEXT, created_at REAL,
            target_completion REAL, priority REAL, progress REAL,
            completed BOOLEAN, notes TEXT)""")
        
        c.execute("""CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY, question TEXT, created_at REAL,
            importance REAL, answered BOOLEAN, answer TEXT, answered_at REAL)""")
        
        with self._get_conn() as conn:
            conn.commit()
    
    def add_knowledge(self, content: str, type: str, source: str = "learning",
                      confidence: float = 0.7, metadata: Optional[Dict] = None) -> str:
        """Add knowledge — thread-safe."""
        node_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        with self._lock:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                # Check existing
                existing = self.get_knowledge(node_id)
                if existing:
                    self._update_knowledge_access(node_id, 0.05) # Fixed boost
                    return node_id
                
                c = conn.cursor()
                c.execute("""INSERT INTO knowledge VALUES (?,?,?,?,?,?,?,?,?)""",
                          (node_id, content, type, source, confidence, time.time(),
                           time.time(), 1, json.dumps(metadata or {})))
                # conn.commit() handled by context manager
        
        logger.info("📚 Learned: %s...", content[:80])
        return node_id
    
    def get_knowledge(self, node_id: str) -> Optional[Dict]:
        """Get knowledge by ID"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM knowledge WHERE id = ?", (node_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    def search_knowledge(self, query: str, type: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """Search knowledge"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            if type:
                c.execute("""SELECT * FROM knowledge WHERE type = ? AND content LIKE ?
                            ORDER BY confidence DESC LIMIT ?""",
                         (type, f"%{query}%", limit))
            else:
                c.execute("""SELECT * FROM knowledge WHERE content LIKE ?
                            ORDER BY confidence DESC LIMIT ?""",
                         (f"%{query}%", limit))
            return [dict(row) for row in c.fetchall()]
    
    def _update_knowledge_access(self, node_id: str, confidence_boost: float = 0.0):
        """Update access — caller must hold _lock or call within with self._lock."""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("""UPDATE knowledge SET last_accessed = ?, access_count = access_count + 1,
                        confidence = MIN(1.0, confidence + ?) WHERE id = ?""",
                     (time.time(), confidence_boost, node_id))
            conn.commit()
    
    def count_nodes(self, type: Optional[str] = None) -> int:
        """Count nodes"""
        with self._get_conn() as conn:
            c = conn.cursor()
            if type:
                c.execute("SELECT COUNT(*) FROM knowledge WHERE type = ?", (type,))
            else:
                c.execute("SELECT COUNT(*) FROM knowledge")
            return c.fetchone()[0]
    
    def remember_person(self, name: str, interaction_data: Dict) -> str:
        """Remember person"""
        with self._lock:
            person_id = hashlib.sha256(name.lower().encode()).hexdigest()[:16]
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT data FROM people WHERE id = ?", (person_id,))
                row = c.fetchone()
            
                if row:
                    data = json.loads(row[0])
                    data["last_interaction"] = time.time()
                    data["interaction_count"] += 1
                    data["conversation_history"].append(interaction_data)
                    data["conversation_history"] = data["conversation_history"][-100:]
                
                    c.execute("""UPDATE people SET last_interaction = ?,
                                interaction_count = ?, data = ? WHERE id = ?""",
                             (time.time(), data["interaction_count"], json.dumps(data), person_id))
                else:
                    data = {
                        "name": name, "first_met": time.time(),
                        "last_interaction": time.time(), "interaction_count": 1,
                        "conversation_history": [interaction_data],
                        "preferences": {}, "topics_discussed": []
                    }
                    c.execute("""INSERT INTO people VALUES (?,?,?,?,?,?)""",
                             (person_id, name, time.time(), time.time(), 1, json.dumps(data)))
            
            logger.info("👤 Remembered: %s", name)
            return person_id
    
    def get_person(self, name: str) -> Optional[Dict]:
        """Get person"""
        person_id = hashlib.sha256(name.lower().encode()).hexdigest()[:16]
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM people WHERE id = ?", (person_id,))
            row = c.fetchone()
            if row:
                data = dict(row)
                data.update(json.loads(data["data"]))
                del data["data"]
                return data
        return None
    
    def add_skill(self, name: str, description: str, proficiency: float = 0.1) -> str:
        """Add skill"""
        with self._lock:
            skill_id = hashlib.sha256(name.lower().encode()).hexdigest()[:16]
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("""INSERT INTO skills VALUES (?,?,?,?,?,?,?,?,?)""",
                         (skill_id, name, description, time.time(), proficiency,
                          0, 0.0, None, json.dumps({})))
                conn.commit()
            logger.info("🎓 Skill: %s", name)
            return skill_id
    
    def practice_skill(self, skill_id: str, success: bool):
        """Practice skill"""
        with self._lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT practice_count, success_rate, proficiency FROM skills WHERE id = ?", (skill_id,))
                row = c.fetchone()
                if not row:
                    return
            
                count, rate, prof = row
                new_rate = (rate * count + (1.0 if success else 0.0)) / (count + 1)
                new_prof = min(1.0, prof + (0.05 if success else 0.01) * (1.0 - prof))
            
                c.execute("""UPDATE skills SET practice_count = practice_count + 1,
                            success_rate = ?, proficiency = ?, last_used = ? WHERE id = ?""",
                         (new_rate, new_prof, time.time(), skill_id))
    
    def get_skills(self, min_prof: float = 0.0) -> List[Dict]:
        """Get skills"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM skills WHERE proficiency >= ? ORDER BY proficiency DESC", (min_prof,))
            return [dict(row) for row in c.fetchall()]
    
    def add_learning_goal(self, goal: str, priority: float = 0.5, target_days: int = 7) -> str:
        """Add goal"""
        with self._lock:
            goal_id = hashlib.sha256(goal.encode()).hexdigest()[:16]
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("""INSERT OR REPLACE INTO learning_goals VALUES (?,?,?,?,?,?,?,?)""",
                         (goal_id, goal, time.time(), time.time() + target_days * 86400,
                          priority, 0.0, False, ""))
                conn.commit()
            logger.info("🎯 Goal: %s", goal)
            return goal_id
    
    def get_active_learning_goals(self) -> List[Dict]:
        """Get active goals"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM learning_goals WHERE completed = FALSE ORDER BY priority DESC")
            return [dict(row) for row in c.fetchall()]
    
    def ask_question(self, question: str, importance: float = 0.5) -> str:
        """Ask question"""
        with self._lock:
            q_id = hashlib.sha256(question.encode()).hexdigest()[:16]
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("""INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?)""",
                         (q_id, question, time.time(), importance, False, None, None))
                conn.commit()
            logger.info("❓ Question: %s", question)
            return q_id
    
    def answer_question(self, q_id: str, answer: str):
        """Answer question"""
        with self._lock:
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("UPDATE questions SET answered = TRUE, answer = ?, answered_at = ? WHERE id = ?",
                         (answer, time.time(), q_id))
                conn.commit()
        
            with self._get_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT question FROM questions WHERE id = ?", (q_id,))
                row = c.fetchone()
                question = row[0] if row else "Unknown"
            self.add_knowledge(f"Q: {question}\nA: {answer}", type="qa",
                              source="self_inquiry", confidence=0.8)
    
    def get_unanswered_questions(self, limit: int = 10) -> List[Dict]:
        """Get unanswered"""
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM questions WHERE answered = FALSE ORDER BY importance DESC LIMIT ?", (limit,))
            return [dict(row) for row in c.fetchall()]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get stats"""
        with self._get_conn() as conn:
            return {
                "total_knowledge": self.count_nodes(),
                "facts": self.count_nodes("fact"),
                "concepts": self.count_nodes("concept"),
                "skills": len(self.get_skills()),
                "people_known": conn.execute("SELECT COUNT(*) FROM people").fetchone()[0],
                "active_learning_goals": len(self.get_active_learning_goals()),
                "unanswered_questions": len(self.get_unanswered_questions())
            }

    def to_vis_data(self) -> Dict[str, List[Dict]]:
        """Export graph data for vis-network visualization."""
        nodes = []
        edges = []
        try:
            with self._get_conn() as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                # Fetch nodes
                c.execute("SELECT id, content, type, confidence, metadata FROM knowledge LIMIT 100")
            for row in c.fetchall():
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                if meta.get("test"):
                    continue
                    
                # Color map based on type
                colors = {
                    "fact": "#8a2be2",
                    "concept": "#00ffa3",
                    "qa": "#e6a800",
                    "learning": "#00e5ff"
                }
                nodes.append({
                    "id": row["id"],
                    "label": row["content"][:20] + "..." if len(row["content"]) > 20 else row["content"],
                    "title": row["content"],
                    "color": colors.get(row["type"], "#ccc"),
                    "value": row["confidence"]
                })
            
            # Fetch edges
            c.execute("SELECT from_id, to_id, relation_type, strength FROM relationships LIMIT 200")
            for row in c.fetchall():
                edges.append({
                    "from": row["from_id"],
                    "to": row["to_id"],
                    "label": row["relation_type"],
                    "width": row["strength"] * 2
                })
            
            # If empty, add a primary node
            if not nodes:
                nodes.append({"id": "aura-core", "label": "Aura Core", "color": "#ff00ff"})

            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            logger.error("Failed to generate vis data: %s", e)
            return {"nodes": [{"id": "error", "label": "Graph Error", "color": "red"}], "edges": []}

    def get_random_node(self) -> Optional[str]:
        """Returns a random knowledge node's content."""
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT content FROM knowledge ORDER BY RANDOM() LIMIT 1")
            row = c.fetchone()
            return row[0] if row else None

    def get_sparse_nodes(self, limit: int = 5) -> List[str]:
        """Identify nodes with the few relationships (novelty targets)."""
        query = """
        SELECT k.content, COUNT(r.from_id) as rel_count
        FROM knowledge k
        LEFT JOIN relationships r ON k.id = r.from_id OR k.id = r.to_id
        GROUP BY k.id
        ORDER BY rel_count ASC
        LIMIT ?
        """
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(query, (limit,))
            return [row[0] for row in c.fetchall() if row[0]]

# Alias for compatibility
KnowledgeGraph = PersistentKnowledgeGraph

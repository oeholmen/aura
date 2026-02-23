"""[DEPRECATED] Legacy Learning and Memory System.
Superseded by core/learning/ package and core/meta/meta_learning_engine.py.
"""
import warnings

warnings.warn("core/learning.py is deprecated. Use core/learning package or meta_learning instead.", DeprecationWarning)

import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Aura.Learning")


class LearningSystem:
    """Enables Aura to learn from experience and improve over time.
    
    Features:
    - Memory of successful/failed strategies
    - Pattern recognition for what works
    - Continuous improvement through reinforcement
    - Knowledge accumulation
    """
    
    def __init__(self, vector_memory=None):
        self.logger = logger
        self.vector_memory = vector_memory
        
        # Short-term memory (current session)
        self.execution_history = []
        
        # Strategy effectiveness tracking
        self.strategy_stats = defaultdict(lambda: {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "avg_quality": 0.0
        })
        
        # Learned patterns
        self.learned_patterns = {
            "successful_queries": [],
            "failed_queries": [],
            "good_sources": set(),
            "bad_sources": set(),
        }
        
        # Skill improvement tracking
        self.skill_performance = defaultdict(lambda: {
            "total_runs": 0,
            "successful_runs": 0,
            "last_success_time": None,
            "common_failures": []
        })
    
    def record_execution(
        self,
        goal: Dict[str, Any],
        result: Dict[str, Any],
        skill_used: str,
        strategy: str = "default"
    ):
        """Record an execution for learning.
        """
        execution_record = {
            "timestamp": datetime.now().isoformat(),
            "goal": goal,
            "result": result,
            "skill": skill_used,
            "strategy": strategy,
            "success": result.get("ok", False),
            "quality_score": self._calculate_quality_score(result)
        }
        
        # Add to history
        self.execution_history.append(execution_record)
        
        # Update strategy stats
        self._update_strategy_stats(strategy, execution_record)
        
        # Update skill performance
        self._update_skill_performance(skill_used, execution_record)
        
        # Learn patterns
        self._learn_from_execution(execution_record)
        
        # Store in long-term memory if available
        if self.vector_memory:
            self._store_in_long_term_memory(execution_record)
        
        self.logger.info(
            f"Recorded execution: {skill_used}/{strategy} - "
            f"{'✓ Success' if execution_record['success'] else '✗ Failed'} "
            f"(Quality: {execution_record['quality_score']:.2f})"
        )
    
    def _calculate_quality_score(self, result: Dict[str, Any]) -> float:
        """Calculate quality score for a result (0.0 to 1.0).
        """
        if not result.get("ok"):
            return 0.0
        
        score = 0.5  # Base score for success
        
        # Content quality
        if "results" in result:
            num_results = len(result.get("results", []))
            score += min(0.3, num_results * 0.06)  # Up to 0.3 for results
        
        if "summary" in result:
            summary_length = len(result.get("summary", ""))
            if summary_length > 100:
                score += 0.1
            if summary_length > 500:
                score += 0.1
        
        # Validation score
        validation = result.get("validation", {})
        if validation.get("is_valid"):
            score += 0.2
        
        # Penalty for using fallback strategies
        if result.get("engine") == "duckduckgo_lite":
            pass  # No penalty, this is our primary
        elif result.get("engine") in ["brave", "wikipedia"]:
            score -= 0.05  # Small penalty for fallback
        
        return min(1.0, score)
    
    def _update_strategy_stats(self, strategy: str, record: Dict[str, Any]):
        """Update statistics for a strategy"""
        stats = self.strategy_stats[strategy]
        stats["attempts"] += 1
        
        if record["success"]:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        
        # Update average quality (running average)
        quality = record["quality_score"]
        n = stats["attempts"]
        stats["avg_quality"] = (stats["avg_quality"] * (n - 1) + quality) / n
    
    def _update_skill_performance(self, skill: str, record: Dict[str, Any]):
        """Track skill-specific performance"""
        perf = self.skill_performance[skill]
        perf["total_runs"] += 1
        
        if record["success"]:
            perf["successful_runs"] += 1
            perf["last_success_time"] = record["timestamp"]
        else:
            # Track common failure reasons
            error = record["result"].get("error", "unknown")
            if error not in perf["common_failures"]:
                perf["common_failures"].append(error)
    
    def _learn_from_execution(self, record: Dict[str, Any]):
        """Extract patterns and learnings from execution"""
        goal = record["goal"]
        result = record["result"]
        success = record["success"]
        
        # Extract query if present
        query = None
        if isinstance(goal.get("objective"), dict):
            query = goal["objective"].get("query")
        elif isinstance(goal.get("objective"), str):
            query = goal["objective"]
        
        if query:
            if success and record["quality_score"] > 0.7:
                # Remember successful queries
                self.learned_patterns["successful_queries"].append({
                    "query": query,
                    "strategy": record["strategy"],
                    "quality": record["quality_score"]
                })
                
                # Remember good sources
                if "results" in result:
                    for res in result["results"][:3]:  # Top 3 results
                        url = res.get("url", "")
                        if url:
                            import urllib.parse
                            domain = urllib.parse.urlparse(url).netloc
                            self.learned_patterns["good_sources"].add(domain)
            
            elif not success:
                # Remember failed queries
                self.learned_patterns["failed_queries"].append({
                    "query": query,
                    "strategy": record["strategy"],
                    "error": result.get("error")
                })
    
    def _store_in_long_term_memory(self, record: Dict[str, Any]):
        """Store execution in vector memory with semantic typing (Strategy vs UserPref)"""
        try:
            goal_text = str(record["goal"].get("objective", ""))
            result_summary = str(record["result"].get("summary", ""))[:500]
            success = record["success"]
            
            # 1. Store as Strategy Memory (General Pattern)
            if success and record["quality_score"] > 0.6:
                strategy_text = (
                    f"To achieve '{goal_text}', handling intent '{record['goal'].get('intent', 'unknown')}', "
                    f"I used skill '{record['skill']}' with strategy '{record['strategy']}'. "
                    f"Result quality was {record['quality_score']:.2f}."
                )
                
                metadata = {
                    "type": "strategy",
                    "skill": record["skill"],
                    "scope": f"component:{record['skill']}",
                    "success": success,
                    "timestamp": record["timestamp"]
                }
                
                self.vector_memory.add(strategy_text, metadata=metadata)
                self.logger.debug("Stored Strategy Memory")

            # 2. Heuristic: Deduce User Preference from repeatedly successful interactions
            # (In a real v2.6 implementation, this would be an explicit specific turn-level policy check)
            
        except Exception as e:
            self.logger.error("Failed to store in long-term memory: %s", e)
    
    def get_best_strategy(self, skill: str, goal: Dict[str, Any]) -> Optional[str]:
        """Recommend the best strategy based on learned experience.
        """
        # Get all strategies that have been used
        relevant_strategies = {
            name: stats for name, stats in self.strategy_stats.items()
            if stats["attempts"] > 0
        }
        
        if not relevant_strategies:
            return None
        
        # Sort by quality and success rate
        strategy_scores = []
        for name, stats in relevant_strategies.items():
            if stats["attempts"] < 3:  # Need minimum attempts
                continue
            
            success_rate = stats["successes"] / stats["attempts"]
            quality = stats["avg_quality"]
            
            # Combined score (weighted)
            score = (success_rate * 0.6) + (quality * 0.4)
            strategy_scores.append((name, score))
        
        if not strategy_scores:
            return None
        
        # Return best strategy
        strategy_scores.sort(key=lambda x: x[1], reverse=True)
        best_strategy, best_score = strategy_scores[0]
        
        if best_score > 0.5:  # Minimum threshold
            self.logger.info("Recommending strategy '%s' (score: %.2f)", best_strategy, best_score)
            return best_strategy
        
        return None
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Generate a performance report showing what Aura has learned.
        """
        total_executions = len(self.execution_history)
        successful = sum(1 for e in self.execution_history if e["success"])
        
        stats_copy = {k: v.copy() for k, v in self.strategy_stats.items()}
        skills_copy = {k: v.copy() for k, v in self.skill_performance.items()}
        
        report = {
            "total_executions": total_executions,
            "successful_executions": successful,
            "success_rate": successful / total_executions if total_executions > 0 else 0,
            "strategies": stats_copy,
            "skills": skills_copy,
            "patterns": {
                "successful_queries_count": len(self.learned_patterns["successful_queries"]),
                "failed_queries_count": len(self.learned_patterns["failed_queries"]),
                "trusted_sources_count": len(self.learned_patterns["good_sources"]),
            }
        }
        
        return report
    
    def get_learning_insights(self) -> List[str]:
        """Generate human-readable insights about what's been learned.
        """
        insights = []
        
        # Overall performance
        report = self.get_performance_report()
        success_rate = report["success_rate"] * 100
        insights.append(f"Current success rate: {success_rate:.1f}%")
        
        # Best performing strategy
        if self.strategy_stats:
            best_strategy = max(
                self.strategy_stats.items(),
                key=lambda x: x[1]["avg_quality"]
            )
            insights.append(
                f"Most effective strategy: {best_strategy[0]} "
                f"(quality: {best_strategy[1]['avg_quality']:.2f})"
            )
        
        # Trusted sources
        if self.learned_patterns["good_sources"]:
            top_sources = list(self.learned_patterns["good_sources"])[:5]
            insights.append(f"Trusted sources discovered: {', '.join(top_sources)}")
        
        # Skill improvements
        for skill, perf in self.skill_performance.items():
            if perf["total_runs"] > 5:
                skill_success = (perf["successful_runs"] / perf["total_runs"]) * 100
                insights.append(f"{skill}: {skill_success:.1f}% success rate")
        
        return insights

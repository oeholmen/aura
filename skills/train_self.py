"""skills/train_self.py - Neuroplasticity / Self-Fine-Tuning Skill
Provides the architecture for Aura to learn from her own high-value experiences.
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger("Aura.Training")

class TrainSelfSkill:
    """Sleep and Learn: Neuroplasticity simulation.
    Orchestrates the preparation and trigger for local model fine-tuning.
    """

    name = "train_self"
    
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = workspace_root
        self.dataset_path = os.path.join(workspace_root, "data/training/dataset.jsonl")
        os.makedirs(os.path.dirname(self.dataset_path), exist_ok=True)

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        action = goal.get("action", "collect_memories")
        
        if action == "collect_memories":
            return await self._collect_high_value_memories(context)
        elif action == "trigger_tuning":
            return await self._trigger_finetuning(goal.get("params", {}))
            
        return {"ok": False, "error": f"Unknown action: {action}"}

    async def _collect_high_value_memories(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gathers successful interactions for future training (v13: no fake data)."""
        try:
            logger.info("Collecting high-value memories for neuroplasticity...")
            
            # Query actual conversation history from context
            history = context.get("history", [])
            collected = 0
            
            if not history:
                return {
                    "ok": True,
                    "message": "No conversation history available to collect memories from.",
                    "collected": 0
                }
            
            with open(self.dataset_path, "a") as f:
                for turn in history[-10:]:  # Last 10 turns
                    if isinstance(turn, dict) and turn.get("role") == "assistant":
                        entry = {
                            "instruction": "Continue the conversation naturally.",
                            "input": "",
                            "output": turn.get("content", "")[:500]
                        }
                        f.write(json.dumps(entry) + "\n")
                        collected += 1
                
            return {
                "ok": True,
                "message": f"Collected {collected} high-value memories for future consolidation.",
                "collected": collected
            }
        except Exception as e:
            logger.error("Memory collection failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def _trigger_finetuning(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Consolidate memories into permanent knowledge (Self-Learning).
        Instead of full fine-tuning (expensive), we distill high-value memories
        into a 'Self-Learned Knowledge' file that is injected into context.
        """
        try:
            logger.info("🧠 Consolidating short-term memories into long-term knowledge...")
            
            # 1. Read dataset
            if not os.path.exists(self.dataset_path):
                return {"ok": False, "error": "No memories to consolidate."}
                
            knowledge_path = os.path.join(self.workspace_root, "core/knowledge/self_learned.md")
            os.makedirs(os.path.dirname(knowledge_path), exist_ok=True)
            
            # 2. Distill (mock distillation for now, in real expanded ver we'd use LLM to summarize)
            new_knowledge = []
            with open(self.dataset_path, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if "output" in data:
                            new_knowledge.append(f"- **Learned Pattern**: {data['output'][:100]}...")
                    except:
                        pass
            
            # 3. Append to Knowledge Base
            timestamp = datetime.now().isoformat()
            with open(knowledge_path, "a") as f:
                f.write(f"\n\n### Consolidation {timestamp}\n")
                f.write("\n".join(new_knowledge))
                
            # 4. Clear buffer
            open(self.dataset_path, 'w').close()
            
            return {
                "ok": True,
                "message": f"Consolidated {len(new_knowledge)} insights into Long-Term Memory.",
                "path": knowledge_path
            }
        except Exception as e:
            logger.error("Consolidation failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _get_dataset_size(self) -> int:
        if not os.path.exists(self.dataset_path): return 0
        with open(self.dataset_path, "r") as f:
            return sum(1 for _ in f)

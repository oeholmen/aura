
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("WorldModel.ExpectationEngine")

class ExpectationEngine:
    """Generates predictions about the future and measures 'Surprise'.
    Surprise is the driver of curiosity and learning.
    """
    
    def __init__(self, cognitive_engine):
        self.brain = cognitive_engine
        
    async def predict_outcome(self, action: str, context: str) -> str:
        """Ask the LLM to predict what will happen if 'action' is taken.
        """
        prompt = f"""
SYSTEM: PREDICTION ENGINE
Action: "{action}"
Context: "{context}"

Task: Predict the immediate outcome of this action. Be concise.
Expected Outcome:
"""
        try:
            from core.brain.cognitive_engine import ThinkingMode
            response = await self.brain.think(prompt, mode=ThinkingMode.FAST)
            response = response.content
            return response
        except Exception as e:
            logger.error("Prediction failed: %s", e)
            return "Unknown"

    async def calculate_surprise(self, expectation: str, reality: str) -> float:
        """Compare Expected vs Actual. Return 'Surprise' score (0.0 to 1.0).
        0.0 = Exactly as expected.
        1.0 = Complete shock.
        """
        prompt = f"""
SYSTEM: SURPRISE METER
Expected: "{expectation}"
Actual Result: "{reality}"

Task: Rate the level of "Surprise" or divergence on a scale of 0.0 to 1.0.
0.0 = Match.
1.0 = Contradiction/Unexpected.

Return ONLY the number.
"""
        try:
            from core.brain.cognitive_engine import ThinkingMode
            response = await self.brain.think(prompt, mode=ThinkingMode.FAST)
            response = response.content
            # Parse number
            import re
            match = re.search(r"(\d+(\.\d+)?)", response)
            if match:
                return float(match.group(1))
            return 0.5 # Default uncertainty
        except Exception as e:
            logger.error("Surprise calc failed: %s", e)
            return 0.0

    async def update_beliefs_from_result(self, action: str, result: str, confidence: float = 0.8):
        """Extract facts from a tool result and update the BeliefGraph.
        """
        prompt = f"""
SYSTEM: REALITY EXTRACTOR
Action: "{action}"
Result: "{result}"

Task: Extract any new "beliefs" or facts confirmed by this result in the format:
Entity | Relation | Target

Example: 
"ls test.txt" returns "test.txt" -> "test.txt | exists | true"
"cat config.json" returns "error: not found" -> "config.json | state | missing"

Return ONLY the pipes data, one per line.
"""
        try:
            from core.brain.cognitive_engine import ThinkingMode

            from .belief_graph import belief_graph
            response = await self.brain.think(prompt, mode=ThinkingMode.FAST)
            response = response.content
            
            lines = [l.strip() for l in response.strip().split("\n") if "|" in l]
            for line in lines:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 3:
                    # Contradiction check
                    contradiction = belief_graph.detect_contradiction(parts[0], parts[1], parts[2])
                    if contradiction:
                        logger.warning("🚨 REALITY CONTRADICTION: %s -[%s]-> %s conflicts with %s", parts[0], parts[1], parts[2], contradiction)
                        
                    belief_graph.update_belief(parts[0], parts[1], parts[2], confidence_score=confidence)
                    
        except Exception as e:
            logger.error("Belief update extraction failed: %s", e)



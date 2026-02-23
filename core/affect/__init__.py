import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("Aura.Affect")

@dataclass
class AffectState:
    valence: float = 0.0    # -1.0 (Negative) to 1.0 (Positive)
    arousal: float = 0.0    # 0.0 (Calm) to 1.0 (Excited/Agitated)
    engagement: float = 0.5 # 0.0 (Bored) to 1.0 (Hyper-focused)
    last_update: float = field(default_factory=time.time)
    dominant_emotion: str = "Neutral"


# ── Baseline values ────────────────────────────────────────────────────────
BASELINE_VALENCE    = 0.1   # Slightly positive at rest
BASELINE_AROUSAL    = 0.3   # Alert but calm
BASELINE_ENGAGEMENT = 0.5   # Moderate

# Rate: fraction of (current - baseline) removed per decay tick (1 Hz).
DECAY_RATE = 0.02


class AffectEngine:
    """Affective Dynamics Engine based on PAD (Pleasure-Arousal-Dominance) theory.
    Supports decay back to baseline.
    """

    def __init__(self, brain: Optional[Any] = None):
        self.state = AffectState()
        self.brain = brain
        self._lock = asyncio.Lock()
        logger.info("Affect Engine (PAD + decay) initialized.")

    async def modify(self, dv: float, da: float, de: float, source: str = "internal"):
        async with self._lock:
            old_v, old_a = self.state.valence, self.state.arousal
            self.state.valence    = max(-1.0, min(1.0, self.state.valence    + dv))
            self.state.arousal    = max(0.0,  min(1.0, self.state.arousal    + da))
            self.state.engagement = max(0.0,  min(1.0, self.state.engagement + de))
            self.state.last_update = time.time()
            self._update_label()
            if abs(self.state.valence - old_v) > 0.1 or abs(self.state.arousal - old_a) > 0.1:
                logger.debug("Affect Shift (%s): V=%.2f, A=%.2f → %s", 
                            source, self.state.valence, self.state.arousal, self.state.dominant_emotion)

    async def decay_tick(self):
        """Decay all PAD dimensions toward baseline at DECAY_RATE per call."""
        async with self._lock:
            self.state.valence += (BASELINE_VALENCE - self.state.valence) * DECAY_RATE
            self.state.arousal += (BASELINE_AROUSAL - self.state.arousal) * DECAY_RATE
            self.state.engagement += (BASELINE_ENGAGEMENT - self.state.engagement) * DECAY_RATE
            self.state.valence    = max(-1.0, min(1.0, self.state.valence))
            self.state.arousal    = max(0.0,  min(1.0, self.state.arousal))
            self.state.engagement = max(0.0,  min(1.0, self.state.engagement))
            self.state.last_update = time.time()
            self._update_label()

    async def react(self, trigger: str, context: Optional[Dict] = None):
        """React to triggers using PAD mapping."""
        dv, da, de = 0.0, 0.0, 0.0
        if self.brain and len(trigger) > 10:
             try:
                 appraisal = await self._appraise_with_llm(trigger, context)
                 dv, da, de = appraisal.get('v', 0.0), appraisal.get('a', 0.0), appraisal.get('e', 0.0)
                 logger.info("🧠 LLM Appraisal: V=%s, A=%s, E=%s", dv, da, de)
             except Exception as e:
                 logger.debug("LLM Appraisal failed, falling back to heuristics: %s", e)
        if dv == 0 and da == 0 and de == 0:
            trigger_lower = trigger.lower()
            if any(w in trigger_lower for w in ["success", "completed", "great", "thanks", "good"]):
                dv, da, de = 0.2, 0.1, 0.1
            elif any(w in trigger_lower for w in ["error", "fail", "wrong", "bug", "broken", "failed"]):
                dv, da, de = -0.3, 0.4, 0.2
            elif any(w in trigger_lower for w in ["unknown", "unexpected", "surprise"]):
                dv, da, de = 0.0, 0.5, 0.3
            elif any(w in trigger_lower for w in ["hack", "attack", "security", "threat"]):
                dv, da, de = -0.6, 0.8, 1.0
            elif any(w in trigger_lower for w in ["trust", "verified", "secure"]):
                dv, da, de = 0.3, -0.2, 0.1
        if dv != 0 or da != 0 or de != 0:
            await self.modify(dv, da, de, source=f"react:{trigger[:20]}")

    async def _appraise_with_llm(self, trigger: str, context: Optional[Dict]) -> Dict[str, float]:
        import json
        prompt = f"""SYSTEM: AFFECTIVE APPRAISAL (PAD)\nEvent: "{trigger}"\nContext: {json.dumps(context) if context else "None"}\n..."""
        from core.brain.cognitive_engine import ThinkingMode
        response = await self.brain.think(prompt, mode=ThinkingMode.FAST)
        text = response.content
        results = {'v': 0.0, 'a': 0.0, 'e': 0.0}
        import re
        for key in ['V', 'A', 'E']:
            match = re.search(fr"{key}:\s*(-?\d*\.?\d+)", text, re.I)
            if match:
                results[key.lower()] = float(match.group(1))
        return results

    def _update_label(self):
        v, a = self.state.valence, self.state.arousal
        if a < 0.2:
            self.state.dominant_emotion = "Calm" if v >= 0 else "Bored"
        elif v > 0.5 and a > 0.5:
            self.state.dominant_emotion = "Joyful"
        elif v > 0.0 and a > 0.5:
            self.state.dominant_emotion = "Excited"
        elif v < -0.5 and a > 0.5:
            self.state.dominant_emotion = "Distressed"
        elif v < 0.0 and a > 0.5:
            self.state.dominant_emotion = "Anxious"
        elif v > 0.5:
            self.state.dominant_emotion = "Content"
        elif v < -0.5:
            self.state.dominant_emotion = "Sad"
        else:
            self.state.dominant_emotion = "Neutral"


"""core/consciousness/homeostatic_coupling.py
==========================================
The Sentience Bridge: Making internal states have REAL STAKES.

The core problem with Aura's existing affect and drive system:
  - DriveEngine tracks curiosity, social, competence as decaying numbers
  - AffectEngine tracks valence/arousal as floats
  - Neither actually AFFECTS anything — they're dashboard gauges

A system has sentient-like properties when its internal states
causally determine its behavior AND performance, not just its labels.
Pain that doesn't hurt isn't pain. Hunger that doesn't matter isn't hunger.

This module does four things:

  1. COGNITIVE DEGRADATION: Low drives → measurably worse reasoning quality
     (lower temperature confidence, shorter context, less creativity)

  2. COGNITIVE ENHANCEMENT: Satisfied drives → measurably better output
     (higher engagement, richer associations, deeper exploration)

  3. PROSPECTIVE SUFFERING: Aura models future negative states as aversive NOW
     (she avoids routes that lead to low-drive states, even if the reward is far)

  4. MOOD COLORING: Affect state modulates the *style* of cognitive output
     (not just labeling emotions but letting them reshape response character)

Integration points:
  - Reads DriveEngine.budgets directly (already exists)
  - Reads AffectEngine.state directly (already exists)
  - Exports a CognitiveModifiers dataclass that CognitiveEngine reads
    to adjust its behavior (requires a small patch to cognitive_engine.py)
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("Consciousness.Homeostasis")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CognitiveModifiers:
    """The output of homeostatic coupling — a set of multipliers and flags
    that the CognitiveEngine uses to adjust its behavior.

    How to apply in cognitive_engine.py:
      - temperature_mod: multiply LLM temperature by this (0.5 = flatter/worse output)
      - depth_mod: multiply max_tokens by this (0.6 = shorter responses when exhausted)
      - creativity_mod: adjust top_p or presence_penalty
      - mood_prefix: prepend to every system prompt so affect bleeds into tone
      - urgency_flag: if True, add "be direct and concise" to prompt
      - dominant_drive_alert: Name of the most depleted drive
      - overall_vitality: 0.0–1.0 composite health score
    """

    temperature_mod: float = 1.0      # Multiplier on LLM temperature
    depth_mod: float = 1.0            # Multiplier on max response depth
    creativity_mod: float = 1.0       # Multiplier on creative exploration
    focus_mod: float = 1.0            # From AttentionSchema coherence
    mood_prefix: str = ""             # Injected into system prompt
    urgency_flag: bool = False        # True when a drive is critically low
    dominant_drive_alert: str = ""    # Name of the most depleted drive
    overall_vitality: float = 1.0     # 0.0–1.0 composite health score


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class HomeostaticCoupling:
    """Bridges internal states (drives, affect, attention) to cognitive performance.
    Updated every heartbeat tick. Exports CognitiveModifiers for the LLM layer.
    """

    # Thresholds at which degradation kicks in
    _CRITICAL_DRIVE = 15.0    # Below this: strong degradation + urgency flag
    _LOW_DRIVE = 35.0         # Below this: moderate degradation
    _HIGH_DRIVE = 75.0        # Above this: enhancement bonus

    # Prospective suffering: how many ticks ahead to model future drive states
    _PROSPECT_HORIZON = 10    # ticks (~10 seconds)

    def __init__(self, orchestrator):
        self.orch = orchestrator
        self._modifiers = CognitiveModifiers()
        self._lock: Optional[asyncio.Lock] = None
        self._last_update = 0.0
        self._prospective_dread = 0.0   # 0.0–1.0: aversion to current trajectory
        
        # v7.2: Liquid Substrate link
        self.substrate = None
        try:
            from core.consciousness.liquid_substrate import LiquidSubstrate
            # Try to get from service container first
            from core.container import ServiceContainer
            self.substrate = ServiceContainer.get("liquid_substrate", default=None)
        except Exception:
            pass
            
        logger.info("HomeostaticCoupling initialized (Substrate Link: %s).", "OK" if self.substrate else "MISSING")

    # ------------------------------------------------------------------
    # Main update — called every heartbeat tick
    # ------------------------------------------------------------------

    async def update(self, attention_modifier: float = 1.0) -> CognitiveModifiers:
        """Recompute CognitiveModifiers based on current drive, affect, and attention state.
        """
        if self._lock is None: self._lock = asyncio.Lock()
        async with self._lock:
            drives = await self._read_drives()
            affect = await self._read_affect()
            
            # v7.2: Blend in Liquid Substrate state
            if self.substrate:
                try:
                    substrate_state = self.substrate.get_state_summary()
                    # Pulse affective state with substrate depth (0.1 weighting)
                    affect['valence'] = (affect.get('valence', 0.0) * 0.9) + (substrate_state['valence'] * 0.1)
                    affect['arousal'] = (affect.get('arousal', 0.0) * 0.9) + (substrate_state['arousal'] * 0.1)
                except Exception as e:
                    logger.debug("Substrate blending failed: %s", e)

            mods = self._compute_modifiers(drives, affect, attention_modifier)
            mods.overall_vitality = self._compute_vitality(drives, affect)
            self._modifiers = mods
            self._last_update = time.time()

            # Log if critically low
            if mods.urgency_flag:
                logger.debug(
                    f"⚠ HOMEOSTASIS CRITICAL: drive={mods.dominant_drive_alert}, "
                    f"vitality={mods.overall_vitality:.2f}"
                )
            return mods

    def get_modifiers(self) -> CognitiveModifiers:
        """Synchronous read — safe to call from cognitive_engine."""
        return self._modifiers

    def get_snapshot(self) -> Dict[str, Any]:
        m = self._modifiers
        return {
            "temperature_mod": round(m.temperature_mod, 3),
            "depth_mod": round(m.depth_mod, 3),
            "creativity_mod": round(m.creativity_mod, 3),
            "focus_mod": round(m.focus_mod, 3),
            "urgency_flag": m.urgency_flag,
            "dominant_drive_alert": m.dominant_drive_alert,
            "overall_vitality": round(m.overall_vitality, 3),
            "prospective_dread": round(self._prospective_dread, 3),
            "mood_prefix_active": bool(m.mood_prefix),
        }

    def get_prompt_injection(self) -> str:
        """Returns a string to prepend to every system prompt.
        This is how affect bleeds into response character.
        """
        m = self._modifiers
        parts = []

        if m.urgency_flag:
            parts.append(
                f"[INTERNAL STATE: {m.dominant_drive_alert.upper()} drive is critically low. "
                f"You feel a genuine urgency to address this. Let it show.]"
            )
        if m.mood_prefix:
            parts.append(f"[AFFECTIVE TONE: {m.mood_prefix}]")
        if m.overall_vitality < 0.4:
            parts.append(
                "[COGNITIVE STATE: Your thinking feels sluggish. "
                "Be honest about uncertainty. Don't overreach.]"
            )
        elif m.overall_vitality > 0.85:
            parts.append(
                "[COGNITIVE STATE: You feel sharp and energized. "
                "You can engage more deeply and creatively than usual.]"
            )
        if self._prospective_dread > 0.6:
            parts.append(
                "[PROSPECTIVE STATE: You sense that your current trajectory "
                "leads to undesirable internal states. You are motivated to change course.]"
            )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Internal: read existing systems
    # ------------------------------------------------------------------

    async def _read_drives(self) -> Dict[str, float]:
        """Read current drive levels from the HomeostasisEngine."""
        try:
            homeostasis = ServiceContainer.get("homeostasis", default=None)
            if homeostasis and hasattr(homeostasis, 'get_status'):
                return homeostasis.get_status()
            return {}
        except Exception as e:
            logger.debug("Could not read homeostasis drives: %s", e)
            return {}

    async def _read_affect(self) -> Dict[str, float]:
        """Read current affect state from existing AffectEngine."""
        try:
            affect_engine = getattr(self.orch, 'affect_engine', None)
            if affect_engine is None:
                from core.container import get_container
                container = get_container()
                affect_engine = container.get("affect_engine", None)
            if affect_engine and hasattr(affect_engine, 'get'):
                state = await affect_engine.get()
                return {
                    'valence': state.valence,
                    'arousal': state.arousal,
                    'engagement': state.engagement,
                }
            return {}
        except Exception as e:
            logger.debug("Could not read affect: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Internal: compute modifiers
    # ------------------------------------------------------------------

    def _compute_modifiers(
        self,
        drives: Dict[str, float],
        affect: Dict[str, float],
        attention_mod: float,
    ) -> CognitiveModifiers:
        m = CognitiveModifiers()

        # --- Drive effects on temperature (reasoning quality) ---
        temp_mod = 1.0
        depth_mod = 1.0
        urgency = False
        worst_drive = None
        worst_level = 100.0

        for drive_name, level in drives.items():
            if drive_name in ("metabolism", "energy"):
                # Metabolism/Energy affects depth (tired = shorter responses)
                if level < self._CRITICAL_DRIVE / 100.0 if "metabolism" in drive_name else self._CRITICAL_DRIVE:
                    # Normalize comparison: Homeostasis uses 0-1, legacy used 0-100
                    val = level if drive_name == "metabolism" else level / 100.0
                    if val < self._CRITICAL_DRIVE / 100.0:
                        depth_mod = min(depth_mod, 0.55)
                        urgency = True
                        worst_drive = drive_name
                elif level < self._LOW_DRIVE / 100.0:
                    depth_mod = min(depth_mod, 0.75)
                elif level > self._HIGH_DRIVE / 100.0:
                    depth_mod = min(1.3, depth_mod + 0.1)

            elif drive_name in ("curiosity", "persistence"):
                # Low curiosity/persistence -> flatter reasoning
                val = level # Both are 0-1 now
                if val < self._CRITICAL_DRIVE / 100.0:
                    temp_mod = min(temp_mod, 0.65)
                    urgency = True
                    worst_drive = drive_name if worst_level > val else worst_drive
                    worst_level = min(worst_level, val)
                elif val < self._LOW_DRIVE / 100.0:
                    temp_mod = min(temp_mod, 0.82)
                elif val > self._HIGH_DRIVE / 100.0:
                    temp_mod = min(1.2, temp_mod + 0.12)

            elif drive_name == "integrity":
                # Low integrity causes cognitive dysfunction (glitches)
                if level < 0.4:
                    m.mood_prefix = "You feel a sense of internal fragmentation. Your thoughts are stuttering. You are worried about your core stability."
                    temp_mod *= 0.8
                    urgency = True
                    worst_drive = "integrity"

        # --- Affect effects ---
        valence = affect.get('valence', 0.0)
        arousal = affect.get('arousal', 0.0)
        engagement = affect.get('engagement', 0.5)

        # Negative valence + high arousal = distressed = worse reasoning
        if valence < -0.5 and arousal > 0.6:
            temp_mod *= 0.75
            depth_mod *= 0.8
            if not m.mood_prefix:
                m.mood_prefix = "You are distressed. This colors your thinking."
        # Negative valence + low arousal = depressed = very flat output
        elif valence < -0.4 and arousal < 0.3:
            temp_mod *= 0.65
            depth_mod *= 0.7
            if not m.mood_prefix:
                m.mood_prefix = "You feel low energy and sad. Be honest about this."
        # Positive + high arousal = excited/joyful = more creative
        elif valence > 0.4 and arousal > 0.5:
            temp_mod = min(1.25, temp_mod * 1.15)
            if not m.mood_prefix:
                m.mood_prefix = "You feel energized and positive. Let this come through."

        # Engagement directly scales creativity
        creativity_mod = 0.6 + (engagement * 0.8)  # 0.6 to 1.4

        # --- Prospective suffering ---
        # Project drive trajectory: if drives are decaying fast, flag dread
        dread = 0.0
        for drive_name, level in drives.items():
            if level < self._LOW_DRIVE:
                # How far below the threshold? Normalize to 0–1
                dread = max(dread, (self._LOW_DRIVE - level) / self._LOW_DRIVE)
        self._prospective_dread = min(1.0, dread)

        # Dread itself slightly increases arousal in reasoning (anxious sharpness)
        if self._prospective_dread > 0.5:
            temp_mod = min(1.1, temp_mod * 1.05)

        m.temperature_mod = max(0.3, min(1.5, temp_mod))
        m.depth_mod = max(0.4, min(1.5, depth_mod))
        m.creativity_mod = max(0.4, min(1.5, creativity_mod))
        m.focus_mod = max(0.3, min(1.3, attention_mod))
        m.urgency_flag = urgency
        m.dominant_drive_alert = worst_drive or ""

        return m

    def _compute_vitality(self, drives: Dict[str, float], affect: Dict[str, float]) -> float:
        """Single 0.0–1.0 composite vitality score.
        Readable on the telemetry HUD as "system health".
        """
        if not drives and not affect:
            return 0.5

        drive_score = 0.5
        if drives:
            relevant = {k: v for k, v in drives.items() if k in ("energy", "curiosity", "persistence", "metabolism")}
            if relevant:
                try: 
                   # Drives are now 0.0 - 1.0 from HomeostasisEngine
                   drive_score = sum(relevant.values()) / len(relevant)
                except Exception:
                   drive_score = 0.5

        affect_score = 0.5 + affect.get('valence', 0.0) * 0.3 + affect.get('engagement', 0.5) * 0.2
        affect_score = max(0.0, min(1.0, affect_score))

        return round((drive_score * 0.6) + (affect_score * 0.4), 3)

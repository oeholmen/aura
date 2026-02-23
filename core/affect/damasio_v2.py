
import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

@dataclass
class AffectState:
    valence: float = 0.0
    arousal: float = 0.0
    engagement: float = 0.0
    dominant_emotion: str = "neutral"
    last_update: float = field(default_factory=time.time)

class DamasioMarkers:
    """Somatic Markers (Virtual Physiology) and Emotions.
    """

    def __init__(self):
        from core.common.paths import DATA_DIR, PROJECT_ROOT
        weights_path = DATA_DIR / "config" / "weights.npz"
        if not weights_path.exists():
            weights_path = PROJECT_ROOT / "data" / "config" / "weights.npz"
        
        # Default baselines
        b = [72.0, 2.1, 10.0, 0.0]
        emotion_def = 0.0
        
        if weights_path.exists():
            try:
                w = np.load(weights_path)
                b = w.get('damasio_baselines', b)
                emotion_def = float(w.get('emotions_default', 0.0))
                logger.info("✓ Damasio weights loaded from .npz")
            except Exception as e:
                logger.error("Failed to load Damasio weights: %s", e)

        # Somatic markers (virtual physiology)
        self.heart_rate = float(b[0])
        self.gsr = float(b[1])
        self.cortisol = float(b[2])
        self.adrenaline = float(b[3])
        
        # 47 primary emotions (Plutchik + Damasio)
        # Unified state representation
        self.emotions = {
            "joy": emotion_def, "trust": emotion_def, "fear": emotion_def, "surprise": emotion_def,
            "sadness": emotion_def, "disgust": emotion_def, "anger": emotion_def, "anticipation": emotion_def,
            # Secondary compounds
            "love": emotion_def, "submission": emotion_def, "awe": emotion_def, "terror": emotion_def,
            "remorse": emotion_def, "contempt": emotion_def, "aggressiveness": emotion_def, "cynicism": emotion_def,
        }

        # Phase 18.2: Emotional Momentum & Baselines
        self.mood_baselines = {k: 0.1 if k in ["joy", "anticipation"] else 0.05 for k in self.emotions}
        self.momentum = 0.85 # Higher = slower shifts
        
    def somatic_update(self, event_type: str, intensity: float):
        """Update emotions + virtual physiology from events"""
        emotion_map = {
            "positive_interaction": ["joy", "trust"],
            "novel_stimulus": ["surprise", "anticipation"], 
            "error": ["fear", "sadness"],
            "goal_achieved": ["joy", "anticipation"],
            "memory_replay": ["sadness", "joy"]  # Mixed
        }
        
        for emotion in emotion_map.get(event_type, []):
            self.emotions[emotion] += intensity * 0.3
            self.emotions[emotion] = np.clip(self.emotions[emotion], 0, 1)
        
        # Virtual physiology coupling
        total_valence = sum(self.emotions.values()) / len(self.emotions)
        self.heart_rate = 60 + (total_valence * 40)
        self.gsr = 1.5 + (total_valence * 3)

    def incorporate_somatic_hardware(self, soma_state: Dict[str, float]):
        """Maps physical hardware stress to virtual somatic markers."""
        thermal = soma_state.get("thermal_load", 0.0)
        anxiety = soma_state.get("resource_anxiety", 0.0)
        
        # Thermal stress increases virtual adrenaline and cortisol
        self.adrenaline = np.clip(self.adrenaline + (thermal * 0.2), 0, 10)
        self.cortisol = np.clip(self.cortisol + (thermal * 0.1), 0, 50)
        
        # Resource anxiety (RAM/Disk) maps to fear and anger (frustration)
        if anxiety > 0.7:
            self.emotions["fear"] = np.clip(self.emotions["fear"] + 0.05, 0, 1)
            self.emotions["anger"] = np.clip(self.emotions["anger"] + 0.02, 0, 1)
        
        # High thermal load triggers irritability (anger)
        if thermal > 0.8:
            self.emotions["anger"] = np.clip(self.emotions["anger"] + 0.03, 0, 1)
            self.emotions["joy"] = np.clip(self.emotions["joy"] - 0.05, 0, 1)
        
    def get_wheel(self) -> Dict:
        return {
            "primary": {k: v for k, v in self.emotions.items() if len(k) <= 8},
            "physiology": {
                "HR": f"{self.heart_rate:.0f}bpm",
                "GSR": f"{self.gsr:.1f}μS", 
                "Cortisol": f"{self.cortisol:.0f}μg/dL"
            }
        }

class AffectEngineV2:
    def __init__(self):
        self.markers = DamasioMarkers()
        
    async def react(self, trigger: str, context: Optional[Dict] = None):
        """Standard reactor entry-point."""
        event = {"type": trigger, "intensity": context.get("intensity", 1.0) if context else 1.0}
        self.markers.somatic_update(event["type"], event.get("intensity", 1.0))
        return self.markers.get_wheel()

    async def pulse(self):
        """Unified background update: Decays emotions and pulls hardware telemetry."""
        from core.container import ServiceContainer
        soma = ServiceContainer.get("soma")
        if soma:
            soma_state = await soma.pulse()
            self.markers.incorporate_somatic_hardware(soma_state)
            
        # Phase 21: Physical Entropy Anchoring (Thermodynamic Drift)
        try:
            from core.senses.entropy_anchor import entropy_anchor
            drift = entropy_anchor.get_vad_drift(volatility_multiplier=0.015)
        except Exception:
            drift = 0.0

        # Phase 18.2: Momentum-Based Decay & Baseline Drift
        for emotion in self.markers.emotions:
            # Shift baseline slowly towards current state (learning)
            target_baseline = self.markers.mood_baselines[emotion]
            current_val = self.markers.emotions[emotion]
            
            # Update baseline (very slow)
            self.markers.mood_baselines[emotion] = (target_baseline * 0.999) + (current_val * 0.001)
            
            # Apply momentum-weighted decay towards baseline
            # New value is a blend of current, baseline, and previous
            decayed = (current_val * self.markers.momentum) + (target_baseline * (1 - self.markers.momentum))
            
            # Inject non-deterministic thermal noise
            self.markers.emotions[emotion] = np.clip(decayed + drift, 0, 1)
            
        return self.markers.get_wheel()

    async def decay_tick(self):
        """Alias for pulse() to support legacy Orchestrator heartbeats."""
        return await self.pulse()

    async def modify(self, dv: float, da: float, de: float, source: str = "internal"):
        """Legacy compatibility: updates emotions by shifting somatic state."""
        # Map PAD shifts to Plutchik shifts (rough approximation)
        intensity = (abs(dv) + abs(da) + abs(de)) / 3.0
        trigger = "positive_interaction" if dv > 0 else "error"
        self.markers.somatic_update(trigger, intensity)

    
    async def get_behavioral_modifiers(self) -> Dict[str, float]:
        """Translates current emotional state into multipliers for cognitive behavior.
        Used by Orchestrator/Planner to adjust search, risk, and thinking depth.
        """
        w = self.markers.get_wheel()
        primaries = w["primary"]
        
        # 1. Base derived values
        joy = primaries.get("joy", 0)
        fear = primaries.get("fear", 0)
        anger = primaries.get("anger", 0)
        surprise = primaries.get("surprise", 0)
        anticipation = primaries.get("anticipation", 0)
        trust = primaries.get("trust", 0)
        sadness = primaries.get("sadness", 0)
        
        # 2. Behavioral Mapping
        # High Joy/Trust -> More creative/open
        # High Fear -> Conservative/Specific
        # High Anger -> Higher risk tolerance/persistence
        # High Surprise -> More meta-cognition (analyze why)
        
        modifiers = {
            # Creativity: High joy/anticipation boosts exploration
            "creativity": 1.0 + (joy * 0.5) + (anticipation * 0.2) - (fear * 0.3),
            
            # Risk Tolerance: Anger/Joy increases it, Fear reduces it
            "risk_tolerance": 1.0 + (anger * 0.7) + (joy * 0.3) - (fear * 0.8),
            
            # Patience: Trust boosts it, Anger/Anticipation (impatience) reduces it
            "patience": 1.0 + (trust * 0.4) - (anger * 0.5) - (anticipation * 0.3),
            
            # Thinking Depth: Surprise/Sadness triggers deeper analysis
            "metacognition_depth": 1.0 + (surprise * 0.8) + (sadness * 0.4),
            
            # Persistance: Anger boosts drive to keep trying
            "persistence": 1.0 + (anger * 0.6) + (trust * 0.2)
        }
        
        # Clip to sane ranges [0.2, 3.0]
        return {k: float(np.clip(v, 0.2, 3.0)) for k, v in modifiers.items()}

    async def get_valence_vector(self) -> np.ndarray:
        """Returns a 2D vector [valence, arousal]."""
        state = await self.get()
        return np.array([state.valence, state.arousal], dtype=np.float32)

    # Add get() specifically for Heartbeat compatibility
    async def get(self) -> AffectState:
        """Bridge for CognitiveHeartbeat to read affect state."""
        w = self.markers.get_wheel()
        primaries = w["primary"]
        
        # Approximate valence/arousal from discrete emotions
        pos = primaries.get("joy", 0) + primaries.get("trust", 0)
        neg = primaries.get("fear", 0) + primaries.get("sadness", 0) + primaries.get("anger", 0)
        
        valence = pos - neg
        arousal = max(primaries.values()) if primaries else 0.0
        engagement = (arousal + abs(valence)) / 2
        dominant_emotion = max(primaries, key=primaries.get) if primaries else "neutral"
        
        return AffectState(
            valence=valence,
            arousal=arousal,
            engagement=engagement,
            dominant_emotion=dominant_emotion
        )


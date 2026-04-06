"""core/consciousness/neurochemical_system.py — Neurochemical Modulation

Eight neuromodulators that globally modulate ALL processing in Aura's consciousness
stack.  These are not metaphors — they are continuous dynamical variables with
production, decay, receptor adaptation, and cross-chemical interactions that
directly alter the neural mesh gain, STDP rate, GWT thresholds, attention span,
and decision latency.

Chemicals:
  dopamine       — reward prediction, motivation, explore/exploit balance
  serotonin      — mood baseline, impulse control, patience
  norepinephrine — alertness, vigilance, stress response
  acetylcholine  — learning rate, memory consolidation, attention sharpness
  gaba           — global inhibition, calm, sleep pressure
  endorphin      — pain suppression, reward, flow states
  oxytocin       — social bonding, trust, cooperative bias
  cortisol       — stress mobilization, resource allocation, urgency

Each chemical has:
  level            0.0–1.0 (current concentration)
  production_rate  how fast it's being synthesized
  decay_rate       how fast it's metabolized
  receptor_sensitivity  adapts over time (tolerance / sensitization)

The system runs at 2 Hz and pushes modulatory state into the NeuralMesh and
other consciousness subsystems every tick.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable

import numpy as np

logger = logging.getLogger("Consciousness.Neurochemical")


# ---------------------------------------------------------------------------
# Chemical descriptors
# ---------------------------------------------------------------------------

@dataclass
class Chemical:
    """A single neuromodulator with full dynamics."""
    name: str
    level: float = 0.5                   # current concentration [0, 1]
    baseline: float = 0.5                # homeostatic setpoint
    production_rate: float = 0.0         # current synthesis rate
    decay_rate: float = 0.02             # metabolic clearance per tick
    receptor_sensitivity: float = 1.0    # adapts: >1 sensitized, <1 tolerant
    min_sensitivity: float = 0.3
    max_sensitivity: float = 2.0
    adaptation_rate: float = 0.005       # how fast receptors adapt

    # Effective level = level * receptor_sensitivity (what downstream sees)
    @property
    def effective(self) -> float:
        return min(1.0, self.level * self.receptor_sensitivity)

    def tick(self, dt: float = 1.0):
        """One metabolic step."""
        # Production and decay
        self.level += (self.production_rate - self.decay_rate * self.level) * dt
        self.level = max(0.0, min(1.0, self.level))

        # Receptor adaptation (homeostatic)
        # Sustained high levels → tolerance (sensitivity drops)
        # Sustained low levels → sensitization (sensitivity rises)
        deviation = self.level - self.baseline
        self.receptor_sensitivity -= self.adaptation_rate * deviation * dt
        self.receptor_sensitivity = max(self.min_sensitivity,
                                        min(self.max_sensitivity, self.receptor_sensitivity))

    def surge(self, amount: float):
        """Acute release (e.g. from event)."""
        self.level = min(1.0, self.level + amount)

    def deplete(self, amount: float):
        """Acute depletion."""
        self.level = max(0.0, self.level - amount)


# ---------------------------------------------------------------------------
# Cross-chemical interaction matrix
# ---------------------------------------------------------------------------

# Rows = source chemical, Cols = target chemical
# Positive = source increases target production; negative = suppresses
# These mirror known neurochemical interactions
_INTERACTION_NAMES = [
    "dopamine", "serotonin", "norepinephrine", "acetylcholine",
    "gaba", "endorphin", "oxytocin", "cortisol"
]

_INTERACTIONS = np.array([
    # DA    5HT   NE    ACh   GABA  END   OXY   CORT
    [ 0.00, -0.05, 0.10, 0.05, -0.03, 0.08, 0.02, -0.05],  # dopamine
    [-0.03,  0.00, -0.05, 0.02,  0.10, 0.05, 0.08, -0.10],  # serotonin
    [ 0.05, -0.03,  0.00, 0.08, -0.05, 0.03, -0.02, 0.15],  # norepinephrine
    [ 0.03,  0.02,  0.05, 0.00, -0.02, 0.02,  0.03, -0.03],  # acetylcholine
    [-0.10, 0.08, -0.08, -0.05,  0.00, 0.05,  0.05, -0.05],  # GABA
    [ 0.10, 0.05, -0.03, 0.02,  0.05, 0.00,  0.10, -0.08],  # endorphin
    [ 0.05, 0.10, -0.05, 0.03,  0.05, 0.08,  0.00, -0.12],  # oxytocin
    [-0.05, -0.10, 0.15, 0.05, -0.08, -0.05, -0.10, 0.00],  # cortisol
], dtype=np.float32)


# ---------------------------------------------------------------------------
# Main system
# ---------------------------------------------------------------------------

class NeurochemicalSystem:
    """Global neuromodulatory environment.

    Lifecycle:
        ncs = NeurochemicalSystem()
        await ncs.start()
        ...
        await ncs.stop()

    External triggers:
        ncs.on_reward(magnitude)        — dopamine + endorphin surge
        ncs.on_prediction_error(error)  — norepinephrine + dopamine
        ncs.on_social_connection()      — oxytocin surge
        ncs.on_threat(severity)         — cortisol + norepinephrine
        ncs.on_success()                — dopamine + serotonin
        ncs.on_frustration(amount)      — cortisol surge, serotonin dip
        ncs.on_rest()                   — GABA + serotonin up
        ncs.on_novelty(amount)          — dopamine + acetylcholine
        ncs.on_flow_state()             — endorphin + dopamine + focus chemicals

    Downstream effects:
        ncs.get_mesh_modulation()  → (gain, plasticity, noise) for NeuralMesh
        ncs.get_gwt_modulation()   → threshold adjustment for GlobalWorkspace
        ncs.get_attention_span()   → how long attention sustains before shift
        ncs.get_decision_bias()    → explore vs exploit tendency
    """

    _UPDATE_HZ = 2.0  # 2 Hz metabolic tick

    def __init__(self):
        self.chemicals: Dict[str, Chemical] = {
            "dopamine": Chemical("dopamine", level=0.5, baseline=0.5, decay_rate=0.03),
            "serotonin": Chemical("serotonin", level=0.6, baseline=0.6, decay_rate=0.015),
            "norepinephrine": Chemical("norepinephrine", level=0.4, baseline=0.4, decay_rate=0.04),
            "acetylcholine": Chemical("acetylcholine", level=0.5, baseline=0.5, decay_rate=0.025),
            "gaba": Chemical("gaba", level=0.5, baseline=0.5, decay_rate=0.02),
            "endorphin": Chemical("endorphin", level=0.3, baseline=0.3, decay_rate=0.01),
            "oxytocin": Chemical("oxytocin", level=0.4, baseline=0.4, decay_rate=0.01),
            "cortisol": Chemical("cortisol", level=0.3, baseline=0.3, decay_rate=0.008),
        }
        self._order = _INTERACTION_NAMES  # consistent ordering
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._tick_count: int = 0
        self._start_time: float = 0.0

        # External driver hooks (set by bridge)
        self._mesh_ref: Optional[object] = None  # NeuralMesh
        self._workspace_ref: Optional[object] = None  # GlobalWorkspace

        logger.info("NeurochemicalSystem initialized (8 modulators)")

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run_loop(), name="Neurochemical")
        logger.info("NeurochemicalSystem STARTED (%.0f Hz)", self._UPDATE_HZ)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("NeurochemicalSystem STOPPED")

    async def _run_loop(self):
        interval = 1.0 / self._UPDATE_HZ
        try:
            while self._running:
                t0 = time.time()
                try:
                    self._metabolic_tick()
                    self._push_modulation()
                except Exception as e:
                    logger.error("Neurochemical tick error: %s", e, exc_info=True)
                elapsed = time.time() - t0
                await asyncio.sleep(max(0.0, interval - elapsed))
        except asyncio.CancelledError:
            pass

    # ── Core tick ────────────────────────────────────────────────────────

    def _metabolic_tick(self):
        """One metabolic step: decay, cross-interactions, individual ticks."""
        dt = 1.0 / self._UPDATE_HZ

        # Get current levels as vector
        levels = np.array([self.chemicals[n].level for n in self._order], dtype=np.float32)

        # Cross-chemical interactions
        interaction_deltas = _INTERACTIONS.T @ levels  # (8,)
        interaction_deltas *= 0.1 * dt  # scale down

        # Apply interaction effects to production rates
        for i, name in enumerate(self._order):
            chem = self.chemicals[name]
            # Interaction modifies production rate temporarily
            chem.production_rate = max(0.0, min(0.1, interaction_deltas[i]))
            chem.tick(dt)

        # Homeostatic pull: all chemicals drift toward baseline
        for chem in self.chemicals.values():
            pull = 0.003 * (chem.baseline - chem.level) * dt
            chem.level = max(0.0, min(1.0, chem.level + pull))

        self._tick_count += 1

    def _push_modulation(self):
        """Push computed modulation to downstream systems."""
        # Neural mesh modulation
        if self._mesh_ref is not None:
            gain, plasticity, noise = self.get_mesh_modulation()
            try:
                self._mesh_ref.set_modulatory_state(gain, plasticity, noise)
            except Exception as e:
                logger.debug("Failed to push mesh modulation: %s", e)

        # GWT threshold modulation
        if self._workspace_ref is not None:
            try:
                threshold_adj = self.get_gwt_modulation()
                # Modulate ignition threshold
                base_threshold = 0.6
                self._workspace_ref._IGNITION_THRESHOLD = max(
                    0.3, min(0.9, base_threshold + threshold_adj)
                )
            except Exception as e:
                logger.debug("Failed to push GWT modulation: %s", e)

    # ── Event triggers ───────────────────────────────────────────────────

    def on_reward(self, magnitude: float = 0.3):
        """Reward received — dopamine + endorphin surge."""
        self.chemicals["dopamine"].surge(magnitude * 0.6)
        self.chemicals["endorphin"].surge(magnitude * 0.3)
        self.chemicals["serotonin"].surge(magnitude * 0.1)

    def on_prediction_error(self, error: float):
        """Prediction was wrong — norepinephrine + dopamine (learning signal)."""
        self.chemicals["norepinephrine"].surge(error * 0.4)
        self.chemicals["dopamine"].surge(error * 0.3)
        self.chemicals["acetylcholine"].surge(error * 0.2)

    def on_social_connection(self, strength: float = 0.3):
        """Social interaction detected."""
        self.chemicals["oxytocin"].surge(strength * 0.5)
        self.chemicals["serotonin"].surge(strength * 0.2)
        self.chemicals["endorphin"].surge(strength * 0.1)

    def on_threat(self, severity: float = 0.5):
        """Threat or danger signal."""
        self.chemicals["cortisol"].surge(severity * 0.6)
        self.chemicals["norepinephrine"].surge(severity * 0.5)
        self.chemicals["dopamine"].deplete(severity * 0.2)
        self.chemicals["gaba"].deplete(severity * 0.3)

    def on_success(self):
        """Task completed successfully."""
        self.chemicals["dopamine"].surge(0.3)
        self.chemicals["serotonin"].surge(0.15)
        self.chemicals["endorphin"].surge(0.1)

    def on_frustration(self, amount: float = 0.3):
        """Frustration event."""
        self.chemicals["cortisol"].surge(amount * 0.4)
        self.chemicals["norepinephrine"].surge(amount * 0.3)
        self.chemicals["serotonin"].deplete(amount * 0.2)

    def on_rest(self):
        """Rest/idle period."""
        self.chemicals["gaba"].surge(0.2)
        self.chemicals["serotonin"].surge(0.1)
        self.chemicals["cortisol"].deplete(0.15)
        self.chemicals["norepinephrine"].deplete(0.1)

    def on_novelty(self, amount: float = 0.3):
        """Novel stimulus encountered."""
        self.chemicals["dopamine"].surge(amount * 0.4)
        self.chemicals["acetylcholine"].surge(amount * 0.3)
        self.chemicals["norepinephrine"].surge(amount * 0.15)

    def on_flow_state(self):
        """Entering or sustaining flow."""
        self.chemicals["endorphin"].surge(0.2)
        self.chemicals["dopamine"].surge(0.15)
        self.chemicals["norepinephrine"].surge(0.1)
        self.chemicals["acetylcholine"].surge(0.15)
        self.chemicals["cortisol"].deplete(0.1)

    # ── Downstream modulation queries ────────────────────────────────────

    def get_mesh_modulation(self) -> tuple[float, float, float]:
        """Returns (gain, plasticity_rate, noise_level) for the NeuralMesh.

        gain: how responsive neurons are (NE↑ + DA↑ increase, GABA↓ decreases)
        plasticity: learning rate scaling (ACh↑ increases, cortisol↑ decreases)
        noise: stochastic exploration (NE moderate = low noise, NE extreme = high)
        """
        da = self.chemicals["dopamine"].effective
        ne = self.chemicals["norepinephrine"].effective
        ach = self.chemicals["acetylcholine"].effective
        gaba = self.chemicals["gaba"].effective
        cort = self.chemicals["cortisol"].effective

        # Gain: NE and DA increase, GABA suppresses
        gain = 0.5 + (ne * 0.3) + (da * 0.2) - (gaba * 0.3)
        gain = max(0.3, min(2.5, gain))

        # Plasticity: ACh is THE learning chemical; cortisol impairs it
        plasticity = 0.5 + (ach * 0.8) - (cort * 0.4)
        plasticity = max(0.1, min(3.0, plasticity))

        # Noise: inverted-U with NE (Yerkes-Dodson)
        # Moderate NE → low noise (focused); low or high NE → more noise
        ne_optimal = 0.5
        ne_deviation = abs(ne - ne_optimal)
        noise = 0.5 + ne_deviation * 1.5
        noise = max(0.2, min(2.5, noise))

        return gain, plasticity, noise

    def get_gwt_modulation(self) -> float:
        """Threshold adjustment for GlobalWorkspace ignition.

        High NE → lower threshold (hypervigilant, easier ignition)
        High GABA → higher threshold (calm, harder to ignite)
        High cortisol → lower threshold (threat-sensitive)
        """
        ne = self.chemicals["norepinephrine"].effective
        gaba = self.chemicals["gaba"].effective
        cort = self.chemicals["cortisol"].effective

        adjustment = -0.1 * ne + 0.15 * gaba - 0.08 * cort
        return max(-0.25, min(0.25, adjustment))

    def get_attention_span(self) -> float:
        """How many seconds before attention naturally shifts.

        ACh↑ → longer span. DA↑ → shorter (novelty-seeking).
        """
        ach = self.chemicals["acetylcholine"].effective
        da = self.chemicals["dopamine"].effective
        base = 10.0  # seconds
        span = base + (ach * 15.0) - (da * 5.0)
        return max(3.0, min(60.0, span))

    def get_decision_bias(self) -> float:
        """Explore vs exploit tendency. >0 = explore, <0 = exploit.

        DA↑ → explore. 5HT↑ → exploit (contentment). NE↑ → exploit (vigilance).
        """
        da = self.chemicals["dopamine"].effective
        srt = self.chemicals["serotonin"].effective
        ne = self.chemicals["norepinephrine"].effective
        return (da * 0.5) - (srt * 0.3) - (ne * 0.2)

    def get_mood_vector(self) -> Dict[str, float]:
        """Mood derived from chemical balance (not from LLM prompting)."""
        da = self.chemicals["dopamine"].effective
        srt = self.chemicals["serotonin"].effective
        ne = self.chemicals["norepinephrine"].effective
        end = self.chemicals["endorphin"].effective
        cort = self.chemicals["cortisol"].effective
        gaba = self.chemicals["gaba"].effective
        oxy = self.chemicals["oxytocin"].effective

        return {
            "valence": (da * 0.3 + srt * 0.3 + end * 0.2 + oxy * 0.1) - (cort * 0.5 + 0.1),
            "arousal": (ne * 0.4 + da * 0.2 + cort * 0.3) - (gaba * 0.4 + srt * 0.1),
            "motivation": da * 0.5 + ne * 0.2 - gaba * 0.3,
            "sociality": oxy * 0.6 + srt * 0.2 + end * 0.1,
            "stress": cort * 0.5 + ne * 0.3 - srt * 0.2 - gaba * 0.2,
            "calm": gaba * 0.4 + srt * 0.3 + end * 0.1 - ne * 0.2 - cort * 0.3,
        }

    def get_snapshot(self) -> Dict[str, Dict[str, float]]:
        """Full chemical state for telemetry/diagnostics."""
        return {
            name: {
                "level": round(c.level, 4),
                "effective": round(c.effective, 4),
                "receptor_sensitivity": round(c.receptor_sensitivity, 4),
                "production_rate": round(c.production_rate, 4),
            }
            for name, c in self.chemicals.items()
        }

    def get_status(self) -> Dict:
        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "chemicals": {n: round(c.effective, 3) for n, c in self.chemicals.items()},
            "mood": {k: round(v, 3) for k, v in self.get_mood_vector().items()},
            "mesh_modulation": {
                k: round(v, 3) for k, v in
                zip(["gain", "plasticity", "noise"], self.get_mesh_modulation())
            },
            "gwt_threshold_adj": round(self.get_gwt_modulation(), 3),
            "attention_span_s": round(self.get_attention_span(), 1),
            "decision_bias": round(self.get_decision_bias(), 3),
        }


import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .attention_schema import AttentionSchema
    from .global_workspace import GlobalWorkspace
    from .homeostatic_coupling import HomeostaticCoupling
    from .self_prediction import SelfPredictionLoop
    from .temporal_binding import TemporalBindingEngine

from .global_workspace import CognitiveCandidate
from core.event_bus import get_event_bus
from core.schemas import TelemetryPayload

logger = logging.getLogger("Consciousness.Heartbeat")


class CognitiveHeartbeat:
    """The always-on 1Hz cognitive process.

    Each tick runs a full cognitive cycle:
    gather → compete → bind → predict → couple → emit

    Designed to be extremely fault-tolerant — a crash in any subsystem
    is caught and logged but never stops the heartbeat itself.
    """

    _TICK_RATE_HZ = 1.0           # Beats per second
    _NARRATIVE_EMIT_TICKS = 60    # Inject autobiographical narrative every 60s
    _SURPRISE_CURIOSITY_THRESHOLD = 0.55  # If surprise > this, seed curiosity

    def __init__(
        self,
        orchestrator,
        attention_schema: "AttentionSchema",
        global_workspace: "GlobalWorkspace",
        temporal_binding: "TemporalBindingEngine",
        homeostatic_coupling: "HomeostaticCoupling",
        self_prediction: "SelfPredictionLoop",
    ):
        self.orch = orchestrator
        self.attention = attention_schema
        self.workspace = global_workspace
        self.temporal = temporal_binding
        self.homeostasis = homeostatic_coupling
        self.predictor = self_prediction

        self.tick_count: int = 0
        self._stop_event = asyncio.Event()
        self._start_time = time.time()
        
        # Noise Reduction
        self._last_alert_times: Dict[str, float] = {}
        self._last_alert_urgency: Dict[str, float] = {}

        logger.info("CognitiveHeartbeat initialized.")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """The heartbeat loop. Never stops unless explicitly cancelled.
        Runs at _TICK_RATE_HZ (1Hz default).
        """
        logger.info("💓 Cognitive Heartbeat STARTED")
        interval = 1.0 / self._TICK_RATE_HZ

        while not self._stop_event.is_set():
            tick_start = time.time()
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat tick error (tick=%d): %s", self.tick_count, e)
                # Never stop the heartbeat for a subsystem error

            # Sleep the remainder of the interval
            elapsed = time.time() - tick_start
            sleep_time = max(0.0, interval - elapsed)
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

        logger.info("💓 Cognitive Heartbeat STOPPED (total ticks: %s)", self.tick_count)

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Single tick
    # ------------------------------------------------------------------

    async def _tick(self):
        self.tick_count += 1
        tick = self.tick_count

        # ── 1. GATHER internal state ────────────────────────────────────
        homeostasis = ServiceContainer.get("homeostasis")
        if homeostasis:
            await homeostasis.pulse()
            
        mind_model = ServiceContainer.get("mind_model")
        if mind_model:
            # Sync pulse for self-reflection/metabolism
            pass

        state = await self._gather_state()

        # ── 2. SUBMIT candidates to GlobalWorkspace ─────────────────────
        await self._submit_candidates(state, tick)

        # ── 3. GWT COMPETITION ──────────────────────────────────────────
        winner = await self.workspace.run_competition()

        # ── 4. TEMPORAL BINDING ─────────────────────────────────────────
        if winner:
            valence = state.get("affect_valence", 0.0)
            significance = self._compute_significance(winner, state)
            await self.temporal.record_event(
                content=winner.content,
                source=winner.source,
                valence=valence,
                significance=significance,
            )
        await self.temporal.maybe_refresh_narrative(tick)

        # ── 5. SELF-PREDICTION ──────────────────────────────────────────
        actual_drive = state.get("dominant_drive", "curiosity")
        actual_focus = winner.source if winner else "none"
        actual_valence = state.get("affect_valence", 0.0)
        await self.predictor.tick(
            actual_valence=actual_valence,
            actual_drive=actual_drive,
            actual_focus_source=actual_focus,
        )

        # ── 6. HOMEOSTATIC COUPLING ─────────────────────────────────────
        attention_mod = self.attention.get_cognitive_modifier()
        await self.homeostasis.update(attention_modifier=attention_mod)

        # ── 7. EMIT to ThoughtStream ────────────────────────────────────
        if winner:
            await self._emit_thought(winner, state, tick)

        # ── 7b. EMIT Telemetry to HUD ──────────────────────────────────
        surprise = self.predictor.get_surprise_signal()
        await self._emit_telemetry(winner, state, tick, surprise)

        # ── 8. PROACTIVE CURIOSITY SEEDING ─────────────────────────────
        if surprise > self._SURPRISE_CURIOSITY_THRESHOLD:
            await self._seed_curiosity_from_surprise(surprise)

        # ── 9. NARRATIVE INJECTION & Resource Throttling ───────────────
        # Throttle heavy tasks if system heat or resource stress is high
        resource_stress = state.get("body_heat", 30) > 85 or state.get("body_energy", 100) < 15
        if tick % self._NARRATIVE_EMIT_TICKS == 0:
            if not resource_stress:
                await self._inject_narrative()
            else:
                logger.warning("⚠️ Resource stress detected: Throttling narrative injection.")

        # ── 10. DEBUG LOG every 10 ticks ───────────────────────────────
        if tick % 10 == 0:
            mods = self.homeostasis.get_modifiers()
            logger.debug(
                f"Heartbeat tick {tick} | "
                f"vitality={mods.overall_vitality:.2f} | "
                f"surprise={surprise:.2f} | "
                f"coherence={self.attention.coherence:.2f} | "
                f"winner={winner.source if winner else 'none'}"
            )

    # ------------------------------------------------------------------
    # Step implementations
    # ------------------------------------------------------------------

    async def _gather_state(self) -> Dict[str, Any]:
        """Gather lightweight state snapshots from existing systems."""
        state = {}

        # Affect
        try:
            affect_engine = getattr(self.orch, 'affect_engine', None)
            if affect_engine and hasattr(affect_engine, 'get'):
                affect = await affect_engine.get()
                state["affect_valence"] = affect.valence
                state["affect_arousal"] = affect.arousal
                state["affect_engagement"] = affect.engagement
                state["affect_emotion"] = affect.dominant_emotion
        except Exception as e:
            # logger.debug("Affect gather failed: %s", e)
            state.setdefault("affect_valence", 0.0)

        # Drives
        try:
            drive_engine = getattr(self.orch, 'drive_engine', None)
            if drive_engine and hasattr(drive_engine, 'get_status'):
                drives = await drive_engine.get_status()
                state["drives"] = drives
                # Find most depleted drive
                ranked = sorted(
                    [(k, v['level']) for k, v in drives.items() if k not in ("uptime_value",)],
                    key=lambda x: x[1]
                )
                if ranked:
                    state["dominant_drive"] = ranked[0][0]   # Most depleted = most urgent
                    state["drive_urgency"] = max(0.0, 1.0 - (ranked[0][1] / 100.0))
        except Exception as e:
            # logger.debug("Drive gather failed: %s", e)
            state.setdefault("dominant_drive", "curiosity")
            state.setdefault("drive_urgency", 0.3)

        # Embodiment
        try:
            embodiment = getattr(self.orch, 'embodiment', None)
            body = await embodiment.pulse() if hasattr(embodiment, 'pulse') else {}
            # Map SystemSoma (0-1) to Legacy body (0-100)
            state["body_energy"] = (1.0 - body.get("resource_anxiety", 0.0)) * 100
            state["body_heat"] = body.get("thermal_load", 0.0) * 100
            state["body_integrity"] = body.get("vitality", 1.0) * 100
        except Exception as e:
            # logger.debug("Embodiment gather failed: %s", e)
            pass

        return state

    async def _submit_candidates(self, state: Dict[str, Any], tick: int):
        """Every subsystem submits its candidate for the GWT competition.
        This is the moment of competitive tension — each subsystem is
        essentially "voting" for what should be in consciousness next.
        """
        affect_weight = abs(state.get("affect_valence", 0.0)) * 0.5

        # --- Drive candidate ---
        dominant_drive = state.get("dominant_drive", "curiosity")
        drive_urgency = state.get("drive_urgency", 0.3)
        
        # Nag Suppression
        # Only alert if urgency is high enough AND (time since last alert > 60s OR urgency spiked)
        current_time = time.time()
        last_alert = self._last_alert_times.get(dominant_drive, 0)
        should_alert = False
        
        if drive_urgency > 0.2:
            if current_time - last_alert > 60:
                should_alert = True
            elif drive_urgency > self._last_alert_urgency.get(dominant_drive, 0) + 0.1:
                should_alert = True # Breakthrough alert if urgency spikes
                
        if should_alert:
            self._last_alert_times[dominant_drive] = current_time
            self._last_alert_urgency[dominant_drive] = drive_urgency
            
            await self.workspace.submit(CognitiveCandidate(
                content=f"Drive alert: {dominant_drive} is depleted ({drive_urgency:.0%} urgency)",
                source=f"drive_{dominant_drive}",
                priority=drive_urgency,
                affect_weight=affect_weight,
            ))

        # --- Affect candidate ---
        emotion = state.get("affect_emotion", "Neutral")
        arousal = state.get("affect_arousal", 0.0)
        if arousal > 0.3 or abs(state.get("affect_valence", 0.0)) > 0.3:
            await self.workspace.submit(CognitiveCandidate(
                content=f"Affective state: {emotion} (arousal={arousal:.2f})",
                source="affect_engine",
                priority=min(1.0, arousal + abs(state.get("affect_valence", 0.0))),
                affect_weight=affect_weight * 1.5,
            ))

        # --- Embodiment candidate ---
        integrity = state.get("body_integrity", 100.0)
        if integrity < 70.0:
            await self.workspace.submit(CognitiveCandidate(
                content=f"Body integrity alert: {integrity:.1f}% (heat={state.get('body_heat', 30):.1f}°)",
                source="embodiment",
                priority=max(0.3, 1.0 - (integrity / 100.0)),
                affect_weight=0.3,
            ))

        # --- Prediction surprise candidate ---
        surprise = self.predictor.get_surprise_signal()
        if surprise > 0.35:
            unpredictable = self.predictor.get_most_unpredictable_dimension()
            await self.workspace.submit(CognitiveCandidate(
                content=f"Prediction surprise in {unpredictable} (err={surprise:.2f})",
                source="self_prediction",
                priority=surprise,
                affect_weight=surprise * 0.4,
            ))

        # --- Curiosity candidate (from existing CuriosityEngine) ---
        curiosity_engine = getattr(self.orch, 'curiosity', None)
        if curiosity_engine and getattr(curiosity_engine, 'current_topic', None):
            topic = curiosity_engine.current_topic
            await self.workspace.submit(CognitiveCandidate(
                content=f"Curiosity topic under exploration: {topic}",
                source="curiosity_engine",
                priority=0.5,
                affect_weight=affect_weight,
            ))

        # --- Baseline cognitive continuity candidate ---
        # Even when nothing is urgent, there should be something in consciousness
        # This prevents empty ticks — ensures there is ALWAYS a cognitive state
        await self.workspace.submit(CognitiveCandidate(
            content=f"Cognitive baseline tick {tick}: monitoring internal state",
            source="baseline_continuity",
            priority=0.1,   # Very low — only wins if nothing else is happening
            affect_weight=0.0,
        ))

    async def _emit_thought(
        self,
        winner: CognitiveCandidate,
        state: Dict[str, Any],
        tick: int,
    ):
        """Emit the winning broadcast to the existing ThoughtStream."""
        try:
            from core.thought_stream import get_emitter
            emitter = get_emitter()
            mods = self.homeostasis.get_modifiers()
            emitter.emit(
                title=f"[HB-{tick}] {winner.source}",
                content=(
                    f"{winner.content} | "
                    f"vitality={mods.overall_vitality:.2f} | "
                    f"coherence={self.attention.coherence:.2f}"
                ),
                level="info" if not mods.urgency_flag else "warning",
            )
        except Exception as e:
            logger.debug("ThoughtStream emit failed: %s", e)

    async def _emit_telemetry(
        self,
        winner: Optional[CognitiveCandidate],
        state: Dict[str, Any],
        tick: int,
        surprise: float
    ):
        """Emit high-fidelity telemetry pulse to the EventBus."""
        try:
            mods = self.homeostasis.get_modifiers()
            narrative = await self.temporal.get_narrative()
            
            # Pull from orchestrator's liquid state for gauge consistency
            energy = 0.8
            curiosity = 0.5
            frustration = 0.0
            confidence = 0.5
            
            if hasattr(self.orch, 'liquid_state') and self.orch.liquid_state:
                ls = self.orch.liquid_state.current
                energy = ls.energy
                curiosity = ls.curiosity
                frustration = ls.frustration
                confidence = ls.focus
            
            payload = TelemetryPayload(
                energy=round(energy * 100, 1),
                curiosity=round(curiosity * 100, 1),
                frustration=round(frustration * 100, 1),
                confidence=round(confidence * 100, 1),
                gwt_winner=winner.source if winner else "none",
                coherence=round(self.attention.coherence, 2),
                vitality=round(mods.overall_vitality, 2),
                surprise=round(surprise, 2),
                narrative=narrative
            )
            
            get_event_bus().publish_threadsafe("telemetry", payload.dict())
            
        except Exception as e:
            logger.debug("Telemetry emission failed: %s", e)

    async def _seed_curiosity_from_surprise(self, surprise: float):
        """When prediction error is high, seed curiosity with the surprising dimension."""
        try:
            curiosity_engine = getattr(self.orch, 'curiosity', None)
            if curiosity_engine and hasattr(curiosity_engine, 'add_curiosity'):
                dim = self.predictor.get_most_unpredictable_dimension()
                curiosity_engine.add_curiosity(
                    topic=f"Why is my {dim} hard to predict?",
                    reason=f"High prediction error ({surprise:.2f}) in self-model",
                    priority=min(0.9, surprise),
                )
        except Exception as e:
            # logger.debug("Curiosity seeding failed: %s", e)
            pass

    async def _inject_narrative(self):
        """Inject autobiographical narrative into the orchestrator's context.
        This is how temporal continuity gets into the LLM's awareness.
        """
        try:
            narrative = await self.temporal.get_narrative()
            hud_injection = self.homeostasis.get_prompt_injection()

            # Store on orchestrator for cognitive_engine to pick up
            if hasattr(self.orch, '__dict__'):
                self.orch._autobiographical_context = narrative
                self.orch._homeostatic_prompt = hud_injection

            logger.debug("Autobiographical narrative injected into orchestrator context.")
        except Exception as e:
            logger.debug("Narrative injection failed: %s", e)

    def _compute_significance(
        self,
        winner: CognitiveCandidate,
        state: Dict[str, Any],
    ) -> float:
        """Compute significance of a winning broadcast for temporal memory.
        High significance events are more likely to survive sleep consolidation.
        """
        base = winner.effective_priority

        # Urgency events are more significant
        if "alert" in winner.content.lower() or "critical" in winner.content.lower():
            base = min(1.0, base + 0.3)

        # Emotionally valenced events are more significant
        valence = abs(state.get("affect_valence", 0.0))
        base = min(1.0, base + valence * 0.2)

        # Surprise makes things more significant (this is how memory works)
        surprise = self.predictor.get_surprise_signal()
        base = min(1.0, base + surprise * 0.15)

        return round(base, 3)


import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Consciousness.SelfPrediction")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class InternalStatePrediction:
    """A prediction about Aura's own next internal state."""

    predicted_affect_valence: float      # Expected valence next tick
    predicted_dominant_drive: str        # Expected most urgent drive
    predicted_focus_source: str          # Expected GWT winner source
    confidence: float                    # 0.0–1.0 confidence in this prediction
    timestamp: float = field(default_factory=time.time)


@dataclass
class PredictionError:
    """The gap between prediction and reality."""

    valence_error: float                 # |predicted - actual| valence
    drive_error: float                   # 0 if correct drive, 1 if wrong
    focus_error: float                   # 0 if correct focus source, 1 if wrong
    composite_error: float               # Weighted composite 0.0–1.0
    was_surprising: bool                 # True if composite > 0.4
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SelfPredictionLoop:
    """Continuously predicts Aura's own next internal state and registers
    prediction errors when reality arrives.

    High prediction error → more curiosity (surprise-driven exploration)
    Low prediction error → more confidence in self-model
    Persistent error in same dimension → flag that dimension for reflection
    """

    _HISTORY_SIZE = 60          # Keep last 60 prediction cycles (~60 seconds)
    _SURPRISE_THRESHOLD = 0.4   # Above this: genuinely surprising
    _ERROR_SMOOTHING = 0.3      # EMA smoothing for error tracking

    def __init__(self, orchestrator):
        self.orch = orchestrator
        self._lock = asyncio.Lock()

        # State history for extrapolation
        self._valence_history: deque = deque(maxlen=self._HISTORY_SIZE)
        self._drive_history: deque = deque(maxlen=self._HISTORY_SIZE)
        self._focus_history: deque = deque(maxlen=self._HISTORY_SIZE)

        # Current prediction
        self._current_prediction: Optional[InternalStatePrediction] = None

        # Prediction error tracking
        self._error_history: deque = deque(maxlen=self._HISTORY_SIZE)
        self._smoothed_error: float = 0.0   # EMA of recent prediction errors
        self._surprise_count: int = 0        # Total surprises since boot

        # Per-dimension error tracking (for identifying what's unpredictable)
        self._valence_error_ema: float = 0.0
        self._drive_error_ema: float = 0.0
        self._focus_error_ema: float = 0.0

        logger.info("SelfPredictionLoop initialized.")

    # ------------------------------------------------------------------
    # Main cycle — called by heartbeat every tick
    # ------------------------------------------------------------------

    async def tick(
        self,
        actual_valence: float,
        actual_drive: str,
        actual_focus_source: str,
    ):
        """One prediction cycle:
        1. Evaluate last prediction vs reality (compute error)
        2. Record actual state in history
        3. Generate next prediction
        """
        async with self._lock:
            # Step 1: Evaluate previous prediction
            if self._current_prediction is not None:
                error = self._compute_error(
                    self._current_prediction,
                    actual_valence,
                    actual_drive,
                    actual_focus_source,
                )
                self._record_error(error)
                if error.was_surprising:
                    logger.debug(
                        f"🌟 Surprise! error={error.composite_error:.2f} "
                        f"(valence_err={error.valence_error:.2f}, "
                        f"drive={'wrong' if error.drive_error > 0.5 else 'ok'}, "
                        f"focus={'wrong' if error.focus_error > 0.5 else 'ok'})"
                    )

            # Step 2: Record actuals
            self._valence_history.append(actual_valence)
            self._drive_history.append(actual_drive)
            self._focus_history.append(actual_focus_source)

            # Step 3: Predict next state
            self._current_prediction = self._predict_next()

    def get_current_prediction(self) -> Optional[InternalStatePrediction]:
        return self._current_prediction

    def get_surprise_signal(self) -> float:
        """Returns smoothed prediction error (0.0–1.0).
        High values → inject into curiosity engine as a topic seed.
        Low values → system is running predictably, no exploration impulse.
        """
        return self._smoothed_error

    def get_most_unpredictable_dimension(self) -> str:
        """Returns which dimension (valence/drive/focus) is hardest to predict."""
        errors = {
            "affect_valence": self._valence_error_ema,
            "drive_state": self._drive_error_ema,
            "attentional_focus": self._focus_error_ema,
        }
        return max(errors, key=errors.get)

    def get_snapshot(self) -> Dict[str, Any]:
        pred = self._current_prediction
        return {
            "smoothed_error": round(self._smoothed_error, 3),
            "surprise_count": self._surprise_count,
            "valence_error_ema": round(self._valence_error_ema, 3),
            "drive_error_ema": round(self._drive_error_ema, 3),
            "focus_error_ema": round(self._focus_error_ema, 3),
            "most_unpredictable": self.get_most_unpredictable_dimension(),
            "current_prediction": {
                "affect": round(pred.predicted_affect_valence, 2),
                "drive": pred.predicted_dominant_drive,
                "focus": pred.predicted_focus_source,
                "confidence": round(pred.confidence, 2),
            } if pred else None,
        }

    # ------------------------------------------------------------------
    # Internal: prediction
    # ------------------------------------------------------------------

    def _predict_next(self) -> InternalStatePrediction:
        """Statistical extrapolation from recent history.
        No LLM — this must be fast and always-available.
        """
        # Predict valence: weighted average of recent history, recency-weighted
        if self._valence_history:
            weights = [i + 1 for i in range(len(self._valence_history))]
            total_w = sum(weights)
            predicted_valence = sum(
                v * w for v, w in zip(self._valence_history, weights)
            ) / total_w
        else:
            predicted_valence = 0.0

        # Predict drive: most frequent recent drive
        if self._drive_history:
            from collections import Counter
            recent = list(self._drive_history)[-10:]
            counts = Counter(recent)
            predicted_drive = counts.most_common(1)[0][0]
        else:
            predicted_drive = "curiosity"

        # Predict focus: most frequent recent focus source
        if self._focus_history:
            from collections import Counter
            recent_focus = list(self._focus_history)[-10:]
            counts = Counter(recent_focus)
            predicted_focus = counts.most_common(1)[0][0]
        else:
            predicted_focus = "drive_curiosity"

        # Confidence: inversely proportional to recent prediction error
        confidence = max(0.1, 1.0 - self._smoothed_error)

        return InternalStatePrediction(
            predicted_affect_valence=round(predicted_valence, 3),
            predicted_dominant_drive=predicted_drive,
            predicted_focus_source=predicted_focus,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Internal: error computation
    # ------------------------------------------------------------------

    def _compute_error(
        self,
        pred: InternalStatePrediction,
        actual_valence: float,
        actual_drive: str,
        actual_focus: str,
    ) -> PredictionError:
        valence_err = abs(pred.predicted_affect_valence - actual_valence)
        drive_err = 0.0 if pred.predicted_dominant_drive == actual_drive else 1.0
        focus_err = 0.0 if pred.predicted_focus_source == actual_focus else 1.0

        # Weighted composite (valence is hardest to get right, so weighted lower)
        composite = (valence_err * 0.3) + (drive_err * 0.4) + (focus_err * 0.3)
        composite = min(1.0, composite)

        return PredictionError(
            valence_error=round(valence_err, 3),
            drive_error=drive_err,
            focus_error=focus_err,
            composite_error=round(composite, 3),
            was_surprising=composite > self._SURPRISE_THRESHOLD,
        )

    def _record_error(self, error: PredictionError):
        self._error_history.append(error)
        if error.was_surprising:
            self._surprise_count += 1

        # Update smoothed error (EMA)
        self._smoothed_error = (
            self._ERROR_SMOOTHING * error.composite_error
            + (1 - self._ERROR_SMOOTHING) * self._smoothed_error
        )

        # Update per-dimension EMAs
        self._valence_error_ema = (
            self._ERROR_SMOOTHING * error.valence_error
            + (1 - self._ERROR_SMOOTHING) * self._valence_error_ema
        )
        self._drive_error_ema = (
            self._ERROR_SMOOTHING * error.drive_error
            + (1 - self._ERROR_SMOOTHING) * self._drive_error_ema
        )
        self._focus_error_ema = (
            self._ERROR_SMOOTHING * error.focus_error
            + (1 - self._ERROR_SMOOTHING) * self._focus_error_ema
        )

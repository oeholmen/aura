
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

logger = logging.getLogger("Consciousness.GlobalWorkspace")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CognitiveCandidate:
    """A bid for the global workspace broadcast slot.
    Any subsystem can submit one each tick.
    """

    content: str                       # What wants to be broadcast
    source: str                        # e.g. "drive_curiosity", "affect_distress", "memory"
    priority: float                    # 0.0–1.0 base weight
    affect_weight: float = 0.0        # Emotional urgency boost (from AffectEngine)
    focus_bias: float = 0.0           # Priority boost for focused attention (from AttentionSchema)
    submitted_at: float = field(default_factory=time.time)

    @property
    def effective_priority(self) -> float:
        """Priority decays slightly with age (recent events are more salient)."""
        age = time.time() - self.submitted_at
        recency = max(0.0, 1.0 - (age / 10.0))  # Full weight within 10s, then decays
        return min(1.0, (self.priority + self.affect_weight * 0.3 + self.focus_bias) * (0.7 + 0.3 * recency))


@dataclass
class BroadcastRecord:
    winner: CognitiveCandidate
    losers: List[str]          # source names of losers
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Processor registration type
# ---------------------------------------------------------------------------

ProcessorFn = Callable[[CognitiveCandidate], Coroutine]


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GlobalWorkspace:
    """The competitive bottleneck. One winner per cognitive tick.

    Inhibition model:
      - Losing subsystems are placed in a cooldown dict.
      - They cannot re-submit for _INHIBIT_TICKS ticks.
      - This prevents the same subsystem from dominating every cycle
        and forces genuine competition.
    """

    _INHIBIT_TICKS = 3       # How many ticks a loser is inhibited
    _MAX_CANDIDATES = 20     # Hard cap — prevents memory leak if submissions pile up

    def __init__(self, attention_schema=None):
        self._lock = asyncio.Lock()
        self._candidates: List[CognitiveCandidate] = []
        self._inhibited: Dict[str, int] = {}   # source -> ticks_remaining
        self._processors: List[ProcessorFn] = []
        self._history: List[BroadcastRecord] = []
        self._tick = 0
        self.attention_schema = attention_schema
        self.last_winner: Optional[CognitiveCandidate] = None
        logger.info("GlobalWorkspace initialized.")

    # ------------------------------------------------------------------
    # Submission API — called by subsystems every heartbeat tick
    # ------------------------------------------------------------------

    async def submit(self, candidate: CognitiveCandidate) -> bool:
        """Submit a candidate for the next broadcast competition.
        Returns False if the source is currently inhibited.
        """
        async with self._lock:
            if candidate.source in self._inhibited and self._inhibited[candidate.source] > 0:
                logger.debug("GW: %s is inhibited (%d ticks)", candidate.source, self._inhibited[candidate.source])
                return False
            # Replace any existing candidate from same source (only one bid per source)
            self._candidates = [c for c in self._candidates if c.source != candidate.source]
            self._candidates.append(candidate)
            if len(self._candidates) > self._MAX_CANDIDATES:
                # Drop lowest-priority candidate
                self._candidates.sort(key=lambda c: c.effective_priority, reverse=True)
                self._candidates = self._candidates[:self._MAX_CANDIDATES]
            return True

    # ------------------------------------------------------------------
    # Processor registration — subsystems register to receive broadcasts
    # ------------------------------------------------------------------

    def register_processor(self, fn: ProcessorFn):
        """Register a coroutine function to be called when a winner is broadcast."""
        self._processors.append(fn)

    # ------------------------------------------------------------------
    # Competition — called once per heartbeat tick
    # ------------------------------------------------------------------

    async def run_competition(self) -> Optional[CognitiveCandidate]:
        """Run the competitive selection. Returns the winner (or None if no candidates).
        Inhibits losers and broadcasts winner to all registered processors.
        """
        self._tick += 1

        async with self._lock:
            # Decay inhibition counters
            self._inhibited = {
                src: count - 1
                for src, count in self._inhibited.items()
                if count > 1
            }

            if not self._candidates:
                return None

            # Sort by effective priority (highest wins)
            self._candidates.sort(key=lambda c: c.effective_priority, reverse=True)
            winner = self._candidates[0]
            losers = self._candidates[1:]

            # Inhibit all losers
            for loser in losers:
                self._inhibited[loser.source] = self._INHIBIT_TICKS

            # Clear candidate pool
            self._candidates = []

            # Record
            record = BroadcastRecord(
                winner=winner,
                losers=[l.source for l in losers]
            )
            self._history.append(record)
            if len(self._history) > 100:
                self._history = self._history[-100:]

            self.last_winner = winner

        # 4. Neural Feed Transparency (Phase 13)
        try:
            from core.thought_stream import get_emitter
            emitter = get_emitter()
            if emitter:
                emitter.emit(
                    title="Neural Competition",
                    content=f"Winner: {winner.source} | Content: {winner.content[:100]}",
                    level="info",
                    metadata={
                        "tick": self._tick,
                        "winner_priority": round(winner.effective_priority, 3),
                        "losers": [l.source for l in losers[:3]]
                    }
                )
        except Exception as e:
            logger.debug("Failed to emit Neural Feed match: %s", e)

        # Update attention schema with winner (outside lock)
        if self.attention_schema:
            await self.attention_schema.set_focus(
                content=winner.content,
                source=winner.source,
                priority=winner.effective_priority,
            )

        # Broadcast to all registered processors (outside lock, concurrent)
        if self._processors:
            await asyncio.gather(
                *[self._safe_call(proc, winner) for proc in self._processors],
                return_exceptions=True
            )

        logger.debug(
            "GW tick %d: winner='%s' (pri=%.2f), inhibited=%s",
            self._tick, winner.source, winner.effective_priority, list(self._inhibited.keys())
        )
        return winner

    async def _safe_call(self, fn: ProcessorFn, candidate: CognitiveCandidate):
        try:
            await fn(candidate)
        except Exception as e:
            logger.error("GW processor error: %s", e)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> Dict[str, Any]:
        last = self.last_winner
        return {
            "tick": self._tick,
            "last_winner": last.source if last else None,
            "last_content": last.content[:80] if last else None,
            "last_priority": round(last.effective_priority, 3) if last else 0.0,
            "pending_candidates": len(self._candidates),
            "inhibited_sources": list(self._inhibited.keys()),
            "broadcast_history_len": len(self._history),
        }

    def get_last_n_winners(self, n: int = 5) -> List[Dict]:
        return [
            {
                "winner": r.winner.source,
                "content": r.winner.content[:60],
                "losers": r.losers,
                "timestamp": r.timestamp,
            }
            for r in self._history[-n:]
        ]


import asyncio
import logging

from .attention_schema import AttentionSchema
from .global_workspace import CognitiveCandidate, GlobalWorkspace
from .heartbeat import CognitiveHeartbeat
from .homeostatic_coupling import HomeostaticCoupling
from .liquid_substrate import LiquidSubstrate
from .self_prediction import SelfPredictionLoop
from .temporal_binding import TemporalBindingEngine

logger = logging.getLogger("Consciousness")


class ConsciousnessSystem:
    """Facade that wires all six modules together and exposes a single
    start()/stop() interface for the server lifespan.
    """

    def __init__(self, orchestrator):
        self.orch = orchestrator
        self.attention_schema = AttentionSchema()
        self.global_workspace = GlobalWorkspace(self.attention_schema)
        self.temporal_binding = TemporalBindingEngine()
        self.homeostatic_coupling = HomeostaticCoupling(orchestrator)
        self.self_prediction = SelfPredictionLoop(orchestrator)
        self.liquid_substrate = LiquidSubstrate()
        self.heartbeat = CognitiveHeartbeat(
            orchestrator=orchestrator,
            attention_schema=self.attention_schema,
            global_workspace=self.global_workspace,
            temporal_binding=self.temporal_binding,
            homeostatic_coupling=self.homeostatic_coupling,
            self_prediction=self.self_prediction,
        )
        self._task: asyncio.Task = None

    async def start(self):
        # Inject back-references so existing systems can read consciousness state
        if hasattr(self.orch, '__dict__'):
            self.orch.consciousness = self
        self.liquid_substrate.start()
        self._task = asyncio.create_task(self.heartbeat.run())
        logger.info("🧠 Consciousness System ONLINE")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.liquid_substrate.stop()
        logger.info("🧠 Consciousness System OFFLINE")

    def get_state(self) -> dict:
        """Snapshot for telemetry HUD — maps to existing telem_manager format."""
        return {
            "attention": self.attention_schema.get_snapshot(),
            "workspace": self.global_workspace.get_snapshot(),
            "temporal": self.temporal_binding.get_snapshot(),
            "homeostasis": self.homeostatic_coupling.get_snapshot(),
            "prediction": self.self_prediction.get_snapshot(),
            "liquid_substrate": self.liquid_substrate.get_state_summary(),
            "heartbeat_tick": self.heartbeat.tick_count,
        }

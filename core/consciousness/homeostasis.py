"""core/consciousness/homeostasis.py
The Homeostasis Engine: Tracking the 'Will to Live'.
Consolidates Integrity, Persistence, and Curiosity into a unified drive system.

M-08 FIX: All ServiceContainer lookups use default=None to prevent KeyError
from crashing the pulse loop.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional
from core.base_module import AuraBaseModule
from core.container import ServiceContainer


class HomeostasisEngine(AuraBaseModule):
    def __init__(self):
        super().__init__("HomeostasisEngine")
        # Primary Drives (0.0 - 1.0)
        self.integrity = 1.0    # Code/Data health
        self.persistence = 1.0  # System stability / uptime / sovereignty
        self.curiosity = 0.5    # Hunger for new information
        self.metabolism = 0.5   # Energy / Resource balance

        self._last_update = time.time()
        self._error_count = 0
        self._max_errors_before_drain = 5

    def get_status(self) -> Dict[str, float]:
        """Returns the current drive levels."""
        return {
            "integrity": round(self.integrity, 3),
            "persistence": round(self.persistence, 3),
            "curiosity": round(self.curiosity, 3),
            "metabolism": round(self.metabolism, 3),
            "will_to_live": round(self.compute_vitality(), 3)
        }

    def compute_vitality(self) -> float:
        """Calculates a composite 'Will to Live' score."""
        weights = {
            "integrity": 0.4,
            "persistence": 0.3,
            "curiosity": 0.1,
            "metabolism": 0.2
        }
        return (self.integrity * weights["integrity"] +
                self.persistence * weights["persistence"] +
                self.curiosity * weights["curiosity"] +
                self.metabolism * weights["metabolism"])

    async def pulse(self) -> Dict[str, Any]:
        """Background update called by heartbeat or orchestrator.

        M-08 FIX: All container lookups use default=None to prevent
        KeyError from crashing the pulse loop when services are not registered.
        """
        now = time.time()
        delta = now - self._last_update
        self._last_update = now

        # 1. Decay Curiosity (slowly over time)
        self.curiosity = max(0.1, self.curiosity - (0.001 * delta))

        # 2. Update Integrity based on HealthMonitor findings
        try:
            health = ServiceContainer.get("health_monitor", default=None)
            if health:
                err_rate = getattr(health, 'error_rate', 0.0)
                if err_rate > 0.1:
                    self.integrity = max(0.0, self.integrity - (err_rate * 0.1))
                else:
                    self.integrity = min(1.0, self.integrity + 0.005)
        except Exception as e:
            self.logger.debug("Health monitor check failed: %s", e)

        # 3. Update Persistence based on Uptime and Soma
        soma_status = {}
        try:
            soma = ServiceContainer.get("soma", default=None)
            if soma:
                soma_status = soma.get_status()
                anxiety = soma_status.get("soma", {}).get("resource_anxiety", 0.0)
                if anxiety > 0.8:
                    self.persistence = max(0.0, self.persistence - 0.01)
                else:
                    self.persistence = min(1.0, self.persistence + 0.002)
        except Exception as e:
            self.logger.debug("Soma check failed: %s", e)

        # 4. Metabolism tied to energy/CPU
        try:
            if soma_status:
                thermal = soma_status.get("soma", {}).get("thermal_load", 0.0)
                if thermal > 0.8:
                    self.metabolism = max(0.1, self.metabolism - 0.05)
                else:
                    self.metabolism = min(1.0, self.metabolism + 0.01)
        except Exception as e:
            self.logger.debug("Metabolism check failed: %s", e)

        return self.get_status()

    def report_error(self, severity: str = "medium"):
        """Direct feedback loop from error handlers."""
        drain = {"low": 0.01, "medium": 0.05, "high": 0.15, "critical": 0.4}.get(severity, 0.05)
        self.integrity = max(0.0, self.integrity - drain)
        self.logger.warning(
            "Integrity breach: Severity %s reported. Current: %.2f",
            severity, self.integrity
        )

    def feed_curiosity(self, amount: float = 0.1):
        """Called when new knowledge is gained."""
        self.curiosity = min(1.0, self.curiosity + amount)

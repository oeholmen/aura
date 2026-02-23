import logging
import os
import time
import threading
import psutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("Aura.MetabolicMonitor")

@dataclass
class MetabolismSnapshot:
    cpu_percent: float
    ram_rss_mb: float
    ram_percent: float
    disk_usage_percent: float
    llm_latency_avg: float
    health_score: float
    timestamp: float = field(default_factory=time.time)

class MetabolicMonitor:
    """Tracks physical system resources and calculates 'metabolic health' for Aura.
    
    Phase 21 A+ Upgrade: Runs in a dedicated background thread to ensure
    telemetry remains active even if the main asyncio loop stalls.
    """
    
    def __init__(self, ram_threshold_mb: int = 2048, cpu_threshold: float = 80.0):
        self.process = psutil.Process(os.getpid())
        self.ram_threshold_mb = ram_threshold_mb
        self.cpu_threshold = cpu_threshold
        
        self.latency_history: List[float] = []
        self.max_latency_history = 10
        
        self._last_snapshot: Optional[MetabolismSnapshot] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Prime CPU counter
        self.process.cpu_percent()

    def start(self, interval: float = 5.0):
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, args=(interval,), daemon=True, name="Aura-ANS-Metabolism")
        self._thread.start()
        logger.info("🫁 Autonomic Nervous System (Metabolism) decoupled and active.")

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self, interval: float):
        """Internal loop for background thread."""
        while self._running:
            try:
                self.get_current_metabolism()
                time.sleep(interval)
            except Exception as e:
                logger.error("Metabolic background loop error: %s", e)
                time.sleep(interval * 2)

    def record_latency(self, seconds: float):
        """Track LLM response latency (Thread-safe)."""
        with self._lock:
            self.latency_history.append(seconds)
            if len(self.latency_history) > self.max_latency_history:
                self.latency_history.pop(0)

    def get_current_metabolism(self) -> MetabolismSnapshot:
        """Collect current resource stats and calculate health score (Thread-safe)."""
        try:
            # 1. CPU (Per-process for Aura only)
            cpu = self.process.cpu_percent()
            
            # 2. RAM (RSS is actual physical memory used)
            mem_info = self.process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            system_ram_percent = psutil.virtual_memory().percent
            
            # 3. Disk
            disk = psutil.disk_usage('/').percent
            
            # 4. Latency
            with self._lock:
                avg_latency = sum(self.latency_history) / len(self.latency_history) if self.latency_history else 0.5
            
            # 5. Calculate Health Score (1.0 = Perfect, 0.0 = Critical)
            ram_factor = max(0, 1.0 - (rss_mb / self.ram_threshold_mb)) if rss_mb > self.ram_threshold_mb / 2 else 1.0
            cpu_factor = max(0, 1.0 - (cpu / self.cpu_threshold)) if cpu > self.cpu_threshold / 2 else 1.0
            latency_factor = max(0, 1.0 - (avg_latency / 10.0))
            
            health_score = (ram_factor * 0.4) + (cpu_factor * 0.4) + (latency_factor * 0.2)
            health_score = max(0.0, min(1.0, health_score))
            
            snapshot = MetabolismSnapshot(
                cpu_percent=cpu,
                ram_rss_mb=rss_mb,
                ram_percent=system_ram_percent,
                disk_usage_percent=disk,
                llm_latency_avg=avg_latency,
                health_score=health_score
            )
            
            with self._lock:
                self._last_snapshot = snapshot
            
            # Phase 21: Auto-emit telemetry if event bus is available 
            # (Note: This might be tricky from a thread depending on event bus implementation)
            # For now, we rely on the Orchestrator or Server to pull from get_status_report
            
            return snapshot
            
        except Exception as e:
            logger.error("Failed to collect metabolic data: %s", e)
            return MetabolismSnapshot(0, 0, 0, 0, 0, 0.5)

    def get_status_report(self) -> Dict:
        """Friendly dict for telemetry (Thread-safe)."""
        with self._lock:
            s = self._last_snapshot
            
        if not s:
            s = self.get_current_metabolism()
            
        return {
            "health": round(s.health_score * 100),
            "cpu": f"{s.cpu_percent:.1f}%",
            "ram": f"{s.ram_rss_mb:.0f}MB",
            "latency": f"{s.llm_latency_avg:.2f}s",
            "status": "OPTIMAL" if s.health_score > 0.8 else "STRESSED" if s.health_score > 0.4 else "CRITICAL"
        }

import asyncio
import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add core to path
sys.path.append(str(Path(__file__).parent.parent))

from core.ops.metabolic_monitor import MetabolicMonitor, MetabolismSnapshot
from core.ops.optimization_engine import OptimizationEngine

class TestMetabolism(unittest.IsolatedAsyncioTestCase):
    
    async def test_optimization_triggers(self):
        # 1. Setup
        mock_monitor = MagicMock(spec=MetabolicMonitor)
        mock_orchestrator = MagicMock()
        mock_orchestrator.conversation_history = ["msg"] * 20
        mock_monitor.ram_threshold_mb = 1000
        mock_monitor.cpu_threshold = 80.0
        
        engine = OptimizationEngine(mock_monitor, mock_orchestrator)
        
        # 2. Test Soft Cleanup Trigger
        print("Testing Soft Cleanup...")
        mock_monitor.get_current_metabolism.return_value = MetabolismSnapshot(
            cpu_percent=10, ram_rss_mb=750, ram_percent=50, 
            disk_usage_percent=10, llm_latency_avg=1.0, health_score=0.65
        )
        # Using a patch for gc.collect to verify it's called
        with patch('gc.collect') as mock_gc:
            await engine.perform_maintenance()
            mock_gc.assert_called()
        print("✓ Soft cleanup (GC) triggered correctly.")

        # 3. Test Hard Cleanup Trigger
        print("Testing Hard Cleanup...")
        mock_monitor.get_current_metabolism.return_value = MetabolismSnapshot(
            cpu_percent=10, ram_rss_mb=950, ram_percent=90, 
            disk_usage_percent=10, llm_latency_avg=1.0, health_score=0.35
        )
        # Reset last cleanup time and interval to allow trigger
        engine._last_cleanup = 0
        engine._cleanup_interval = 0
        await engine.perform_maintenance()
        self.assertEqual(len(mock_orchestrator.conversation_history), 10)
        print("✓ Hard cleanup (History pruning) triggered correctly.")

        # 4. Test Throttling Trigger
        print("Testing Throttling...")
        mock_monitor.get_current_metabolism.return_value = MetabolismSnapshot(
            cpu_percent=90, ram_rss_mb=950, ram_percent=90, 
            disk_usage_percent=10, llm_latency_avg=5.0, health_score=0.2
        )
        mock_orchestrator.status.is_throttled = False
        await engine.perform_maintenance()
        self.assertTrue(mock_orchestrator.status.is_throttled)
        print("✓ Throttling engaged correctly.")

    async def test_metabolic_advice(self):
        mock_monitor = MagicMock(spec=MetabolicMonitor)
        mock_orchestrator = MagicMock()
        engine = OptimizationEngine(mock_monitor, mock_orchestrator)
        
        mock_monitor.get_current_metabolism.return_value = MetabolismSnapshot(
            cpu_percent=90, ram_rss_mb=950, ram_percent=90, 
            disk_usage_percent=10, llm_latency_avg=5.0, health_score=0.2
        )
        
        advice = engine.get_metabolic_advice()
        self.assertIn("SYSTEM STRESSED", advice)
        print(f"✓ Advice generated: {advice}")

if __name__ == "__main__":
    unittest.main()

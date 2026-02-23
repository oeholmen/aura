import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from core.senses.pulse_manager import PulseManager

class MockOrchestrator:
    def __init__(self):
        self.message_queue = asyncio.Queue()
        self.is_busy = False
        self.metabolic_monitor = MagicMock()
        self.optimization_engine = MagicMock()
        self.optimization_engine.perform_maintenance = AsyncMock() # Use AsyncMock for async calls
    
    def enqueue_message(self, msg):
        self.message_queue.put_nowait(msg)

@pytest.mark.asyncio
async def test_pulse_manager_start_stop():
    orch = MockOrchestrator()
    pm = PulseManager(orch)
    
    await pm.start()
    assert pm.running is True
    assert len(pm._sampling_tasks) == 3
    
    await pm.stop()
    assert pm.running is False
    assert len(pm._sampling_tasks) == 0

@pytest.mark.asyncio
async def test_system_pulse_critical_health():
    orch = MockOrchestrator()
    pm = PulseManager(orch)
    pm.system_sample_interval = 0.1
    
    # Mock critical health
    mock_snapshot = MagicMock()
    mock_snapshot.health_score = 0.2
    orch.metabolic_monitor.get_current_metabolism.return_value = mock_snapshot
    
    await pm.start()
    await asyncio.sleep(0.2)
    await pm.stop()
    
    assert orch.message_queue.qsize() > 0
    msg = await orch.message_queue.get()
    assert "critical" in msg.lower()

@pytest.mark.asyncio
async def test_vision_pulse_idle():
    orch = MockOrchestrator()
    pm = PulseManager(orch)
    pm.vision_sample_interval = 0.1
    
    from core.container import ServiceContainer
    mock_vision = AsyncMock()
    mock_vision.analyze_moment.return_value = "Warning: low disk space"
    ServiceContainer.register_instance("vision_engine", mock_vision)
    
    await pm.start()
    await asyncio.sleep(0.2)
    await pm.stop()
    
    # Verify interjection
    assert orch.message_queue.qsize() > 0
    msg = await orch.message_queue.get()
    assert "warning" in msg.lower()

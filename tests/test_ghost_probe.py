"""tests/test_ghost_probe.py
Unit test for Ghost Probe deployment logic.
"""
import asyncio
import os
import unittest
from unittest.mock import MagicMock
from core.collective.probe_manager import ProbeManager
from core.skills.ghost_probe import GhostProbeSkill
from core.container import ServiceContainer

class TestGhostProbe(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ServiceContainer.clear()
        self.orchestrator = MagicMock()
        # Mock loop for run_in_executor
        self.orchestrator.loop = asyncio.get_running_loop()
        self.manager = ProbeManager(self.orchestrator)
        ServiceContainer.register_instance("probe_manager", self.manager)
        self.skill = GhostProbeSkill(self.orchestrator)

    async def asyncTearDown(self):
        """Ensure all probes are killed."""
        probe_ids = list(self.manager.probes.keys())
        for pid in probe_ids:
            try:
                await self.manager.cleanup_probe(pid)
            except:
                pass
        await self.manager.stop()

    async def test_probe_lifecycle(self):
        # 1. Deploy
        probe_id = "test-ghost-1"
        target = "/tmp/test_target.txt"
        with open(target, "w") as f: f.write("hello")
        
        from core.skills.ghost_probe import GhostProbeParams
        params = GhostProbeParams(probe_id=probe_id, target=target, type="file", duration=10)
        success = await self.skill.execute(params)
        self.assertTrue("successfully deployed" in success)
        self.assertIn(probe_id, self.manager.probes)
        
        # Check if process is running
        process = self.manager.probes[probe_id]
        self.assertIsNone(process.poll())
        
        # 2. Cleanup
        await self.manager.cleanup_probe(probe_id)
        self.assertNotIn(probe_id, self.manager.probes)
        
        # Verify file cleanup
        probe_file = f"/tmp/aura_probe_{probe_id}.py"
        self.assertFalse(os.path.exists(probe_file))
        
        os.remove(target)

if __name__ == '__main__':
    unittest.main()

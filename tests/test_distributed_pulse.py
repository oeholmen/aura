"""tests/test_distributed_pulse.py
Unit test for PulseManager distributed discovery logic.
"""
import asyncio
import json
import socket
import unittest
from unittest.mock import MagicMock, patch
import time

from core.senses.pulse_manager import PulseManager

class TestPulseDiscovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.orchestrator = MagicMock()
        self.orchestrator.loop = asyncio.get_event_loop()
        self.orchestrator.peers = {}
        self.pulse_manager = PulseManager(self.orchestrator)
        self.pulse_manager.running = True

    @patch('socket.socket')
    async def test_peer_discovery(self, mock_socket):
        # Setup mock socket
        mock_sock_inst = mock_socket.return_value
        
        # Prepare fake incoming pulse
        fake_pulse = {
            "type": "aura_pulse",
            "id": "aura-remote-test",
            "status": "active",
            "timestamp": time.time()
        }
        fake_data = json.dumps(fake_pulse).encode()
        fake_addr = ("192.168.1.100", 5555)

        # Mock recvfrom to return data once then raise BlockingIOError
        mock_sock_inst.recvfrom.side_effect = [(fake_data, fake_addr), BlockingIOError()]

        # Run one iteration of the discovery logic manually (or a subset)
        # We'll just run the loop logic once
        task = asyncio.create_task(self.pulse_manager._distributed_pulse_loop())
        
        # Give it a tiny bit of time to run the first loop
        await asyncio.sleep(0.5)
        
        # Check if peer was added
        self.assertIn("aura-remote-test", self.orchestrator.peers)
        self.assertEqual(self.orchestrator.peers["aura-remote-test"]["address"], "192.168.1.100")
        
        # Cleanup
        self.pulse_manager.running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

if __name__ == '__main__':
    unittest.main()

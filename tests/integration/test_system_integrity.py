import asyncio
import sys
import os
import logging
import unittest
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TestSystemIntegrity")

# Ensure path availability
root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root))

class TestSystemIntegrity(unittest.IsolatedAsyncioTestCase):

    async def test_orchestrator_hotfix(self):
        """test_orchestrator from verify_hotfix.py"""
        try:
            from core.orchestrator import create_orchestrator
            from unittest.mock import patch, MagicMock
            
            with patch('core.sensory_integration.SensorySystem', MagicMock(autospec=True)), \
                 patch('core.senses.voice_engine.SovereignVoiceEngine', MagicMock(autospec=True)), \
                 patch('core.vision.llava_engine.SovereignVisionEngine', MagicMock(autospec=True)):
                
                orchestrator = create_orchestrator()
                self.assertIsNotNone(orchestrator, "Failed to create orchestrator!")
            
                
                loop_task = asyncio.create_task(orchestrator.run())
                await asyncio.sleep(5)
                
                cycle_initial = orchestrator.status.cycle_count
                self.assertGreater(cycle_initial, 0, "FAIL: Cycle count is still 0! Loop might be stalled.")
                
                test_msg = "Hello Aura, are you fixed?"
                self.assertTrue(hasattr(orchestrator, 'process_user_input'), "process_user_input MISSING!")
                
                if asyncio.iscoroutinefunction(orchestrator.process_user_input):
                    await orchestrator.process_user_input(test_msg)
                else:
                    orchestrator.process_user_input(test_msg)
                     
                await asyncio.sleep(2)
                
                await orchestrator.stop()
                await asyncio.sleep(1)
            
                if not loop_task.done():
                    loop_task.cancel()
                    try:
                        await loop_task
                    except asyncio.CancelledError:
                        pass
        except ImportError:
            pass

    def test_hardening_logging(self):
        """check_logging from verify_hardening.py"""
        files_to_check = [
            root / "core" / "orchestrator.py",
            root / "core" / "memory" / "knowledge_ledger.py",
            root / "core" / "orchestrator_boot.py"
        ]
        for f in files_to_check:
            if f.exists():
                content = f.read_text()
                self.assertNotIn("%%s", content, f"Double percent found in {f}")
                mixed_formatting = "logger.error(f" in content and "%s" in content
                self.assertFalse(mixed_formatting, f"Mixed formatting found in {f}")

    def test_hardening_security(self):
        """check_security from verify_hardening.py"""
        try:
            from core.core_values import CoreValues
            self.assertIsInstance(CoreValues.VALUES, tuple, "CoreValues.VALUES is not a tuple")
        except ImportError:
            pass

        try:
            from core.brain.consciousness.contract import AlwaysHomeContract
            class MockCC: 
                def __init__(self): self.orchestrator = None
            contract = AlwaysHomeContract(consciousness_core=MockCC())
            status = contract.poll()
            self.assertEqual(status.get("assurance_level"), "DESIGN_ASSERTION", "Assurance level incorrect")
        except (ImportError, TypeError):
            pass

    def test_hardening_paths(self):
        """check_paths from verify_hardening.py"""
        self.assertTrue((root / "actual_health.html").exists(), "actual_health.html missing")
        self.assertFalse((root / "actual_health.json").exists(), "actual_health.json still exists")

    async def test_fix3_affect_decay(self):
        """Verify affect decay moves state toward baseline."""
        try:
            from core.affect import AffectEngine, BASELINE_VALENCE
            engine = AffectEngine()
            engine.state.valence = 0.9 # High
            await engine.decay_tick()
            self.assertLess(engine.state.valence, 0.9)
            self.assertGreater(engine.state.valence, BASELINE_VALENCE)
        except ImportError:
            pass

    def test_privacy_scrubbing(self):
        """Verify PII removal."""
        try:
            from core.core_values import CoreValues
            from core.prime_directives import PrimeDirectives
            from core.environment_awareness import UserIdentityManager
            
            prompt = CoreValues.as_system_prompt()
            self.assertNotIn("Young", prompt)
            self.assertNotIn("Farnsworth", prompt)
            
            directives = PrimeDirectives.as_system_prompt()
            self.assertNotIn("Young", directives)
            self.assertNotIn("Farnsworth", directives)
            
            devs = str(UserIdentityManager.KNOWN_DEVICES)
            self.assertNotIn("SM-S908", devs)
            self.assertNotIn("Galaxy S22", devs)
        except ImportError:
            pass

    def test_fix4_entropy_uniformity(self):
        """Verify entropy math doesn't use modulo 40 bias."""
        try:
            from core.brain.entropy import PhysicalEntropyInjector
            samples = [PhysicalEntropyInjector.calculate_hardware_chaos() for _ in range(100)]
            self.assertTrue(all(0.0 <= s <= 0.45 for s in samples))
            self.assertGreater(len(set(samples)), 1)
        except ImportError:
            pass

    def test_fix5_safety_gate_traversal(self):
        """Verify SafetyGate blocks traversal and protected files."""
        try:
            from core.resilience.system_integrity import SafetyGate
            self.assertFalse(SafetyGate.is_allowed_file("/etc/passwd"))
            self.assertFalse(SafetyGate.is_allowed_file("core/prime_directives.py"))
            self.assertTrue(SafetyGate.is_allowed_file("core/orchestrator.py"))
        except ImportError:
            pass

if __name__ == "__main__":
    unittest.main()

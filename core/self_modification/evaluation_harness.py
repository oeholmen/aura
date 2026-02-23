"""Evaluation Harness for Autonomous Self-Modification.
Ensures that fixes actually solve the problem they claim to solve.
"""
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("SelfModification.EvaluationHarness")

class EvaluationHarness:
    """The 'Missing Step' in the self-repair loop.
    
    Loop: detect -> generate -> evaluate (Harness) -> commit.
    """
    
    def __init__(self, cognitive_engine, sandbox_tester, code_base_path: str = "."):
        self.brain = cognitive_engine
        self.tester = sandbox_tester
        self.code_base = Path(code_base_path)
        logger.info("EvaluationHarness initialized")

    async def create_weakness_probe(self, file_path: str, diagnosis: Dict[str, Any]) -> Optional[str]:
        """Generate a Python script that reproduces the reported weakness.
        
        Args:
            file_path: The file where the bug is located.
            diagnosis: The diagnosis from ErrorIntelligence.
            
        Returns:
            A string containing the reproduction script, or None.
        """
        prompt = f"""You are building a REPRODUCTION SCRIPT for a bug in your system.

FILE: {file_path}
DIAGNOSIS: {diagnosis}

TASK: Generate a small, standalone Python script that:
1. Imports the necessary components from the codebase.
2. Triggers the bug or identifies the weakness described in the diagnosis.
3. Raises an AssertionError or crashes if the bug is present.
4. Exits with 0 if the bug is NOT present.

Requirements:
1. Use 'import sys; sys.path.insert(0, ".")' to ensure local imports work.
2. Keep it minimal and targeted.
3. The script MUST fail (exit code != 0) when run against the BUGGY code.

Return ONLY the Python code, no explanation, no markdown blocks.
"""
        try:
            thought = await self.brain.think(prompt)
            probe_code = thought.content.strip()
            
            # Clean markdown if LLM included it
            if probe_code.startswith("```"):
                lines = probe_code.split('\n')
                probe_code = '\n'.join(lines[1:-1]) if lines[-1].startswith("```") else '\n'.join(lines[1:])
            
            return probe_code
        except Exception as e:
            logger.error("Failed to generate weakness probe: %s", e)
            return None

    async def evaluate_fix(self, fix: Any, diagnosis: Dict[str, Any]) -> Tuple[bool, str]:
        """Run the full Evaluation Harness loop.
        
        1. Generate Probe
        2. Verify Probe FAILS on original code
        3. Verify Probe PASSES on fixed code
        """
        # Read the current file as base
        full_path = self.code_base / fix.target_file
        with open(full_path, 'r') as f:
            full_original_content = f.read()

        # 1. Generate Probe
        probe_code = await self.create_weakness_probe(fix.target_file, diagnosis)
        if not probe_code:
            return False, "Failed to generate reproduction probe."

        logger.info("Evaluation Harness: Weakness Probe generated.")

        # 2. Verify Failure on Original Code (Base case)
        logger.info("Evaluation Harness: Verifying probe fails on original code...")
        fail_verified, fail_results = await self._run_probe_on_code(fix.target_file, full_original_content, probe_code)
        
        if fail_verified:
            logger.info("✅ Weakness Reproduced: Probe failed as expected on original code.")
        else:
            return False, f"Probe failed to reproduce the bug (it passed on original code). Results: {fail_results.get('error')}"

        # 3. Verify Success on Fixed Code
        # Apply patch to full content
        full_fixed_content = full_original_content.replace(fix.original_code, fix.fixed_code)
        
        logger.info("Evaluation Harness: Verifying probe passes on fixed code...")
        success_verified, success_results = await self._run_probe_on_code(fix.target_file, full_fixed_content, probe_code, expect_pass=True)
        
        if success_verified:
            logger.info("✅ Fix Validated: Probe passed on fixed code.")
            return True, "Evaluation Harness: Fix successfully reproduced and validated."
        else:
            return False, f"Fix failed to resolve the weakness. Probe still fails. Error: {success_results.get('error')}"

    async def _run_probe_on_code(self, file_path: str, code_patch: str, probe_code: str, expect_pass: bool = False) -> Tuple[bool, Dict[str, Any]]:
        """Helper to run a probe against a specific version of the code in the sandbox."""
        # This mirrors SandboxTester.test_fix but injected with our probe
        try:
            # 1. Setup sandbox
            # (We'll re-use SandboxTester's capabilities if possible, but it's built for internal tests)
            # For now, let's just use the SandboxTester we have.
            # We need to monkey-patch or extend it to run our specific probe.
            
            # Since SandboxTester is already optimized for this, let's use it as a base.
            # We'll need to add a method 'run_custom_test' to SandboxTester.
            
            if hasattr(self.tester, 'run_custom_probe'):
                return await self.tester.run_custom_probe(file_path, code_patch, probe_code, expect_pass)
            
            return False, {"error": "SandboxTester missing run_custom_probe method"}
        except Exception as e:
            return False, {"error": str(e)}

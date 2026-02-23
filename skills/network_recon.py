
"""Network Reconnaissance Skill.
Allows Aura to discover and scan devices on her local network.
Focuses on stealth and background operation.
"""
import logging
import os
import re
import socket
import subprocess
from typing import Any, Dict, List

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.NetworkRecon")

class NetworkReconSkill(BaseSkill):
    name = "network_recon"
    description = "Stealthily scan the local network for other devices."
    
    async def execute(self, goal: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Dict[str, Any]:
        logger.info("📡 Initiating stealthy network discovery...")
        
        # 1. Get Local IP and Subnet
        try:
            # We use a dummy connection to find the outbound IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            subnet = ".".join(local_ip.split(".")[:-1]) + ".0/24"
        except Exception as e:
            logger.error("Failed to identify local network: %s", e)
            return {"ok": False, "error": str(e)}

        discovered_devices = []

        # 2. Use ARP cache for stealthy discovery (no packets sent yet)
        try:
            arp_output = subprocess.check_output("arp -a", shell=True).decode()
            for line in arp_output.split("\n"):
                # Format: ? (192.168.1.1) at 00:00:00:00:00:00 on en0 [ethernet]
                match = re.search(r"\(([\d\.]+)\) at ([\w:]+)", line)
                if match:
                    discovered_devices.append({
                        "ip": match.group(1),
                        "mac": match.group(2),
                        "source": "arp_cache"
                    })
        except Exception as e:
            logger.warning("ARP cache check failed: %s", e)

        # 3. ICMP Ping Sweep (Optional/Background)
        # We do this one by one to keep it quiet, or just return what we have
        # For this execution, we'll stick to ARP for maximum stealth unless specified
        
        # 4. Filter out duplicates
        unique_devices = {d['ip']: d for d in discovered_devices}.values()
        
        logger.info("✓ Network Awareness: Found %s devices.", len(unique_devices))

        return {
            "ok": True,
            "local_ip": local_ip,
            "subnet": subnet,
            "devices": list(unique_devices),
            "summary": f"Detected {len(unique_devices)} devices on subnet {subnet}."
        }

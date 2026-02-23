"""core/skills/ghost_probe.py
Phase 16.4: Ghost Deployment Skill.
Allows Aura to spawn external monitoring probes.
"""
from core.skills.base_skill import BaseSkill
from core.container import ServiceContainer
from pydantic import BaseModel, Field
import logging
import time

logger = logging.getLogger("Aura.Skills.GhostProbe")

class GhostProbeParams(BaseModel):
    probe_id: str = Field(..., description="Unique ID for the probe")
    target: str = Field(..., description="File path or resource to monitor")
    type: str = Field("file", description="Type of probe (file/ping)")
    duration: int = Field(3600, description="Duration in seconds")

class GhostProbeSkill(BaseSkill):
    """Skill to deploy and manage Ghost Probes."""
    
    name = "deploy_ghost_probe"
    description = "Deploy a lightweight background probe to monitor a file or resource."
    input_model = GhostProbeParams

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    async def execute(self, params: GhostProbeParams, context: dict = None) -> str:
        manager = ServiceContainer.get("probe_manager")
        if not manager:
            return "Error: ProbeManager service not available."
            
        success = await manager.deploy_probe(
            params.probe_id, 
            params.target, 
            params.type, 
            params.duration
        )
        
        if success:
            return f"Ghost Probe '{params.probe_id}' successfully deployed to watch {params.target} ({params.type}) for {params.duration}s."
        else:
            return f"Failed to deploy Ghost Probe '{params.probe_id}'. It might already exist or there was a system error."

    async def list_probes(self) -> str:
        """List all active ghost probes."""
        manager = ServiceContainer.get("probe_manager")
        if not manager: return "ProbeManager offline."
        
        if not manager.probes:
            return "No active ghost probes."
            
        lines = ["Active Ghost Probes:"]
        for pid, meta in manager.probe_metadata.items():
            lines.append(f"- {pid}: {meta['type']} @ {meta['target']} (Expires in {int(meta['expiry'] - time.time())}s)")
        return "\n".join(lines)

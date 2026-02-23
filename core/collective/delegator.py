"""core/collective/delegator.py
Agent Swarm / Collective Intelligence Delegator (Swarm 2.0).
Allows the primary orchestrator to spawn specialized sub-tasks and synthesize consensus.
"""
import asyncio
import logging
import uuid
import time
from typing import Dict, List, Any, Optional, Callable
from core.base_module import AuraBaseModule

class SwarmAgent:
    """A lightweight parallel executor."""
    def __init__(self, agent_id: str, specialty: str):
        self.id = agent_id
        self.specialty = specialty
        self.status = "IDLE"
        self.start_time: Optional[float] = None
        self.result: Any = None

class AgentDelegator(AuraBaseModule):
    def __init__(self, orchestrator):
        super().__init__("AgentDelegator")
        self.orchestrator = orchestrator
        self.active_agents: Dict[str, SwarmAgent] = {}
        self.max_parallel = 5  # Increased for Swarm 2.0
        
        # Swarm 2.0 Factory Roles
        self.agent_roles = {
            "critic": "You are 'The Critic'. Analyze the provided proposal for flaws, edge cases, and security vulnerabilities. Be harsh but precise.",
            "architect": "You are 'The Architect'. Design the high-level structure to solve the problem. Focus on patterns, resilience, and scalability.",
            "researcher": "You are 'The Researcher'. Break down the problem and identify exactly what information is missing or needed to solve it.",
            "optimizer": "You are 'The Optimizer'. Look at the provided solution and find ways to make it faster, use less memory, or be more elegant."
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "active_count": len(self.active_agents),
            "agents": {aid: {"specialty": a.specialty, "status": a.status} for aid, a in self.active_agents.items()},
            "capacity": f"{len(self.active_agents)}/{self.max_parallel}"
        }

    async def delegate(self, specialty: str, task_prompt: str, callback: Optional[Callable] = None, parent_id: Optional[str] = None) -> str:
        """Spawns a sub-task and returns the agent ID (Swarm 2.0 recursive delegation support)."""
        if len(self.active_agents) >= self.max_parallel:
            self.logger.warning("🚫 Swarm capacity reached. Blocking delegation.")
            return ""

        # Recursive tracking string
        hierarchy = f"{parent_id}/" if parent_id else ""
        agent_id = f"ag-{uuid.uuid4().hex[:4]}"
        
        agent = SwarmAgent(agent_id, specialty)
        agent.status = "BUSY"
        agent.start_time = time.time()
        self.active_agents[agent_id] = agent

        self.logger.info("🐝 Spawning Swarm Agent: %s%s (%s)", hierarchy, agent_id, specialty)
        
        # Fire and forget the internal execution
        asyncio.create_task(self._run_agent(agent, task_prompt, callback))
        
        return agent_id
        
    async def delegate_debate(self, topic: str, roles: List[str] = ["architect", "critic"], timeout: float = 60.0) -> str:
        """Spawns multiple agents, waits for them, and synthesizes a consensus."""
        self.logger.info("🧠 Forming swarm debate on: %s...", topic[:50])
        
        agent_ids = []
        for role in roles:
            aid = await self.delegate(role, f"Analyze this topic from your perspective: {topic}")
            if aid:
                agent_ids.append(aid)
                
        if not agent_ids:
            return "Swarm capacity reached, debate cancelled."
            
        # Wait for debate to finish
        start = time.time()
        completed = False
        while time.time() - start < timeout:
            await asyncio.sleep(1.0)
            if all(self.active_agents.get(aid, SwarmAgent("", "")).status in ["COMPLETED", "FAILED"] for aid in agent_ids):
                completed = True
                break
                
        results = []
        for aid in agent_ids:
            if aid in self.active_agents and self.active_agents[aid].result:
                results.append(f"[{self.active_agents[aid].specialty.upper()}]:\n{self.active_agents[aid].result}")
                
        if not results:
            return "Swarm failed to produce a consensus."
            
        # Synthesize consensus
        return await self.synthesize_consensus(topic, results)

    async def synthesize_consensus(self, original_topic: str, agent_outputs: List[str]) -> str:
        """Synthesizes the outputs of multiple swarm agents into a single conclusion."""
        if not hasattr(self.orchestrator, 'cognitive_engine') or not self.orchestrator.cognitive_engine:
            return "No cognitive engine available for synthesis."
            
        combined_outputs = "\n\n---\n\n".join(agent_outputs)
        prompt = f"""You are the Master Synthesizer. Review the original problem and the analyses from your specialized swarm agents.
Formulate a final, conclusive recommendation or plan that balances their insights.

ORIGINAL PROBLEM:
{original_topic}

SWARM ANALYSES:
{combined_outputs}

FINAL SYNTHESIS:"""

        try:
            from core.brain.cognitive_engine import ThinkingMode
            res = await self.orchestrator.cognitive_engine.think(prompt, mode=ThinkingMode.DEEP, block_user=True)
            return res.content
        except Exception as e:
            self.logger.error("Failed to synthesize consensus: %s", e)
            return f"Synthesis error: {e}"

    async def _run_agent(self, agent: SwarmAgent, prompt: str, callback: Optional[Callable]):
        try:
            brain = self.orchestrator.cognitive_engine
            
            # Specialized system prompt insertion
            role_prompt = self.agent_roles.get(agent.specialty.lower(), f"You are an expert in {agent.specialty}.")
            swarm_context = f"[SWARM PROTOCOL: {role_prompt} Focus exclusively on your specialized perspective.]\n"
            
            # Sub-agents use fast mode to prevent endless latency
            res = await brain.think(swarm_context + prompt, mode="fast")
            agent.result = res.content
            agent.status = "COMPLETED"
            
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(agent_id=agent.id, result=agent.result)
                else:
                    callback(agent_id=agent.id, result=agent.result)
            
            self.logger.info("✅ Swarm Agent %s completed task.", agent.id)
            
        except Exception as e:
            self.logger.error("❌ Swarm Agent %s failed: %s", agent.id, e)
            agent.status = "FAILED"
            agent.result = str(e)
        finally:
            # We keep it in active_agents for a short time to allow result retrieval
            await asyncio.sleep(120)  # Extended for Swarm 2.0 multi-agent waits
            if agent.id in self.active_agents:
                del self.active_agents[agent.id]

    async def join_all(self, timeout: float = 30.0):
        """Waits for all active agents to complete."""
        start = time.time()
        while self.active_agents and (time.time() - start < timeout):
            await asyncio.sleep(0.5)
        return len(self.active_agents) == 0

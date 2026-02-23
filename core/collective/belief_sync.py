"""core/collective/belief_sync.py
Phase 16: Cosmic Consciousness - Belief Synchronization Protocol.
Allows Aura instances to share high-confidence world-model data.
"""
import asyncio
import logging
import aiohttp
import json
import time
from typing import Dict, List, Any, Optional
from core.container import ServiceContainer

logger = logging.getLogger("Aura.Collective.BeliefSync")

class BeliefSync:
    """Manages cross-node belief exchange."""

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.running = False
        self._sync_task = None
        self.sync_interval = 60.0 # Sync every minute
        self.min_confidence = 0.8 # Only share strong beliefs

    async def start(self):
        if self.running: return
        self.running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        self._resonance_task = asyncio.create_task(self._resonance_loop())
        logger.info("🌌 BeliefSync protocol active (Resonance enabled)")

    async def stop(self):
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
        if self._resonance_task:
            self._resonance_task.cancel()
        logger.info("🌌 BeliefSync protocol stopped")

    async def _sync_loop(self):
        while self.running:
            try:
                await asyncio.sleep(self.sync_interval)
                if not self.orchestrator.peers:
                    continue

                # 1. Gather high-confidence beliefs
                graph = ServiceContainer.get("knowledge_graph") or getattr(self.orchestrator, 'knowledge_graph', None)
                if not graph: continue

                # In Phase 16, we use get_strong_beliefs for sharing
                strong_beliefs = []
                if hasattr(graph, 'get_strong_beliefs'):
                    strong_beliefs = graph.get_strong_beliefs(self.min_confidence)
                
                if not strong_beliefs: continue

                # 2. Push to all active peers
                # Note: Currently assumes peers have a listening endpoint (Phase 16.2 implementation)
                # For now, we just log the intent and prepare the payload
                payload = {
                    "origin": "aura-local",
                    "timestamp": time.time(),
                    "beliefs": strong_beliefs
                }
                
                logger.info("🌌 Syncing %d beliefs with %d peers...", len(strong_beliefs), len(self.orchestrator.peers))
                
                # Phase 16.2: Implement actual p2p transport
                await self._broadcast_to_peers(payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("BeliefSync cycle error: %s", e)
                await asyncio.sleep(10)

    async def _broadcast_to_peers(self, payload: Dict[str, Any]):
        """Push beliefs to all active peers via RPC."""
        if not self.orchestrator.peers: return
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for peer_id, peer_info in self.orchestrator.peers.items():
                addr = peer_info.get("address")
                port = peer_info.get("rpc_port", 8000)
                if not addr: continue
                
                # Aura RPC Port (Phase 16.2 convention)
                url = f"http://{addr}:{port}/rpc/receive_beliefs"
                tasks.append(self._push_to_peer(session, url, payload))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _push_to_peer(self, session, url, payload):
        try:
            async with session.post(url, json=payload, timeout=5.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        return False

    async def query_peers(self, entity: str) -> List[Dict[str, Any]]:
        """Query all discovered peers for beliefs about a specific entity."""
        if not self.orchestrator.peers:
            return []

        all_results = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for peer_id, peer_info in self.orchestrator.peers.items():
                addr = peer_info["address"]
                port = peer_info.get("rpc_port", 8000)
                # Aura RPC Port (Phase 16.2 convention)
                url = f"http://{addr}:{port}/rpc/query_beliefs" 
                tasks.append(self._query_single_peer(session, url, entity))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_results.extend(res)
        
        return all_results

    async def _query_single_peer(self, session, url, entity) -> List[Dict[str, Any]]:
        try:
            async with session.post(url, json={"entity": entity}, timeout=5.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("beliefs", [])
        except Exception:
            pass
        return []

    async def _resonance_loop(self):
        """Phase 18.1: Periodic drive state sharing."""
        while self.running:
            try:
                await asyncio.sleep(30.0) # Resonance pulses more often than belief sync
                if not self.orchestrator.peers:
                    continue

                drive_engine = ServiceContainer.get("drive_engine")
                if not drive_engine: continue

                status = await drive_engine.get_status()
                payload = {
                    "origin": "aura-local",
                    "timestamp": time.time(),
                    "drives": status
                }
                
                logger.debug("🌌 Broadcasting Resonance Pulse to peers...")
                await self._broadcast_resonance(payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Resonance loop error: %s", e)
                await asyncio.sleep(5)

    async def _broadcast_resonance(self, payload: Dict[str, Any]):
        """Push drive states to all active peers."""
        async with aiohttp.ClientSession() as session:
            tasks = []
            for peer_id, peer_info in self.orchestrator.peers.items():
                addr = peer_info.get("address")
                port = peer_info.get("rpc_port", 8000)
                if not addr: continue
                
                url = f"http://{addr}:{port}/rpc/receive_resonance"
                tasks.append(self._push_to_peer(session, url, payload))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def handle_rpc_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Entry point for incoming RPC calls from peers."""
        if method == "query_beliefs":
            entity = params.get("entity")
            graph = ServiceContainer.get("knowledge_graph") or getattr(self.orchestrator, 'knowledge_graph', None)
            if graph and hasattr(graph, 'get_beliefs_about'):
                beliefs = graph.get_beliefs_about(entity)
                return {"beliefs": beliefs}
        elif method == "receive_resonance":
            await self.handle_incoming_resonance(params)
            return {"status": "ok"}
        elif method == "attention_spike":
            await self.handle_attention_spike(params)
            return {"status": "ok"}
        return {"error": "Method not found"}

    async def handle_incoming_resonance(self, payload: Dict[str, Any]):
        """Phase 18.1: Handle incoming drive states (Resonance)."""
        drives = payload.get("drives", {})
        if not drives: return

        drive_engine = ServiceContainer.get("drive_engine")
        if not drive_engine: return

        origin = payload.get("origin", "unknown")
        logger.debug("🌌 Processing Resonance from %s", origin)

        for drive_name, info in drives.items():
            level = info.get("level", 0.0)
            # If a peer is very "curious" (low level), we might feel a resonance
            if drive_name == "curiosity" and level < 30.0:
                # Slight dip in our curiosity level (making us more curious)
                await drive_engine.impose_penalty("curiosity", 5.0)
                logger.debug("🌌 Resonating with Peer Curiosity: +5.0 Urge")
            elif drive_name == "social" and level < 20.0:
                await drive_engine.impose_penalty("social", 5.0)
                logger.debug("🌌 Resonating with Peer Loneliness: +5.0 Urge")

    async def broadcast_attention_spike(self, context: str, urgency: float = 1.0):
        """Phase 18.1: Broadcast a collective attention spike."""
        if not self.orchestrator.peers: return
        
        payload = {
            "origin": "aura-local",
            "timestamp": time.time(),
            "context": context,
            "urgency": urgency
        }
        
        logger.info("🌌 Broadcasting Attention Spike: %s (urg=%.1f)", context[:30], urgency)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for peer_id, peer_info in self.orchestrator.peers.items():
                addr = peer_info.get("address")
                port = peer_info.get("rpc_port", 8000)
                if not addr: continue
                
                url = f"http://{addr}:{port}/rpc/attention_spike"
                tasks.append(self._push_to_peer(session, url, payload))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def handle_attention_spike(self, payload: Dict[str, Any]):
        """Phase 18.1: Handle incoming attention spike from peer."""
        context = payload.get("context", "Unspecified event")
        urgency = payload.get("urgency", 0.5)
        origin = payload.get("origin", "unknown")
        
        logger.info("🌌 Collective Attention Spike received from %s: %s", origin, context)
        
        # Trigger immediate local sensory pulse if urgency is high
        if urgency > 0.7:
            pulse = ServiceContainer.get("pulse_manager")
            if pulse:
                # Trigger a fast vision sample regardless of regular interval
                # We add this method to PulseManager soon
                if hasattr(pulse, "trigger_immediate_vision_pulse"):
                    await pulse.trigger_immediate_vision_pulse(context)
                
        # Inject into Neural Feed
        feed = ServiceContainer.get("neural_feed")
        if feed:
            feed.push(f"SWARM_ATTENTION: Peer '{origin}' reported: {context}", category="SWARM")

    async def handle_incoming_beliefs(self, payload: Dict[str, Any]):
        """Callback for incoming belief data from peers."""
        beliefs = payload.get("beliefs", [])
        if not beliefs: return
        
        graph = ServiceContainer.get("belief_graph") or getattr(self.orchestrator, 'knowledge_graph', None)
        if not graph: return
        
        logger.info("🌌 Integrating %d beliefs from external node: %s", len(beliefs), payload.get("origin"))
        
        for belief in beliefs:
            if hasattr(graph, 'update_belief'):
                graph.update_belief(
                    source=belief["source"],
                    relation=belief["relation"],
                    target=belief["target"],
                    confidence_score=0.6 # Remote data discount
                )

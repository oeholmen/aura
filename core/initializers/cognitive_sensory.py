"""Cognitive sensory layer initialization.

Registers sensory subsystems (vision, hearing, continuous perception)
into the service container for use by the cognitive pipeline.
"""
import logging

logger = logging.getLogger("Aura.Init.CognitiveSensory")


def init_cognitive_sensory_layer(container):
    """Register sensory subsystems in the service container."""
    try:
        from core.sensory_integration import get_sensory_system
        sensory = get_sensory_system()
        if sensory is not None:
            container.register_instance("sensory_system", sensory, required=False)
            logger.debug("Sensory system registered.")
    except Exception as e:
        logger.debug("Sensory system init deferred: %s", e)

    try:
        from core.senses.continuous_vision import ContinuousSensoryBuffer
        from core.config import config
        buffer = ContinuousSensoryBuffer(data_dir=getattr(config.paths, "data_dir", None))
        container.register_instance("continuous_vision", buffer, required=False)
        logger.debug("Continuous vision buffer registered.")
    except Exception as e:
        logger.debug("Continuous vision init deferred: %s", e)

    # Code graph — Aura's self-knowledge of her own codebase
    try:
        from core.introspection.code_graph import get_code_graph
        import asyncio
        graph = get_code_graph()
        container.register_instance("code_graph", graph, required=False)
        # Build incrementally in background (don't block boot)
        asyncio.create_task(_build_code_graph_background(graph))
        logger.info("Code graph registered (building in background).")
    except Exception as e:
        logger.debug("Code graph init deferred: %s", e)


async def _build_code_graph_background(graph):
    """Build the code graph without blocking boot."""
    import logging
    _logger = logging.getLogger("Aura.Init.CodeGraph")
    try:
        await asyncio.sleep(10)  # Let critical subsystems boot first
        stats = await graph.build(incremental=True)
        _logger.info("Code graph ready: %d files, %d symbols, %d relationships (%.1fs)",
                     stats["files"], stats["symbols"], stats["relationships"], stats.get("build_time_s", 0))
    except Exception as e:
        _logger.warning("Code graph background build failed: %s", e)

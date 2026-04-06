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

# core/app_context.py
from dataclasses import dataclass
from typing import Any, Optional

# Forward references to avoid circular imports during type checking at runtime
# In a real scenario, use actual types or Protocol definitions

@dataclass
class AppContext:
    """Singleton-like container for long-lived application services.
    Injected into components (Orchestrator, API) to provide access to shared infrastructure.
    """

    input_bus: Any # InputBus
    process_manager: Any # ProcessManager
    memory: Any # MemoryStoreV2
    
    # Optional shared resources
    config: Optional[dict] = None
    logger: Optional[Any] = None

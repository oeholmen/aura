"""core/container.py
Robust DI Container with lifecycle hooks.

H-09 FIX: Lock is released BEFORE factory execution to prevent blocking
all service resolution during slow initializations.
H-11 FIX: All logger calls use consistent %s formatting (no f-string mixing).
"""

import asyncio
import inspect
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union, cast

logger = logging.getLogger("Aura.Container")


class ServiceLifetime(Enum):
    """Service lifetime management"""

    SINGLETON = "singleton"
    TRANSIENT = "transient"


@dataclass
class ServiceDescriptor:
    """Describes how to create and manage a service"""

    name: str
    factory: Callable
    lifetime: ServiceLifetime = ServiceLifetime.SINGLETON
    instance: Any = None
    dependencies: List[str] = field(default_factory=list)
    package_dependencies: List[str] = field(default_factory=list)
    required: bool = True
    initialized: bool = False


class ServiceContainer:
    """Robust DI Container with Eager Wake and Lifecycle Hooks.

    H-09 FIX: Lock released before factory execution to prevent
    blocking all resolution during slow service init.
    """

    _instance = None
    _lock = threading.RLock()
    _wake_lock = None
    _resolving = threading.local()
    _start_time: Optional[float] = None

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                logger.debug(
                    "ServiceContainer initialized NEW instance in pid %s",
                    os.getpid(),
                )
                inst = super(ServiceContainer, cls).__new__(cls)
                inst._services: Dict[str, ServiceDescriptor] = {}
                inst._package_cache: Dict[str, bool] = {}
                cls._instance = inst
            return cls._instance

    @classmethod
    def _get_resolving_set(cls) -> Set[str]:
        try:
            return cls._resolving.resolving_set
        except AttributeError:
            cls._resolving.resolving_set = set()
            return cls._resolving.resolving_set

    @classmethod
    def register(
        cls,
        name: str,
        factory: Callable,
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
        dependencies: Optional[List[str]] = None,
        required: bool = True,
    ):
        """Register a service with the container."""
        with cls._lock:
            if cls._instance is None:
                logger.debug(
                    "ServiceContainer implicit init via register(%s)", name
                )
                cls()

            cls._instance._services[name] = ServiceDescriptor(
                name=name,
                factory=factory,
                lifetime=lifetime,
                dependencies=dependencies or [],
                required=required,
            )
            logger.debug("Registered service: %s [%s]", name, lifetime.value)

    @classmethod
    def register_instance(cls, name: str, instance: Any, required: bool = True):
        """Register a pre-built instance as a singleton service."""
        with cls._lock:
            if cls._instance is None:
                logger.debug(
                    "ServiceContainer implicit init via register_instance(%s)",
                    name,
                )
                cls()

            cls._instance._services[name] = ServiceDescriptor(
                name=name,
                factory=lambda: instance,
                lifetime=ServiceLifetime.SINGLETON,
                instance=instance,
                required=required,
                initialized=True,
            )
            logger.debug("Registered instance: %s", name)

    @classmethod
    def check_package(cls, package_name: str) -> bool:
        """Unified dependency check."""
        inst = cls()
        if package_name in inst._package_cache:
            return inst._package_cache[package_name]

        import importlib

        try:
            importlib.import_module(package_name)
            inst._package_cache[package_name] = True
            return True
        except ImportError:
            inst._package_cache[package_name] = False
            return False

    @classmethod
    def reload_service(cls, name: str) -> bool:
        """Phase 21 HOT-SWAPPING (Neuroplasticity):
        Forces a service to be purged from the container so it can be re-initialized.
        If it has an on_stop_async hook, it will be executed synchronously via an event loop wrapper.
        """
        inst = cls()
        with cls._lock:
            if name not in inst._services:
                logger.warning("Cannot reload unregistered service: %s", name)
                return False
            
            descriptor = inst._services[name]
            instance = descriptor.instance
            
            if instance:
                logger.info("🧠 Hot-swapping service: %s", name)
                # Cleanup existing instance
                for hook in ("on_stop", "cleanup"):
                    if hasattr(instance, hook):
                        try:
                            getattr(instance, hook)()
                        except Exception as e:
                            logger.error("Reload cleanup error for %s.%s: %s", name, hook, e)
                
                descriptor.instance = None
                descriptor.initialized = False
            return True

    @classmethod
    def get(cls, name: str, default: Any = "_SENTINEL") -> Any:
        """Resolve a service, including its dependency tree.

        H-09 FIX: Lock is only held for dict lookups, NOT during factory
        execution. This prevents a slow factory from blocking all resolution.
        """
        inst = cls()

        # Phase 1: Lookup under lock
        with cls._lock:
            if name not in inst._services:
                if default != "_SENTINEL":
                    return default
                raise KeyError(
                    f"Service '{name}' not found. "
                    f"Available: {list(inst._services.keys())}"
                )

            descriptor = inst._services[name]

            # Check package requirements
            for pkg in descriptor.package_dependencies:
                if not cls.check_package(pkg):
                    logger.warning(
                        "Service '%s' missing package dependency: %s", name, pkg
                    )
                    if not descriptor.required:
                        return default
                    raise ImportError(
                        f"Service '{name}' requires missing package: {pkg}"
                    )

            # Fast path: singleton already created
            if (
                descriptor.lifetime == ServiceLifetime.SINGLETON
                and descriptor.instance is not None
            ):
                return descriptor.instance

        # Phase 2: Build outside lock (prevents blocking all resolution)
        resolving = cls._get_resolving_set()
        if name in resolving:
            raise RuntimeError(
                f"Circular dependency: {' -> '.join(list(resolving) + [name])}"
            )

        resolving.add(name)
        try:
            # 1. Resolve dependencies
            deps = {}
            for dep in descriptor.dependencies:
                deps[dep] = cls.get(dep)

            # 2. Instantiate
            instance = descriptor.factory(**deps) if deps else descriptor.factory()

            # 3. Lifecycle on_start (synchronous)
            if hasattr(instance, "on_start") and not descriptor.initialized:
                try:
                    instance.on_start()
                except Exception as e:
                    logger.error("on_start failed for %s: %s", name, e)

            # Phase 3: Store result under lock
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                with cls._lock:
                    descriptor.instance = instance
                    descriptor.initialized = True

            return instance
        finally:
            resolving.discard(name)

    @classmethod
    async def wake(cls) -> List[str]:
        """EAGER WAKE: Instantiate and start all 'required' services."""
        if cls._wake_lock is None:
            cls._wake_lock = asyncio.Lock()
        async with cls._wake_lock:
            errors = []
            to_wake: List[str] = []

            with cls._lock:
                to_wake = [
                    n for n, d in cls._instance._services.items() if d.required
                ]

            cls._start_time = time.time()

            for name in to_wake:
                try:
                    instance = cls.get(name)
                    if hasattr(instance, "on_start_async"):
                        await instance.on_start_async()
                    logger.info("   [✓] %s online.", name)
                except Exception as e:
                    logger.critical("   [!] %s FAILED: %s", name, e)
                    errors.append(f"{name}: {e}")

            if errors:
                raise RuntimeError(f"Core Wake Failed: {', '.join(errors)}")

            return to_wake

    @classmethod
    def clear(cls) -> None:
        """Reset the container state. Used primarily for testing."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._services = {}
            cls._resolving = threading.local()
            cls._instance = None
            cls._start_time = None

    @classmethod
    def validate(cls) -> tuple[bool, List[str]]:
        """Check if all registered services can have their dependencies satisfied."""
        errors = []
        inst = cls._instance
        if inst is None:
            return True, []
        with cls._lock:
            for name, descriptor in inst._services.items():
                for dep in descriptor.dependencies:
                    if dep not in inst._services:
                        errors.append(
                            f"Service '{name}' depends on unregistered service '{dep}'"
                        )

        return len(errors) == 0, errors

    @classmethod
    async def shutdown(cls) -> None:
        """Cleanup all singleton services in reverse order."""
        inst = cls._instance
        if inst is None:
            return
        with cls._lock:
            names: List[str] = list(inst._services.keys())
            names.reverse()
            services_snapshot = {n: inst._services.get(n) for n in names}

        for name, descriptor in services_snapshot.items():
            if not descriptor:
                continue

            if descriptor.instance:
                instance = descriptor.instance
                if hasattr(instance, "on_stop_async"):
                    try:
                        res = instance.on_stop_async()
                        if asyncio.iscoroutine(res) or inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.error("on_stop_async %s error: %s", name, e)

                for hook in ("on_stop", "cleanup"):
                    if hasattr(instance, hook):
                        try:
                            getattr(instance, hook)()
                        except Exception as e:
                            logger.error("%s %s error: %s", hook, name, e)

                descriptor.instance = None
                descriptor.initialized = False

        logger.info("Service Container shutdown complete.")

    @classmethod
    def get_health_report(cls) -> Dict[str, Any]:
        inst = cls._instance
        if inst is None:
            return {"status": "offline", "services": {}}
        with cls._lock:
            services_report: Dict[str, Any] = {}
            report: Dict[str, Any] = {
                "status": "operational",
                "services": services_report,
            }
            if cls._start_time:
                report["uptime_seconds"] = round(
                    time.time() - cls._start_time, 1
                )
            for name, d in inst._services.items():
                services_report[name] = {
                    "status": "online" if d.instance is not None else "offline",
                    "required": d.required,
                    "initialized": d.initialized,
                }
                if d.required and not d.instance:
                    report["status"] = "degraded"
            return report


def get_container() -> Type[ServiceContainer]:
    return ServiceContainer

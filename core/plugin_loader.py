"""core/plugin_loader.py
Safe dynamic loading mechanism for agent skills.
Replaces insecure 'Genetic Mutation' self-modification.
"""
import importlib.util
import logging
import os
import sys
from typing import Any, Dict

logger = logging.getLogger("Aura.PluginLoader")

class PluginManager:
    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = plugin_dir
        # Ensure path is absolute if needed, or relative to cwd
        if not os.path.isabs(plugin_dir):
            self.plugin_dir = os.path.abspath(f"autonomy_engine/{plugin_dir}")
            
        os.makedirs(self.plugin_dir, exist_ok=True)
        self.loaded_plugins: Dict[str, Any] = {}

    def validate_plugin(self, file_path: str) -> bool:
        """Static analysis of plugin code before loading.
        Rejects usage of 'eval', 'exec', 'subprocess' in plugins.
        """
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if "import subprocess" in content or "exec(" in content or "eval(" in content:
                    logger.warning("Plugin %s rejected due to unsafe patterns.", file_path)
                    return False
        except Exception as e:
            logger.error("Validation failed for %s: %s", file_path, e)
            return False
        return True

    def load_plugin(self, plugin_name: str) -> bool:
        """Dynamically loads a module from the plugins directory.
        """
        file_path = os.path.join(self.plugin_dir, f"{plugin_name}.py")
        if not os.path.exists(file_path):
            logger.warning("Plugin file not found: %s", file_path)
            return False
            
        if not self.validate_plugin(file_path):
            return False

        try:
            spec = importlib.util.spec_from_file_location(plugin_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[plugin_name] = module
                spec.loader.exec_module(module)
                self.loaded_plugins[plugin_name] = module
                logger.info("Plugin %s loaded successfully.", plugin_name)
                return True
        except Exception as e:
            logger.error("Failed to load plugin %s: %s", plugin_name, e)
            return False
        return False

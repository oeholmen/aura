"""infrastructure/operations.py - Core Aura operations.
"""
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .hardening import CircuitBreaker

logger = logging.getLogger("Infra.Operations")

class DepOps:
    @staticmethod
    def check_and_install() -> None:
        """Real dependency check and installation."""
        REQUIRED_PACKAGES = [
            "pydantic", 
            "pydantic-settings", 
            "psutil", 
            "sounddevice", 
            "numpy",
            "setproctitle",
            "cryptography",
            "requests",
            "beautifulsoup4"
        ]
        
        logger.info("Verifying dependencies...")
        installed = []
        missing = []
        
        try:
            import pkg_resources
            installed_packages = [d.project_name.lower() for d in pkg_resources.working_set]
            
            for pkg in REQUIRED_PACKAGES:
                if pkg.lower() in installed_packages:
                    installed.append(pkg)
                else:
                    missing.append(pkg)
        except Exception as e:
            logger.warning("Dependency check failed: %s. Assuming missing.", e)
            missing = REQUIRED_PACKAGES

        if missing:
            logger.info("Installing missing dependencies: %s", ', '.join(missing))
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
                logger.info("Dependencies installed successfully.")
            except subprocess.CalledProcessError as e:
                logger.error("Failed to install dependencies: %s", e)
        else:
            logger.info("All dependencies satisfied.")

class WebOps:
    @staticmethod
    async def fetch_page_text(url: str, timeout: int = 10) -> Optional[str]:
        """Real web fetch using requests, non-blocking."""
        import requests
        loop = asyncio.get_running_loop()
        
        def _sync_fetch():
            headers = {'User-Agent': 'Aura/3.5 (Sovereign)'}
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text

        try:
            return await loop.run_in_executor(None, _sync_fetch)
        except Exception as e:
            logger.error("WebOps Fetch Error: %s", e)
            return None

class FileOps:
    @staticmethod
    def timestomp(filepath: Path) -> None:
        """Anti-Forensics: Resets file modification time to a fixed past date."""
        fake_time = 1704110400 
        try:
           os.utime(filepath, (fake_time, fake_time))
        except Exception as e:
           logger.warning("Failed to timestomp %s: %s", filepath, e)

    @staticmethod
    def load_file(path: str) -> str:
        """Safely loads a file, returning empty string on failure."""
        if not os.path.exists(path):
            return ""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error("File load error for %s: %s", path, e)
            return ""

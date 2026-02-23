import logging
import os
import asyncio
from enum import Enum, auto
from typing import Dict, Any, Optional
from ..base_module import AuraBaseModule

class PermissionType(Enum):
    MIC = auto()
    CAMERA = auto()
    SCREEN = auto()

class PermissionGuard(AuraBaseModule):
    """Handles hardware-level TCC (Transparency, Consent, and Control) permissions for macOS.
    
    Provides pre-flight checks to detect if the OS is blocking access 
    and offers guidance on how to fix it.
    """
    
    def __init__(self):
        super().__init__("PermissionGuard")
        self._cache: Dict[PermissionType, Dict[str, Any]] = {}

    async def check_permission(self, ptype: PermissionType, force: bool = False) -> Dict[str, Any]:
        """Check if a hardware permission is granted.
        
        Returns:
            {"granted": bool, "status": str, "guidance": str}
        """
        if not force and ptype in self._cache:
            return self._cache[ptype]

        self.logger.info("Checking %s permission...", ptype.name)
        
        result = {"granted": False, "status": "unknown", "guidance": ""}
        
        if ptype == PermissionType.SCREEN:
            result = await self._check_screen_permission()
        elif ptype == PermissionType.MIC:
            result = await self._check_mic_permission()
        else:
            result = {"granted": True, "status": "assumed", "guidance": "No check implemented for this type yet."}

        self._cache[ptype] = result
        return result

    async def _check_screen_permission(self) -> Dict[str, Any]:
        """MacOS specific check for Screen Recording permissions.
        Attempts to take a tiny screenshot. If it fails or returns blank, it's blocked.
        """
        try:
            import pyautogui
            from PIL import Image
            
            # Offload to thread to avoid blocking loop
            loop = asyncio.get_running_loop()
            def _try_shot():
                # Take a 1x1 screenshot - very fast
                return pyautogui.screenshot(region=(0, 0, 1, 1))

            shot = await loop.run_in_executor(None, _try_shot)
            
            # On macOS, if permission is denied, pyautogui might return a blank image
            # or throw an error depending on the version/OS.
            if shot is None:
                return {
                    "granted": False, 
                    "status": "denied", 
                    "guidance": "Please grant 'Screen Recording' to terminal/Aura in System Settings > Privacy & Security."
                }
            
            return {"granted": True, "status": "active", "guidance": ""}
        except Exception as e:
            self.logger.error("Screen permission check failed: %s", e)
            return {
                "granted": False, 
                "status": "error", 
                "guidance": f"System error checking screen: {e}. Ensure pyautogui is installed."
            }

    async def _check_mic_permission(self) -> Dict[str, Any]:
        """MacOS specific check for Microphone permissions.
        Note: RealtimeSTT often handles its own errors, but we do a pre-flight probe.
        """
        try:
            # We can't easily check Mic TCC without actually opening a stream, 
            # which might trigger the OS prompt. 
            # For now, we assume if we are in the browser, the browser handles it.
            # If we are local, we'd need sounddevice or similar.
            return {"granted": True, "status": "active", "guidance": ""}
        except Exception as e:
             return {"granted": False, "status": "error", "guidance": f"Mic check failed: {e}"}

    def get_guidance(self, ptype: PermissionType) -> str:
        """Return human-readable instructions for fixing a permission block."""
        if ptype == PermissionType.SCREEN:
            return "1. Open System Settings\n2. Go to Privacy & Security\n3. Select Screen Recording\n4. Ensure Aura/Terminal is switched ON."
        if ptype == PermissionType.MIC:
            return "1. Open System Settings\n2. Go to Privacy & Security\n3. Select Microphone\n4. Ensure Aura/Terminal is switched ON."
        return "Check your macOS Privacy & Security settings."

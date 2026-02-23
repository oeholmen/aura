"""Aura Voice Skill (Sovereign)
Enables Aura to speak using local engines only.
"""
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.Voice")

class VoiceSkill(BaseSkill):
    name = "speak"
    description = "Convert text to audible speech using local system voices."
    
    def __init__(self):
        self._voice_engine = None
        self._fallback_engine = None
        if sys.platform != "darwin":
            try:
                import pyttsx3
                self._fallback_engine = pyttsx3.init()
                self._fallback_engine.setProperty('rate', 175) 
            except Exception as e:
                logger.warning("pyttsx3 init failed: %s", e)
            
    def _get_engine(self):
        """Resolve voice engine from ServiceContainer."""
        if self._voice_engine is None:
            try:
                from core.container import ServiceContainer
                self._voice_engine = ServiceContainer.get("voice_engine")
            except Exception as e:
                logger.error("Failed to resolve voice_engine: %s", e)
        return self._voice_engine

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        text = goal.get("params", {}).get("text") or goal.get("objective", "")
        
        if not isinstance(text, str):
            text = str(text)
            
        if not text:
            return {"ok": False, "error": "No text provided to speak."}
            
        logger.info("🔊 Speaking: %s...", text[:50])
        
        # Strategy 1: Sovereign Voice Engine (Premium/Standard)
        engine = self._get_engine()
        if engine:
            try:
                await engine.synthesize_speech(text)
                return {"ok": True, "mode": "sovereign", "message": "Spoken via Sovereign Voice Engine."}
            except Exception as e:
                logger.error("Sovereign synthesis failed: %s", e)

        # Strategy 2: macOS 'say' (High Quality Fallback)
        if sys.platform == "darwin":
            try:
                # Use Samantha for the cool, collected AGI persona
                await asyncio.create_subprocess_exec("say", "-v", "Samantha", "-r", "185", text)
                return {"ok": True, "mode": "macos_say", "message": "Spoken via macOS (Samantha)."}
            except Exception as e:
                logger.error("macOS say failed: %s", e)

        # Strategy 3: Local pyttsx3 (Generic Fallback)
        if self._fallback_engine:
            try:
                self._fallback_engine.say(text)
                self._fallback_engine.runAndWait()
                return {"ok": True, "mode": "pyttsx3", "message": "Spoken via local engine."}
            except Exception as e:
                logger.error("pyttsx3 failed: %s", e)
        
        return {"ok": False, "error": "No voice engine available."}

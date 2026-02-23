"""Sovereign Ears: Auditory Perception System
------------------------------------------
Handles audio input, Voice Activity Detection (VAD), and Transcription.
Now unified to wrap around SovereignVoiceEngine for reliability.
"""

import logging
from pathlib import Path
from typing import Callable, Optional

from .voice_engine import VoiceState, get_voice_engine

logger = logging.getLogger("Aura.Senses.Ears")

class SovereignEars:
    """Wrapper for the SovereignVoiceEngine to provide a consistent 'Ears' interface
    across the orchestrator.
    """

    def __init__(self, engine=None):
        if engine:
            self._engine = engine
        else:
            from ..container import ServiceContainer
            self._engine = ServiceContainer.get("voice_engine")
        
        logger.info("👂 SovereignEars linked to VoiceEngine via DI")

    @property
    def model(self):
        """Access the underlying STT model if loaded."""
        return self._engine._whisper_model

    def start_listening(self, callback: Callable[[str], None]):
        """Starts the audio capture and transcription loop via the VoiceEngine.
        Note: VoiceEngine is normally driven by the server's audio chunk stream.
        """
        # Register the callback with the voice engine
        async def _async_callback(text: str):
            callback(text)
            
        self._engine.on_transcript(_async_callback)
        logger.info("👂 Ears listening (via VoiceEngine pipeline)")

    def stop_listening(self):
        """Stop the listening process."""
        self._engine.reset()
        logger.info("Ears closed.")

    def transcribe(self, audio_source) -> str:
        """Transcribe audio from a file path or array using the VoiceEngine's model.
        This is a synchronous wrapper for the engine's STT.
        """
        # Ensure models are loaded
        self._engine.ensure_models()
        
        # If it's a file path, we need to load it
        import io
        import wave
        
        if isinstance(audio_source, (str, Path)):
            with open(audio_source, 'rb') as f:
                audio_data = f.read()
        else:
            audio_data = audio_source

        # Convert to WAV buffer for the engine's internal transcribe
        # simpler to just access the model directly for sync calls
        if self._engine._whisper_model:
            segments, _ = self._engine._whisper_model.transcribe(
                audio_source,
                language="en",
                beam_size=5
            )
            return " ".join([seg.text for seg in segments]).strip()
        
        return ""

    def mock_hear(self, text: str):
        """Inject text as if heard (for testing)."""
        if self._engine._on_transcript:
            import asyncio
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()

                if loop.is_running():
                    loop.create_task(self._engine._on_transcript(text))
                else:
                    try:
                        asyncio.run(self._engine._on_transcript(text))
                    except RuntimeError:
                         # Still fallback for edge cases
                         logger.error("Could not run transcript handler: loop running elsewhere?")

            except Exception as e:
                logger.error("Mock hear failed: %s", e)

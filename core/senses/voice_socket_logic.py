import asyncio
import logging
from typing import List, Optional

import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger("Aura.VoiceProcessor")

# Global singleton for Whisper to prevent RAM churn across connections
_WHISPER_MODEL_CACHE = {}

def get_whisper_model(model_name="tiny"):
    if model_name not in _WHISPER_MODEL_CACHE:
        if WhisperModel:
            try:
                logger.info("🎙️ Loading Whisper STT (%s)...", model_name)
                _WHISPER_MODEL_CACHE[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
            except Exception as e:
                logger.error("Failed to load Whisper: %s", e)
                return None
    return _WHISPER_MODEL_CACHE.get(model_name)

class VoiceStreamProcessor:
    """Stateful audio processor for Advanced Voice Mode.
    Handles VAD logic and local STT.
    """

    def __init__(self, model_name="tiny", model_instance=None):
        self.vad = None
        
        self.sample_rate = 16000
        self.frame_duration_ms = 20
        self.bytes_per_frame = int(self.sample_rate * (self.frame_duration_ms / 1000) * 2)
        self.buffer = b""
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
        self.max_silence = 25 # ~500ms

        # STT Model (Local)
        if model_instance:
            self.model = model_instance
        else:
            self.model = get_whisper_model(model_name)

    def add_audio(self, chunk: bytes):
        self.buffer += chunk

    def is_speech_finished(self) -> bool:
        """Processes buffer and returns True if a complete utterance is detected."""
        while len(self.buffer) >= self.bytes_per_frame:
            frame = self.buffer[:self.bytes_per_frame]
            self.buffer = self.buffer[self.bytes_per_frame:]
            
            # VAD logic is now handled by energy-based detection in the frontend or this fallback
            # calculates RMS of the frame and compares against a threshold
            try:
                audio_np = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
                rms = np.sqrt(np.mean(audio_np**2))
                is_speech = rms > 300 # Threshold for local sensitivity
            except Exception:
                is_speech = False

            if is_speech:
                if not self.is_speaking:
                    logger.info("🎤 Speech detected...")
                self.is_speaking = True
                self.silence_frames = 0
                self.speech_buffer.append(frame)
            elif self.is_speaking:
                self.speech_buffer.append(frame)
                self.silence_frames += 1
                if self.silence_frames >= self.max_silence:
                    logger.info("🛑 End of speech detected.")
                    return True
        return False

    async def get_transcript(self) -> str:
        """Transcribes the captured speech buffer using local Whisper."""
        if not self.model or not self.speech_buffer:
            return ""
        
        try:
            audio_data = b"".join(self.speech_buffer)
            # Convert 16-bit PCM to float32 normalized
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Run transcription in a thread to keep the event loop alive
            def _sync_transcribe():
                segments, _ = self.model.transcribe(audio_np, beam_size=1)
                return "".join([s.text for s in segments]).strip()

            text = await asyncio.to_thread(_sync_transcribe)
            
            self.reset()
            return text
        except Exception as e:
            logger.error("Transcription error: %s", e)
            self.reset()
            return ""

    def reset(self):
        self.speech_buffer = []
        self.is_speaking = False
        self.silence_frames = 0
        self.buffer = b""

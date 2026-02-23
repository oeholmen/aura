"""Sovereign Voice Engine v2.0 — Aura's Real-time Ears & Mouth
100% local. No external APIs.

Pipeline: 
- STT: RealtimeSTT (Silero VAD + faster-whisper) -> Sub-second transcripts
- TTS: Piper (Instant) or XTTS-v2 (Cloned) -> Streaming audio chunks
- Barge-in: Interrupt TTS immediately on VAD detection
"""
import asyncio
import base64
import io
import json
import logging
import os
import time
import wave
from enum import Enum, auto
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Union

import numpy as np

logger = logging.getLogger("Aura.VoiceEngine")

class VoiceState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()

class SovereignVoiceEngine:
    def __init__(self, 
                 whisper_model: str = "base",
                 piper_voice: str = "en_US-amy-medium",
                 use_xtts: bool = False,
                 data_dir: Optional[str] = None):
        self.whisper_model_name = whisper_model
        self.piper_voice_name = piper_voice
        self.use_xtts = use_xtts
        from core.common.paths import DATA_DIR
        self.data_dir = Path(data_dir or (DATA_DIR / "voice_models"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # STT Internal
        self.recorder = None
        self._stt_initialized = False
        
        # TTS Internal
        self._piper_voice = None
        self._xtts_model = None
        self._tts_initialized = False
        
        # State
        self.state = VoiceState.IDLE
        self._barge_in_requested = False
        self._is_feeding = False

        self._models_loaded = False
        
        # Callbacks
        self._on_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        self._on_tts_audio: Optional[Callable[[bytes], Awaitable[None]]] = None
        self._on_state_change: Optional[Callable[[VoiceState], Awaitable[None]]] = None

        logger.info("🎙️ SovereignVoiceEngine v2.0 (RealtimeSTT) initialized")

    def ensure_models(self):
        """Lazy-load STT and TTS models."""
        if not self._stt_initialized:
            self._init_stt()
        if not self._tts_initialized:
            self._init_tts()

    def _init_stt(self):
        try:
            from RealtimeSTT import AudioToTextRecorder
            
            def _on_vad_start():
                try:
                    loop = asyncio.get_running_loop()
                    asyncio.run_coroutine_threadsafe(self._handle_vad_start(), loop)
                except RuntimeError:
                    pass  # No running event loop — VAD event during shutdown

            self.recorder = AudioToTextRecorder(
                model=self.whisper_model_name,
                language="en",
                spinner=False,
                input_device_index=None, # Crucial: we feed audio manually
                silero_sensitivity=0.4,
                post_speech_silence_duration=0.6,
                min_length_of_recording=0.4,
                on_vad_detect_start=_on_vad_start
            )
            self._stt_initialized = True
            logger.info("✓ RealtimeSTT (Whisper) initialized")
        except Exception as e:
            logger.error("Failed to init RealtimeSTT: %s", e)
            raise

    def _init_tts(self):
        try:
            if self.use_xtts:
                from TTS.api import TTS
                model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
                self._xtts_model = TTS(model_name, gpu=False) # CPU for reliability
                logger.info("✓ XTTS-v2 loaded")
            else:
                from piper import PiperVoice
                model_dir = self.data_dir / "piper_voices"
                model_dir.mkdir(parents=True, exist_ok=True)
                model_path = model_dir / f"{self.piper_voice_name}.onnx"
                config_path = model_dir / f"{self.piper_voice_name}.onnx.json"
                
                if not model_path.exists():
                     self._download_piper_voice(model_dir)
                
                self._piper_voice = PiperVoice.load(str(model_path), config_path=str(config_path))
                logger.info("✓ Piper Voice '%s' loaded", self.piper_voice_name)
            
            self._tts_initialized = True
            self._models_loaded = True
        except Exception as e:
            logger.error("Failed to init TTS: %s", e)
            raise

    def load_models(self):
        """Standard method for eager model loading."""
        self.ensure_models()

    @property
    def _whisper_model(self):
        """Compatibility property for things expecting the raw WhisperModel."""
        if self.recorder and hasattr(self.recorder, "model"):
            return self.recorder.model
        return None

    def _download_piper_voice(self, model_dir: Path):
        import urllib.request
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
        parts = self.piper_voice_name.split("-")
        lang_code = parts[0]
        lang = lang_code.split("_")[0]
        speaker = parts[1] if len(parts) > 1 else "default"
        quality = parts[2] if len(parts) > 2 else "medium"
        
        vpath = f"{lang}/{lang_code}/{speaker}/{quality}"
        for fname in [f"{self.piper_voice_name}.onnx", f"{self.piper_voice_name}.onnx.json"]:
            dest = model_dir / fname
            if not dest.exists():
                url = f"{base_url}/{vpath}/{fname}"
                logger.info("Downloading %s...", fname)
                try:
                    urllib.request.urlretrieve(url, str(dest))
                except Exception as e:
                    # Fallback to direct HF link if structure differs
                    alt_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{vpath}/{fname}"
                    urllib.request.urlretrieve(alt_url, str(dest))

    # ── Callbacks ──

    def on_transcript(self, callback: Callable[[str], Awaitable[None]]):
        self._on_transcript = callback

    def on_tts_audio(self, callback: Callable[[bytes], Awaitable[None]]):
        self._on_tts_audio = callback

    def on_state_change(self, callback: Callable[[VoiceState], Awaitable[None]]):
        self._on_state_change = callback

    async def _set_state(self, new_state: VoiceState):
        if self.state != new_state:
            self.state = new_state
            if self._on_state_change:
                await self._on_state_change(new_state)

    async def _handle_vad_start(self):
        """Triggered internally by RealtimeSTT when speech is detected."""
        if self.state == VoiceState.SPEAKING:
            self._barge_in_requested = True
            logger.info("🛑 Barge-in: Speech detected while Aura was speaking")
        await self._set_state(VoiceState.LISTENING)

    # ── Processing ──

    async def process_audio_chunk(self, pcm_data: bytes):
        """Accept raw 16kHz PCM from browser and feed to RealtimeSTT."""
        self.ensure_models()
        
        # Pre-flight Permission Check
        from core.container import ServiceContainer
        from core.security.permission_guard import PermissionType
        guard = ServiceContainer.get("permission_guard")
        if guard:
            check = await guard.check_permission(PermissionType.MIC)
            if not check["granted"]:
                logger.warning("🎙️ MIC Blocked: %s", check["guidance"])
                return # Stop processing if blocked

        if not self._is_feeding:
            self._is_feeding = True
            asyncio.create_task(self._stt_loop())

        # Feed the actual bytes to RealtimeSTT
        self.recorder.feed_audio(pcm_data)

    async def _stt_loop(self):
        """Background loop to pull transcripts from RealtimeSTT."""
        loop = asyncio.get_running_loop()
        while self._is_feeding:
            try:
                # recorder.text() blocks until silence/utterance complete
                text = await loop.run_in_executor(None, self.recorder.text)
                if text and text.strip():
                    logger.info("🎙️ STT Result: %s", text)
                    await self._set_state(VoiceState.PROCESSING)
                    if self._on_transcript:
                        await self._on_transcript(text.strip())
                await self._set_state(VoiceState.IDLE)
            except Exception as e:
                logger.error("STT Loop Error: %s", e)
                await asyncio.sleep(0.1)

    async def transcribe(self, audio_source: Union[str, Path, bytes, np.ndarray]) -> str:
        """Transcribe audio from various sources synchronously (runs in executor).
        """
        self.ensure_models()
        if not self._whisper_model:
            return ""

        loop = asyncio.get_running_loop()
        segments, _ = await loop.run_in_executor(
            None, 
            self._whisper_model.transcribe, 
            audio_source
        )
        return " ".join([seg.text for seg in segments]).strip()

    async def synthesize_speech(self, text: str):
        """Generate audio from text and stream via callback."""
        if not text or not text.strip():
            return

        self.ensure_models()
        self._barge_in_requested = False
        await self._set_state(VoiceState.SPEAKING)

        try:
            loop = asyncio.get_running_loop()
            
            if self.use_xtts:
                wav_data = await loop.run_in_executor(None, self._synthesize_xtts, text)
                await self._stream_audio_bytes(wav_data)
            else:
                await self._synthesize_piper_stream(text)

        except Exception as e:
            logger.error("TTS Synthesis failed: %s", e)
        finally:
            if not self._barge_in_requested:
                await self._set_state(VoiceState.IDLE)

    async def _synthesize_piper_stream(self, text: str):
        """Use Piper to synthesize and stream chunks."""
        def _get_audio():
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                self._piper_voice.synthesize(text, wf)
            return buf.getvalue()

        all_audio = await asyncio.get_running_loop().run_in_executor(None, _get_audio)
        await self._stream_audio_bytes(all_audio)

    def _synthesize_xtts(self, text: str) -> bytes:
        temp_wav = "temp_xtts.wav"
        # Reference voice if available, otherwise fallback
        ref_path = "aura_voice_ref.wav"
        if not os.path.exists(ref_path):
             # Create a dummy ref or use a sample from piper if available?
             # For now, XTTS requires a ref.
             logger.warning("XTTS: aura_voice_ref.wav not found! Please provide a voice sample.")
             return b''

        self._xtts_model.tts_to_file(
            text=text,
            file_path=temp_wav,
            speaker_wav=ref_path,
            language="en"
        )
        with open(temp_wav, "rb") as f:
            data = f.read()
        return data

    async def _stream_audio_bytes(self, audio_data: bytes):
        """Sends audio data in chunks, checking for barge-in."""
        if not self._on_tts_audio:
            return

        # Strip WAV header if present (we send raw PCM 16k)
        if audio_data.startswith(b'RIFF'):
            audio_data = audio_data[44:]
            
        chunk_size = 4096 # Standard buffer
        for i in range(0, len(audio_data), chunk_size):
            if self._barge_in_requested:
                logger.info("🛑 TTS Stream Cut: Barge-in acknowledged")
                break
            chunk = audio_data[i:i + chunk_size]
            await self._on_tts_audio(chunk)
            # Throttle slightly to simulate real-time playback delivery
            await asyncio.sleep(0.01)

    def request_barge_in(self):
        if self.state == VoiceState.SPEAKING:
            self._barge_in_requested = True

    def get_status(self) -> dict:
        return {
            "state": self.state.name,
            "stt": "RealtimeSTT",
            "tts": "XTTS-v2" if self.use_xtts else "Piper",
            "barge_in_detect": True
        }


# Singleton ──
_voice_engine: Optional[SovereignVoiceEngine] = None

def get_voice_engine(**kwargs) -> SovereignVoiceEngine:
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = SovereignVoiceEngine(**kwargs)
    return _voice_engine

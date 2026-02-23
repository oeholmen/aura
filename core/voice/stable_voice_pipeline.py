from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("Aura.VoicePipeline")


# ── States ────────────────────────────────────────────────────────────────────

class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"   # LLM thinking
    SPEAKING = "speaking"       # TTS output
    ERROR = "error"
    RECONNECTING = "reconnecting"


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class VoicePipelineConfig:
    # STT settings
    stt_model: str = "base"           # Whisper model size
    stt_language: str = "en"
    stt_silence_threshold_s: float = 1.2   # Silence before finalizing utterance
    stt_max_utterance_s: float = 30.0      # Max single utterance length
    stt_reconnect_delay_s: float = 2.0
    stt_max_reconnect_attempts: int = 5

    # TTS settings
    tts_speed: float = 1.0
    tts_voice: str = "default"
    tts_interrupt_on_user_speech: bool = True

    # Pipeline settings
    min_response_length: int = 3           # Words — don't speak responses shorter than this
    processing_timeout_s: float = 120.0    # Max wait for LLM response
    wake_word: Optional[str] = "aura"      # Set None to always listen
    push_to_talk_mode: bool = False


# ── Pipeline ──────────────────────────────────────────────────────────────────

class StableVoicePipeline:
    """
    Manages the full voice I/O loop with state machine, error recovery,
    and clean integration with the orchestrator.
    """

    def __init__(self, orchestrator, config: Optional[VoicePipelineConfig] = None):
        self._orch = orchestrator
        self._config = config or VoicePipelineConfig()
        self._state = VoiceState.IDLE
        self._running = False

        # Core components (lazy loaded)
        self._stt = None
        self._tts = None

        # State management
        self._current_tts_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0

        # Metrics
        self._utterances_processed = 0
        self._tts_interrupted = 0
        self._stt_errors = 0
        self._last_utterance_at = 0.0

        # Input queue — voice utterances waiting to be processed
        self._utterance_queue: asyncio.Queue = asyncio.Queue(maxsize=5)

        logger.info("StableVoicePipeline initialized")

    # ── Component Loading ─────────────────────────────────────────────────────

    async def _load_stt(self) -> bool:
        """Load STT engine with fallback options."""
        # Try RealtimeSTT first (existing engine)
        try:
            from core.senses.voice_engine import get_voice_engine
            self._stt = get_voice_engine()
            if self._stt:
                logger.info("STT: Using existing SovereignVoiceEngine")
                return True
        except Exception as exc:
            logger.warning("SovereignVoiceEngine unavailable: %s", exc)

        # Try faster-whisper directly
        try:
            from faster_whisper import WhisperModel
            self._stt = _WhisperWrapper(
                model_size=self._config.stt_model,
                language=self._config.stt_language,
            )
            logger.info("STT: Using faster-whisper directly")
            return True
        except ImportError:
            logger.warning("faster-whisper not installed")
        except Exception as exc:
            logger.error("faster-whisper init failed: %s", exc)

        logger.error("No STT engine available")
        return False

    async def _load_tts(self) -> bool:
        """Load TTS engine with fallback options."""
        # Try FastMouth first (existing engine)
        try:
            from core.senses.tts_stream import FastMouth
            self._tts = FastMouth()
            logger.info("TTS: Using FastMouth")
            return True
        except Exception as exc:
            logger.warning("FastMouth unavailable: %s", exc)

        # Try macOS 'say' command as fallback (works on Bryan's MacBook)
        try:
            import subprocess
            result = subprocess.run(["which", "say"], capture_output=True)
            if result.code == 0:
                self._tts = _MacOSSayWrapper()
                logger.info("TTS: Using macOS 'say' command as fallback")
                return True
        except Exception:
            pass

        logger.error("No TTS engine available")
        return False

    # ── STT Reconnection ──────────────────────────────────────────────────────

    async def _reconnect_stt(self) -> bool:
        """Attempt to reconnect STT with exponential backoff."""
        if self._reconnect_attempts >= self._config.stt_max_reconnect_attempts:
            logger.error("STT reconnection failed after %d attempts", self._reconnect_attempts)
            self._set_state(VoiceState.ERROR)
            return False

        self._set_state(VoiceState.RECONNECTING)
        delay = self._config.stt_reconnect_delay_s * (2 ** self._reconnect_attempts)
        delay = min(delay, 30.0)  # Cap at 30 seconds

        logger.info(
            "STT reconnecting in %.1fs (attempt %d/%d)",
            delay, self._reconnect_attempts + 1,
            self._config.stt_max_reconnect_attempts
        )

        await asyncio.sleep(delay)
        self._reconnect_attempts += 1

        success = await self._load_stt()
        if success:
            self._reconnect_attempts = 0
            self._set_state(VoiceState.IDLE)
            logger.info("STT reconnected successfully")
            return True
        return await self._reconnect_stt()

    # ── Main Loop ─────────────────────────────────────────────────────────────

    async def start(self):
        """Start the voice pipeline."""
        self._running = True

        stt_ok = await self._load_stt()
        tts_ok = await self._load_tts()

        if not stt_ok:
            logger.error("Voice pipeline cannot start — no STT engine")
            return
        if not tts_ok:
            logger.warning("Voice pipeline starting without TTS — text-only output")

        logger.info("Voice pipeline starting (wake_word=%s, ptt=%s)",
                    self._config.wake_word, self._config.push_to_talk_mode)

        # Start listener and processor as separate tasks
        await asyncio.gather(
            self._listen_loop(),
            self._process_loop(),
        )

    async def stop(self):
        """Stop the pipeline cleanly."""
        self._running = False
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        logger.info("Voice pipeline stopped")

    # ── Listen Loop ───────────────────────────────────────────────────────────

    async def _listen_loop(self):
        """
        Continuously listens for speech and puts utterances in the queue.
        Handles STT failures with reconnection.
        """
        logger.info("Voice listen loop started")
        while self._running:
            try:
                if self._state in (VoiceState.SPEAKING,):
                    # Don't capture while speaking unless interrupt is enabled
                    if not self._config.tts_interrupt_on_user_speech:
                        await asyncio.sleep(0.1)
                        continue

                self._set_state(VoiceState.LISTENING)
                utterance = await self._capture_utterance()

                if utterance:
                    utterance = utterance.strip()
                    if len(utterance.split()) < 1:
                        continue

                    # Wake word check
                    if self._config.wake_word:
                        if self._config.wake_word.lower() not in utterance.lower():
                            logger.debug("No wake word in: %r", utterance[:50])
                            continue
                        # Strip wake word from utterance
                        utterance = utterance.lower().replace(
                            self._config.wake_word.lower(), ""
                        ).strip()
                        if not utterance:
                            continue

                    # Interrupt TTS if speaking
                    if self._state == VoiceState.SPEAKING:
                        await self._interrupt_tts()

                    # Queue the utterance
                    try:
                        self._utterance_queue.put_nowait(utterance)
                        self._last_utterance_at = time.time()
                        logger.info("Utterance queued: %r", utterance[:80])
                    except asyncio.QueueFull:
                        # Drop oldest, add newest
                        try:
                            self._utterance_queue.get_nowait()
                            self._utterance_queue.put_nowait(utterance)
                        except Exception:
                            pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._stt_errors += 1
                logger.error("Listen loop error: %s", exc)
                await self._reconnect_stt()

    async def _capture_utterance(self) -> Optional[str]:
        """
        Capture a single utterance from the STT engine.
        Returns the transcribed text or None.
        """
        if not self._stt:
            await asyncio.sleep(1.0)
            return None

        try:
            # If STT has an async get method, use it
            if hasattr(self._stt, 'get_utterance'):
                return await asyncio.wait_for(
                    self._stt.get_utterance(),
                    timeout=self._config.stt_max_utterance_s
                )
            # If STT uses callbacks, poll a queue
            elif hasattr(self._stt, 'last_text'):
                await asyncio.sleep(0.1)
                text = getattr(self._stt, 'last_text', None)
                if text:
                    self._stt.last_text = None  # Clear it
                    return text
                return None
            # Fallback: run blocking transcription in thread
            elif hasattr(self._stt, 'transcribe'):
                return await asyncio.get_event_loop().run_in_executor(
                    None, self._stt.transcribe
                )
            else:
                await asyncio.sleep(0.5)
                return None
        except asyncio.TimeoutError:
            return None

    # ── Process Loop ──────────────────────────────────────────────────────────

    async def _process_loop(self):
        """
        Takes utterances from the queue, sends to LLM, speaks response.
        This is the critical path that must be reliable.
        """
        logger.info("Voice process loop started")
        while self._running:
            try:
                # Wait for an utterance
                try:
                    utterance = await asyncio.wait_for(
                        self._utterance_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._handle_utterance(utterance)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Process loop error: %s", exc)
                self._set_state(VoiceState.IDLE)

    async def _handle_utterance(self, utterance: str):
        """Process a single utterance through LLM and TTS."""
        self._utterances_processed += 1
        self._set_state(VoiceState.PROCESSING)

        logger.info("Processing utterance #%d: %r", self._utterances_processed, utterance[:80])

        try:
            # Interrupt any current autonomous thought
            await self._interrupt_autonomous_thought()

            # Send to orchestrator (this is the LLM call)
            response = await asyncio.wait_for(
                self._orch.process_user_input(utterance, origin="voice"),
                timeout=self._config.processing_timeout_s
            )

            if not response or not response.strip():
                logger.warning("Voice: Empty LLM response for utterance %r", utterance[:50])
                self._set_state(VoiceState.IDLE)
                return

            # Validate response length
            words = response.strip().split()
            if len(words) < self._config.min_response_length:
                logger.warning(
                    "Voice: Response too short (%d words): %r",
                    len(words), response[:50]
                )
                self._set_state(VoiceState.IDLE)
                return

            # Speak the response
            await self._speak(response)

        except asyncio.TimeoutError:
            logger.error(
                "Voice: LLM timed out after %.0fs for utterance %r",
                self._config.processing_timeout_s, utterance[:50]
            )
            self._set_state(VoiceState.IDLE)
        except Exception as exc:
            logger.error("Voice: Error handling utterance: %s", exc)
            self._set_state(VoiceState.IDLE)

    # ── TTS ───────────────────────────────────────────────────────────────────

    async def _speak(self, text: str):
        """Speak text via TTS with interrupt support."""
        if not self._tts:
            # No TTS — just log the response
            logger.info("TTS unavailable. Response: %s", text[:200])
            self._set_state(VoiceState.IDLE)
            return

        self._set_state(VoiceState.SPEAKING)
        logger.info("Speaking: %r...", text[:60])

        try:
            self._current_tts_task = asyncio.create_task(
                self._tts_speak(text), name="tts_speak"
            )
            await self._current_tts_task
        except asyncio.CancelledError:
            self._tts_interrupted += 1
            logger.debug("TTS interrupted")
        except Exception as exc:
            logger.error("TTS error: %s", exc)
        finally:
            self._current_tts_task = None
            self._set_state(VoiceState.IDLE)

    async def _tts_speak(self, text: str):
        """Actual TTS call, wrapped for async."""
        if hasattr(self._tts, 'speak_async'):
            await self._tts.speak_async(text)
        elif hasattr(self._tts, 'speak'):
            await asyncio.get_event_loop().run_in_executor(
                None, self._tts.speak, text
            )
        elif hasattr(self._tts, 'stream_text'):
            await self._tts.stream_text(text)

    async def _interrupt_tts(self):
        """Stop current TTS output."""
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            try:
                await self._current_tts_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._tts and hasattr(self._tts, 'stop'):
            try:
                self._tts.stop()
            except Exception:
                pass

    # ── Orchestrator Integration ──────────────────────────────────────────────

    async def _interrupt_autonomous_thought(self):
        """
        Cancel any running autonomous thought before processing user input.
        This is the FIX for the race condition — we actually await the cancellation.
        """
        if not hasattr(self._orch, '_current_thought_task'):
            return

        task = self._orch._current_thought_task
        if task is None or task.done():
            return

        logger.debug("Interrupting autonomous thought for voice input")
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass

        # Clear the task reference
        self._orch._current_thought_task = None

        # Also flush the reply queue to prevent stale responses
        if hasattr(self._orch, 'reply_queue'):
            while not self._orch.reply_queue.empty():
                try:
                    self._orch.reply_queue.get_nowait()
                except Exception:
                    break

    # ── State Management ──────────────────────────────────────────────────────

    def _set_state(self, new_state: VoiceState):
        if new_state != self._state:
            logger.debug("Voice state: %s → %s", self._state.value, new_state.value)
            self._state = new_state

    def get_status(self) -> Dict[str, Any]:
        return {
            "state": self._state.value,
            "utterances_processed": self._utterances_processed,
            "tts_interruptions": self._tts_interrupted,
            "stt_errors": self._stt_errors,
            "reconnect_attempts": self._reconnect_attempts,
            "stt_loaded": self._stt is not None,
            "tts_loaded": self._tts is not None,
            "queue_depth": self._utterance_queue.qsize(),
        }


# ── Fallback TTS Wrapper ──────────────────────────────────────────────────────

class _MacOSSayWrapper:
    """macOS 'say' command as TTS fallback."""

    def __init__(self, voice: str = "Samantha", rate: int = 180):
        self.voice = voice
        self.rate = rate
        self._proc = None

    def speak(self, text: str):
        import subprocess
        # Kill previous
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        # Clean text for shell safety
        clean = text.replace('"', "'").replace('\\', '')[:500]
        self._proc = subprocess.Popen([
            "say", "-v", self.voice, "-r", str(self.rate), clean
        ])
        self._proc.wait()

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


# ── Whisper Direct Wrapper ────────────────────────────────────────────────────

class _WhisperWrapper:
    """Direct faster-whisper wrapper for audio capture."""

    def __init__(self, model_size: str = "base", language: str = "en"):
        from faster_whisper import WhisperModel
        self._model = WhisperModel(model_size, device="auto", compute_type="int8")
        self._language = language
        self.last_text = None
        logger.info("WhisperWrapper loaded (model=%s)", model_size)

    def transcribe(self, audio_path: Optional[str] = None) -> Optional[str]:
        """
        Transcribe from file path or from microphone capture.
        Returns transcribed text or None.
        """
        if audio_path is None:
            audio_path = self._capture_from_mic()
        if audio_path is None:
            return None

        segments, info = self._model.transcribe(
            audio_path,
            language=self._language,
            beam_size=5,
        )
        text = " ".join(seg.text for seg in segments).strip()
        return text if text else None

    def _capture_from_mic(self) -> Optional[str]:
        """Capture audio from microphone to temp file."""
        try:
            import sounddevice as sd
            import soundfile as sf
            import tempfile
            import numpy as np

            SAMPLE_RATE = 16000
            DURATION = 5  # seconds — adjust for your use case

            logger.debug("Recording %ds of audio...", DURATION)
            audio = sd.rec(
                int(DURATION * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
            )
            sd.wait()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                sf.write(f.name, audio, SAMPLE_RATE)
                return f.name
        except Exception as exc:
            logger.error("Mic capture failed: %s", exc)
            return None

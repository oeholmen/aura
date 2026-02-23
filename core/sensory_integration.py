"""Sensory Integration System
Gives Aura access to cameras, microphones, speakers, and A/V production tools
"""
import base64
import logging
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .container import ServiceContainer, ServiceLifetime
except (ImportError, ValueError):
    from container import ServiceContainer, ServiceLifetime

logger = logging.getLogger("Aura.SensoryIntegration")


class SensoryModality(Enum):
    """Types of sensory input"""

    VISION = "vision"
    HEARING = "hearing"
    TEXT = "text"


class SensorySystem:
    """Manages Aura's sensory perception across multiple modalities.
    
    Enables:
    - Vision (camera)
    - Hearing (microphone)
    - Speech (speakers/TTS)
    - Audio/visual production
    """
    
    def __init__(self):
        self.vision = VisionSystem()
        self.hearing = HearingSystem()
        self.speech = SpeechSystem()
        self.av_production = AVProductionSystem()
        
        # Sensory memory (recent perceptions)
        self.sensory_memory = []
        self.max_memory_items = 100
        
    def perceive(self, modality: SensoryModality, **kwargs) -> Dict[str, Any]:
        """Perceive through specified sensory modality.
        
        Args:
            modality: Which sense to use
            **kwargs: Modality-specific parameters
            
        Returns:
            Perception data

        """
        perception = {
            "timestamp": time.time(),
            "modality": modality.value,
            "data": None,
            "interpretation": None
        }
        
        try:
            if modality == SensoryModality.VISION:
                perception["data"] = self.vision.capture(**kwargs)
                perception["interpretation"] = self.vision.analyze(perception["data"])
                
            elif modality == SensoryModality.HEARING:
                perception["data"] = self.hearing.listen(**kwargs)
                perception["interpretation"] = self.hearing.transcribe(perception["data"])
                
            elif modality == SensoryModality.TEXT:
                # Text is already interpreted
                perception["data"] = kwargs.get("text")
                perception["interpretation"] = perception["data"]
            
            # Store in sensory memory
            self._store_in_memory(perception)
            
            return perception
            
        except Exception as e:
            logger.error("Perception failed: %s", e)
            perception["error"] = str(e)
            return perception
    
    def express(self, modality: SensoryModality, content: Any, **kwargs) -> Dict[str, Any]:
        """Express through specified modality.
        
        Args:
            modality: How to express (speech, visual, etc.)
            content: What to express
            **kwargs: Modality-specific parameters
            
        Returns:
            Expression result

        """
        expression = {
            "timestamp": time.time(),
            "modality": modality.value,
            "content": content,
            "success": False
        }
        
        try:
            if modality == SensoryModality.HEARING:  # Use hearing modality for speech output
                result = self.speech.speak(content, **kwargs)
                expression["success"] = result.get("success", False)
                expression["audio_file"] = result.get("audio_file")
                
            # Could add visual expression (generating images/videos)
            
            return expression
            
        except Exception as e:
            logger.error("Expression failed: %s", e)
            expression["error"] = str(e)
            return expression
    
    def _store_in_memory(self, perception: Dict[str, Any]):
        """Store perception in short-term sensory memory"""
        self.sensory_memory.append(perception)
        
        # Trim if too large
        if len(self.sensory_memory) > self.max_memory_items:
            self.sensory_memory = self.sensory_memory[-self.max_memory_items:]
    
    def get_recent_perceptions(self, modality: Optional[SensoryModality] = None, count: int = 10) -> List[Dict]:
        """Get recent perceptions, optionally filtered by modality"""
        perceptions = self.sensory_memory[-count:]
        
        if modality:
            perceptions = [p for p in perceptions if p["modality"] == modality.value]
        
        return perceptions


class VisionSystem:
    """Camera and visual perception system.
    
    Enables Aura to:
    - Capture images/video from camera
    - Analyze visual content
    - Recognize objects, faces, text
    - Understand scenes
    """
    
    def __init__(self):
        self.camera_available = self._check_camera()
        self.last_capture = None
        
    def _check_camera(self) -> bool:
        """Check if camera is available"""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            available = cap.isOpened()
            cap.release()
            return available
        except ImportError:
            logger.warning("OpenCV not installed - camera unavailable")
            return False
        except Exception as e:
            logger.warning("Camera check failed: %s", e)
            return False
    
    def capture(self, duration: float = 0, save_path: Optional[str] = None) -> Dict[str, Any]:
        """Capture image or video from camera.
        
        Args:
            duration: If > 0, capture video for this many seconds. If 0, capture single image.
            save_path: Where to save capture
            
        Returns:
            Capture data (image or video path)

        """
        if not self.camera_available:
            return {"error": "camera_not_available"}
        
        try:
            import cv2
            import numpy as np
            
            cap = cv2.VideoCapture(0)
            
            if duration == 0:
                # Single image
                ret, frame = cap.read()
                cap.release()
                
                if not ret:
                    return {"error": "capture_failed"}
                
                # Save if path provided
                if save_path:
                    cv2.imwrite(save_path, frame)
                
                # Convert to base64 for storage/transmission
                _, buffer = cv2.imencode('.jpg', frame)
                image_b64 = base64.b64encode(buffer).decode('utf-8')
                
                self.last_capture = {
                    "type": "image",
                    "data": image_b64,
                    "path": save_path,
                    "timestamp": time.time()
                }
                
                return self.last_capture
                
            else:
                # Video capture
                if not save_path:
                    save_path = f"capture_{int(time.time())}.mp4"
                
                # Video writer
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(save_path, fourcc, 20.0, (640, 480))
                
                start_time = time.time()
                while time.time() - start_time < duration:
                    ret, frame = cap.read()
                    if ret:
                        out.write(frame)
                
                cap.release()
                out.release()
                
                self.last_capture = {
                    "type": "video",
                    "path": save_path,
                    "duration": duration,
                    "timestamp": time.time()
                }
                
                return self.last_capture
                
        except Exception as e:
            logger.error("Capture failed: %s", e)
            return {"error": str(e)}
    
    def analyze(self, capture_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze captured visual data.
        
        This would integrate with vision models (CLIP, BLIP, etc.)
        to understand what's in the image.
        """
        if not capture_data or "error" in capture_data:
            return {"error": "invalid_capture"}
        
        analysis = {
            "timestamp": time.time(),
            "objects_detected": [],
            "scene_description": "",
            "text_detected": [],
            "faces_detected": 0
        }
        
        # In production, this would call a vision model
        # For now, placeholder
        analysis["scene_description"] = "Visual analysis requires vision model integration"
        
        # Could integrate with:
        # - OpenAI CLIP for scene understanding
        # - OCR for text detection
        # - Face detection models
        # - Object detection (YOLO, etc.)
        
        return analysis


class HearingSystem:
    """Microphone and audio perception system.
    
    Enables Aura to:
    - Record audio from microphone
    - Transcribe speech to text
    - Understand tone and emotion
    - Detect sounds
    """
    
    def __init__(self):
        self._microphone_checked = False
        self._microphone_available = False
        self.last_recording = None

    @property
    def microphone_available(self) -> bool:
        """Lazy check — only probe hardware on first access, not at startup."""
        if not self._microphone_checked:
            self._microphone_available = self._check_microphone()
            self._microphone_checked = True
        return self._microphone_available
        
    def _check_microphone(self) -> bool:
        """Check if microphone is available"""
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            available = p.get_device_count() > 0
            p.terminate()
            return available
        except ImportError:
            logger.warning("PyAudio not installed - microphone unavailable")
            return False
        except Exception as e:
            logger.warning("Microphone check failed: %s", e)
            return False
    
    def listen(self, duration: float = 5.0, save_path: Optional[str] = None) -> Dict[str, Any]:
        """Record audio from microphone.
        
        Args:
            duration: How long to record (seconds)
            save_path: Where to save recording
            
        Returns:
            Recording data

        """
        if not self.microphone_available:
            return {"error": "microphone_not_available"}
        
        try:
            import wave

            import pyaudio
            
            if not save_path:
                save_path = f"recording_{int(time.time())}.wav"
            
            # Recording parameters
            CHUNK = 1024
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 44100
            
            p = pyaudio.PyAudio()
            
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            
            logger.info("🎤 Recording for %s seconds...", duration)
            
            frames = []
            for i in range(0, int(RATE / CHUNK * duration)):
                data = stream.read(CHUNK)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            
            # Save to file (must call p.get_sample_size BEFORE p.terminate)
            sample_width = p.get_sample_size(FORMAT)
            p.terminate()
            
            wf = wave.open(save_path, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(sample_width)
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            self.last_recording = {
                "type": "audio",
                "path": save_path,
                "duration": duration,
                "timestamp": time.time()
            }
            
            logger.info("✓ Recording saved to: %s", save_path)
            
            return self.last_recording
            
        except Exception as e:
            logger.error("Recording failed: %s", e)
            return {"error": str(e)}
    
    def transcribe(self, audio_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transcribe audio to text.
        
        This would integrate with speech recognition (Whisper, etc.)
        """
        if not audio_data or "error" in audio_data:
            return {"error": "invalid_audio"}
        
        transcription = {
            "timestamp": time.time(),
            "text": "",
            "confidence": 0.0,
            "language": "en"
        }
        
        # In production, integrate with:
        # - Local speech recognition (Sovereign)
        # - Faster-Whisper (Local)
        
        try:
            from core.senses.voice_socket_logic import get_whisper_model
            model = get_whisper_model("tiny")
            
            if model:
                # Transcribe using faster-whisper
                segments, info = model.transcribe(audio_data["path"], beam_size=5)
                text = " ".join([segment.text for segment in segments]).strip()
                transcription["text"] = text
                transcription["confidence"] = 0.95
                logger.info("✓ Transcribed (Sovereign Whisper): %s", text)
            else:
                # Fallback to speech_recognition if model loading fails
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(audio_data["path"]) as source:
                    audio = recognizer.record(source)
                text = recognizer.recognize_google(audio)
                transcription["text"] = text
                transcription["confidence"] = 0.8
                logger.warning("! Whisper unavailable, fell back to legacy SR: %s", text)
            
        except ImportError:
            logger.warning("speech_recognition not installed")
            transcription["text"] = "[Transcription requires speech_recognition library]"
        except Exception as e:
            logger.warning("Transcription failed: %s", e)
            transcription["text"] = "[Transcription failed]"
            transcription["error"] = str(e)
        
        return transcription


class SpeechSystem:
    """Text-to-speech and voice synthesis system.
    
    Enables Aura to:
    - Speak text aloud
    - Use different voices/emotions
    - Control speech rate, pitch
    """
    
    def __init__(self):
        self.tts_available = self._check_tts()
        
    def _check_tts(self) -> bool:
        """Check if TTS is available"""
        try:
            import pyttsx3
            return True
        except ImportError:
            logger.warning("pyttsx3 not installed - TTS unavailable")
            return False
    
    def speak(self, text: str, rate: int = 150, volume: float = 1.0, save_path: Optional[str] = None) -> Dict[str, Any]:
        """Speak text aloud using TTS.
        
        Args:
            text: Text to speak
            rate: Speech rate (words per minute)
            volume: Volume (0.0 to 1.0)
            save_path: If provided, save audio to file instead of playing
            
        Returns:
            Speech result

        """
        if not self.tts_available:
            return {"error": "tts_not_available", "success": False}
        
        try:
            import pyttsx3
            
            engine = pyttsx3.init()
            engine.setProperty('rate', rate)
            engine.setProperty('volume', volume)
            
            if save_path:
                # Save to file
                engine.save_to_file(text, save_path)
                engine.runAndWait()
                
                result = {
                    "success": True,
                    "text": text,
                    "audio_file": save_path,
                    "timestamp": time.time()
                }
            else:
                # Speak aloud
                engine.say(text)
                engine.runAndWait()
                
                result = {
                    "success": True,
                    "text": text,
                    "timestamp": time.time()
                }
            
            logger.info("🔊 Spoke: %s...", text[:50])
            
            return result
            
        except Exception as e:
            logger.error("Speech failed: %s", e)
            return {"error": str(e), "success": False}


class AVProductionSystem:
    """Audio/visual production tools.
    
    Enables Aura to:
    - Edit audio/video
    - Create visual content
    - Generate images/animations
    - Mix audio
    """
    
    def __init__(self):
        pass
    
    def create_image(self, description: str, style: str = "realistic") -> Dict[str, Any]:
        """Generate image from description.
        
        Would integrate with:
        - DALL-E
        - Stable Diffusion
        - Midjourney API
        """
        return {
            "error": "image_generation_not_implemented",
            "note": "Integrate with DALL-E or Stable Diffusion"
        }
    
    def edit_video(self, video_path: str, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Edit video with specified operations.
        
        Would integrate with:
        - FFmpeg
        - MoviePy
        """
        return {
            "error": "video_editing_not_implemented",
            "note": "Integrate with FFmpeg or MoviePy"
        }


def get_sensory_system() -> SensorySystem:
    """Get global sensory system via DI container"""
    try:
        if "sensory_system" not in ServiceContainer._services:
            ServiceContainer.register(
                "sensory_system",
                factory=lambda: SensorySystem(),
                lifetime=ServiceLifetime.SINGLETON
            )
        return ServiceContainer.get("sensory_system")
    except Exception as e:
        logger.debug("ServiceContainer unavailable or failed: %s. Using transient SensorySystem.", e)
        return SensorySystem()


# Integration helpes
def integrate_sensory_system(orchestrator):
    """Integrate sensory system into orchestrator.
    
    Adds sensory perception as available actions.
    """
    sensory = get_sensory_system()
    
    # Store reference
    orchestrator.sensory_system = sensory
    
    logger.info("✓ Sensory system integrated")
    logger.info("  Camera: %s", 'available' if sensory.vision.camera_available else 'unavailable')
    logger.info("  Microphone: %s", 'available' if sensory.hearing.microphone_available else 'unavailable')
    logger.info("  TTS: %s", 'available' if sensory.speech.tts_available else 'unavailable')

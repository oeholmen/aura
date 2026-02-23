import logging

try:
    from RealtimeTTS import SystemEngine, TextToAudioStream
except ImportError:
    TextToAudioStream = None
    SystemEngine = None

logger = logging.getLogger("Senses.Mouth")

class FastMouth:
    """The 'Mouth' of the machine.
    Uses RealtimeTTS to speak LLM tokens/sentences instantly.
    """

    def __init__(self):
        # Sovereign Priority: Kokoro-TTS
        # Switch from SystemEngine (Cloud-Linked) to Kokoro (Local-Only)
        try:
            # We assume Kokoro is available via RealtimeTTS or a local API
            from RealtimeTTS import KokoroEngine
            self.engine = KokoroEngine()
            self.stream = TextToAudioStream(self.engine)
            logger.info("👄 FastMouth initialized (KokoroEngine — Sovereign)")
        except (ImportError, Exception):
            # Fallback to SystemEngine (Fastest for Mac)
            try:
                self.engine = SystemEngine() 
                self.stream = TextToAudioStream(self.engine)
                logger.info("👄 FastMouth initialized (SystemEngine)")
            except Exception as e:
                logger.warning("Failed to initialize RealtimeTTS Engine: %s. Falling back to system 'say'.", e)
                self.stream = None
                self.fallback_say = True

    def speak(self, text: str):
        """Speaks a single string immediately.
        """
        if self.stream:
            try:
                self.stream.feed(text)
                self.stream.play_async()
            except Exception as e:
                logger.error("Speech error: %s", e)
        elif getattr(self, 'fallback_say', False):
            # macOS native 'say' fallback
            import subprocess
            try:
                subprocess.Popen(["say", "-v", "Samantha", text]) # Background process
            except (FileNotFoundError, OSError):
                subprocess.Popen(["say", text])

    def speak_stream(self, text_generator):
        """Ingests a generator (the LLM stream) and speaks instantly.
        """
        if not self.stream:
            return
            
        try:
            self.stream.feed(text_generator)
            self.stream.play_async() # Non-blocking playback
        except Exception as e:
            logger.error("Speech error: %s", e)

    def stop(self):
        if self.stream:
            self.stream.stop()

"""Boot-time fallback implementations for kernel organs.

When a real subsystem (LLM, vision, neural bridge, etc.) isn't available
yet — because the model is still loading, hardware isn't present, or a
dependency failed — the kernel uses these minimal fallbacks so the
cognitive tick can still complete.

These are NOT stubs. They're the offline tier of a graceful degradation
system. Once the real subsystem comes online, it replaces the fallback.
"""


class FallbackLLM:
    """Returns a minimal response until the real model finishes loading."""

    async def think(self, prompt: str, **kwargs) -> str:
        return "I'm Aura."

    async def classify(self, prompt: str) -> str:
        return "CHAT"


class FallbackVision:
    """No-op vision when no camera or vision model is available."""

    async def capture(self):
        return None

    async def capture_desktop(self):
        return None

    async def load(self):
        pass


class FallbackNeural:
    """Lightweight stand-in when NeuralBridge can't initialize."""

    async def load(self):
        pass

    def get_status(self):
        return {"is_running": False, "lightweight_mode": True}


class FallbackVoice:
    """Silent voice when TTS engine isn't available."""

    async def speak(self, text):
        pass

    async def say(self, text):
        pass

    async def load(self):
        pass


class FallbackOrgan:
    """Generic fallback for any organ that failed to load."""

    async def load(self):
        pass

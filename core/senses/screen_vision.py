import base64
import io
import logging

import pyautogui
import requests
from PIL import Image

# Aura Imports
try:
    from core.config import config
except ImportError:
    config = None

logger = logging.getLogger("Senses.Vision")

class LocalVision:
    """The 'Eyes' of the machine.
    Uses a local Vision-Language Model (LLaVA) via Ollama to see the screen.
    """

    def __init__(self, model="llava"):
        self.model = model
        self.api_url = "http://localhost:11434/api/generate"
        self._last_failure_time = 0
        self._cooling_period = 60  # seconds

    async def capture_screen(self):
        """Take a screenshot of the primary monitor.
        Note: pyautogui.screenshot() is generally thread-safe on macOS but 
        performs best when offloaded if Resize/PIL follows.
        """
        from core.utils.executor import run_in_thread
        return await run_in_thread(pyautogui.screenshot)

    async def analyze_moment(self, prompt="What is on the user's screen?"):
        """The visual cortex loop.
        Captures screen -> Sends to LLaVA -> Returns description.
        """
        from core.container import ServiceContainer
        from core.security.permission_guard import PermissionType
        from core.utils.executor import run_in_process, run_in_thread
        
        if time.time() - self._last_failure_time < self._cooling_period:
            logger.debug("👁️ Vision in cooling period, skipping capture.")
            return "Vision system is recovering from a previous failure."

        try:
            # 1. Pre-flight Permission Check
            guard = ServiceContainer.get("permission_guard")
            if guard:
                check = await guard.check_permission(PermissionType.SCREEN)
                if not check["granted"]:
                    logger.warning("👁️ Vision Blocked: %s", check["guidance"])
                    return f"I cannot see your screen. {check['guidance']}"

            # 2. Capture
            image = await self.capture_screen()
            
            # Offload CPU-heavy image processing to Process Pool
            def process_image(img):
                img.thumbnail((672, 672))
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                return base64.b64encode(buffered.getvalue()).decode("utf-8")

            img_str = await run_in_process(process_image, image)

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [img_str],
                "stream": False
            }

            logger.info("🧠 Processing visual data with %s...", self.model)
            
            # Offload blocking HTTP request to Thread Pool
            def send_request(url, p):
                return requests.post(url, json=p, timeout=30)
                
            response = await run_in_thread(send_request, self.api_url, payload)
            response.raise_for_status()
            
            description = response.json().get("response", "")
            logger.info("👁️ Vision Result: %s...", description[:50])
            return description
            
        except Exception as e:
            self._last_failure_time = time.time()
            logger.error("Blindness Error: %s", e)
            return "I tried to look, but my vision subsystem failed. Please ensure Ollama is running with LLaVA."

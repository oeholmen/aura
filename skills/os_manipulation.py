import logging
import asyncio

import pyautogui

from infrastructure import BaseSkill

logger = logging.getLogger("Skills.Hands")

# Disable PyAutoGUI failsafe for pure autonomous mode if requested, 
# but keeping it enabled by default for safety.
# pyautogui.FAILSAFE = False 

class DesktopControlSkill(BaseSkill):
    """The 'Hands' of the machine.
    Allows Aura to click, type, and scroll.
    """

    name = "os_manipulation"
    description = "Manipulate the mouse and keyboard to interact with the OS using PyAutoGUI."
    
    async def execute(self, goal: dict, context: dict) -> dict:
        """Router for physical actions.
        action: 'type', 'click', 'scroll', 'open_app', 'screenshot'
        """
        params = goal.get("params", {})
        action = params.get("action")
        
        logger.warning("🖐️ OS MANIPULATION: %s %s", action, params)

        if action == "type":
            text = params.get("text")
            interval = params.get("speed", 0.05)
            if not text:
                return {"ok": False, "error": "No text provided to type."}
            await asyncio.to_thread(pyautogui.write, text, interval=interval)
            return {"ok": True, "result": f"Typed: {text[:20]}..."}
            
        elif action == "click":
            x = params.get("x")
            y = params.get("y")
            button = params.get("button", "left")
            clicks = params.get("clicks", 1)
            
            if x is not None and y is not None:
                await asyncio.to_thread(pyautogui.click, x, y, button=button, clicks=clicks)
            else:
                await asyncio.to_thread(pyautogui.click, button=button, clicks=clicks)
            return {"ok": True, "result": f"Clicked {button} at ({x or 'current'}, {y or 'current'})"}

        elif action == "scroll":
            amount = params.get("amount", 0)
            await asyncio.to_thread(pyautogui.scroll, amount)
            return {"ok": True, "result": f"Scrolled {amount}"}

        elif action == "open_app":
            app_name = params.get("app_name")
            if not app_name:
                return {"ok": False, "error": "No app name provided."}
            
            # macOS Spotlight trick
            await asyncio.to_thread(pyautogui.hotkey, 'command', 'space')
            await asyncio.sleep(0.5)
            await asyncio.to_thread(pyautogui.write, app_name)
            await asyncio.sleep(0.5)
            await asyncio.to_thread(pyautogui.press, 'enter')
            return {"ok": True, "result": f"Launched signal for {app_name}"}

        elif action == "press":
            key = params.get("key")
            if not key:
                return {"ok": False, "error": "No key provided."}
            await asyncio.to_thread(pyautogui.press, key)
            return {"ok": True, "result": f"Pressed {key}"}

        elif action == "hotkey":
            keys = params.get("keys", [])
            if not keys:
                return {"ok": False, "error": "No keys provided for hotkey."}
            await asyncio.to_thread(pyautogui.hotkey, *keys)
            return {"ok": True, "result": f"Pressed hotkey: {'+'.join(keys)}"}

        return {"ok": False, "error": f"Action '{action}' not recognized."}

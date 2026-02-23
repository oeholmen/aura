"""Unified Browser Skill
Combines the best of Playwright and Selenium/Undetected-Chromedriver.
Primary: Playwright (Fast, Robust)
Fallback: Undetected-Chromedriver (Stealth, CAPTCHA bypass)
Fallback 2: Native Webbrowser (Simple opens)
"""
import asyncio
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

try:
    from infrastructure import BaseSkill
except ImportError:
    sys.path.append(str(Path(__file__).parent.parent))
    from infrastructure import BaseSkill

logger = logging.getLogger("Skills.UnifiedBrowser")

# Dependency Flags
HAS_PLAYWRIGHT = False
HAS_SELENIUM = False

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except ImportError:  # Non-critical, fallback handled
    logger.warning("Playwright not found.")

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    HAS_SELENIUM = True
except ImportError:  # Non-critical, fallback handled
    logger.warning("Selenium not found.")

class PrivacyEnhancer:
    """Techniques to reduce browser fingerprinting."""

    @staticmethod
    def get_randomized_user_agent() -> str:
        import random
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ]
        return random.choice(agents)
    
    @staticmethod
    def get_viewport() -> Dict[str, int]:
        import random
        return random.choice([
            {'width': 1920, 'height': 1080},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1280, 'height': 800}
        ])

class UnifiedBrowserSkill(BaseSkill):
    name = "browser_action"
    description = "Web browsing, searching, and interaction using Playwright or Selenium."
    
    def __init__(self):
        self.profile_dir = str(Path(os.getcwd()) / "autonomy_engine/data/browser_profile")
        self.download_dir = str(Path.home() / "Downloads")
        os.makedirs(self.profile_dir, exist_ok=True)
        from infrastructure import HealthMonitor
        self.monitor = HealthMonitor()
        
    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute browser action with exponential backoff."""
        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                result = await self._execute_core(goal, context)
                if result.get("ok"):
                    self.monitor.record_execution("browser_action", True, (time.time() - start_time) * 1000)
                    return result
                
                # Check for recoverable errors
                error = result.get("error", "")
                if "all_strategies_failed" in error:
                    # Don't retry if everything failed already (strategies have their own logic)
                    break
                    
                logger.warning("Browser attempt %s failed (%s). Retrying...", attempt + 1, error)
                await asyncio.sleep(base_delay * (2 ** attempt))
                
            except Exception as e:
                logger.error("Browser crash on attempt %s: %s", attempt + 1, e)
                await asyncio.sleep(base_delay * (2 ** attempt))

        self.monitor.record_execution("browser_action", False, 0.0, "Max retries exceeded")
        return {"ok": False, "error": "max_retries_exceeded", "message": "Browser automation failed after retries."}

    async def _execute_core(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Core execution logic"""
        engine_pref = context.get("engine", "auto") # auto, playwright, selenium
        
        url = self._extract_url(goal)
        
        # FALLBACK: Topic to URL conversion
        if not url and "objective" in goal:
            obj = goal["objective"]
            if " " in obj and "." not in obj and not obj.startswith("http"):
                clean_query = obj.replace("browse", "").replace("search", "").strip()
                import urllib.parse
                url = f"https://www.google.com/search?q={urllib.parse.quote(clean_query)}"

        # Try Playwright First (Preferred)
        if (engine_pref == "auto" or engine_pref == "playwright") and HAS_PLAYWRIGHT:
            try:
                return await self._run_playwright(goal, context, url)
            except Exception as e:
                logger.error("Playwright failed: %s", e)
                if engine_pref == "playwright": # Strict mode
                    return {"ok": False, "error": str(e)}

        # Try Selenium (Fallback)
        if (engine_pref == "auto" or engine_pref == "selenium") and HAS_SELENIUM:
            try:
                # Selenium is still sync, run in thread if needed?
                # For now, just call it, but ideally we'd thread it.
                return self._run_selenium(goal, context)
            except Exception as e:
                logger.error("Selenium failed: %s", e)
                if engine_pref == "selenium":
                    return {"ok": False, "error": str(e)}
        
        # Last Resort: Text-Only Fetch
        if url: 
             return self._run_text_only(url)

        return {"ok": False, "error": "all_strategies_failed", "message": "Browsers failed and no fallback available"}

    # ... _extract_url and _run_text_only methods remain same ...
    def _extract_url(self, goal: Dict[str, Any]) -> Optional[str]:
        # Try params
        if "params" in goal and "url" in goal["params"]:
            return goal["params"]["url"]
        # Try finding in objective string
        obj = goal.get("objective", "")
        if isinstance(obj, str):
            import re
            urls = re.findall(r'https?://[^\s]+', obj)
            if urls: return urls[0]
        return None

    def _run_text_only(self, url: str) -> Dict[str, Any]:
        """Fallback to simple HTTP fetch"""
        try:
             logger.info("Attempting text-only fetch for %s", url)
             response = requests.get(url, timeout=10)
             response.raise_for_status()
             content = response.text
             if content:
                 return {
                     "ok": True,
                     "engine": "text_only_fallback",
                     "title": "Text Only View",
                     "url": url,
                     "content": content[:5000],
                     "note": "Content fetched via HTTP because browsers failed."
                 }
        except Exception as e:
             logger.warning("Text-only fetch failed: %s", e)
        
        # Absolute Last Resort: System Browser
        try:
            import webbrowser
            webbrowser.open(url)
            return {
                "ok": True,
                "mode": "native_fallback",
                "message": "Opened in system browser (Automation failed)."
            }
        except Exception:
            return {"ok": False, "error": "all_strategies_failed"}

    async def _run_playwright(self, goal: Dict[str, Any], context: Dict[str, Any], url: str = None) -> Dict[str, Any]:
        logger.info("Starting Playwright Session...")
        headless = context.get("headless", False) # Default to visible
        
        # Check for Phantom Browser (Persistent)
        phantom = context.get("phantom_browser")
        if phantom:
            if not headless and not phantom.visible:
                await phantom.set_visibility(True)
            elif headless and phantom.visible:
                await phantom.set_visibility(False)
            if url: await phantom.browse(url)
            
            return {
                "ok": True,
                "engine": "phantom_playwright",
                "title": "Phantom Session",
                "content": await phantom.read_content(),
                "screenshot": await phantom.screenshot()
            }

        # Ephemeral Session with Privacy Enhancements
        async with async_playwright() as p:
            # Launch
            browser = await p.chromium.launch(headless=headless, slow_mo=500)
            
            # Privacy: Randomize context
            context_obj = await browser.new_context(
                viewport=PrivacyEnhancer.get_viewport(),
                user_agent=PrivacyEnhancer.get_randomized_user_agent(),
                locale='en-US'
            )
            page = await context_obj.new_page()
            
            # Navigate
            if url:
                logger.info("Navigating to %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000) # Increased timeout
            
            # Actions
            params = goal.get("params", {})
            steps = params.get("steps", [])
            for step in steps:
                stype = step.get("type")
                sel = step.get("selector")
                val = step.get("value")
                try:
                    if stype == "click": await page.click(sel)
                    elif stype == "type": await page.fill(sel, val)
                    elif stype == "scroll": await page.evaluate("window.scrollBy(0, 500)")
                    elif stype == "wait": await asyncio.sleep(float(val))
                    elif stype == "get_html": 
                        params["html"] = await page.content()
                except Exception as e:
                    logger.warning("Action %s failed: %s", stype, e)

            # Extract
            title = await page.title()
            text = await page.inner_text("body")
            html = await page.content()
            screenshot_bytes = await page.screenshot()
            screenshot = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            await browser.close()
            
            return {
                "ok": True,
                "engine": "playwright_ephemeral_secure",
                "title": title,
                "url": page.url,
                "content": text[:3000] + "...",
                "html": html[:5000] if params.get("get_html") else None,
                "screenshot": screenshot
            }

    def _run_selenium(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Starting Selenium Session...")
        # ... reusing the logic from enhanced_browser.py ...
        # Simplified for brevity in this shim, assuming Playwright works 
        # But fully implementing checking logic
        
        options = uc.ChromeOptions()
        if context.get("headless", False):
            options.add_argument('--headless=new')
            
        driver = uc.Chrome(options=options)
        try:
            url = self._extract_url(goal)
            if url:
                driver.get(url)
            
            title = driver.title
            text = driver.find_element(By.TAG_NAME, "body").text
            
            return {
                "ok": True,
                "engine": "selenium",
                "title": title,
                "content": text[:3000]
            }
        finally:
            driver.quit()


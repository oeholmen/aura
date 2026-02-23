"""Phantom Browser Module
Playwright-based "human-like" browser agent for Aura.

Capabilities:
- Dynamic Visibility: Headless (background) vs Headed (interactive)
- Human-like Interaction: Random microsleeps, typing speeds, cursor movements
- Robust Navigation: Handling broken links, backing out, reading content
- Content Extraction: Getting markdown from pages

Usage:
    browser = PhantomBrowser()
    browser.browse("https://aura.internal")
    browser.type("input[name='q']", "Hello World")
    browser.click("input[name='btnK']")
"""
import asyncio
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional

# Try to import Playwright, but don't crash if not installed yet
try:
    from playwright.async_api import Browser, ElementHandle, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("PhantomBrowser")

class PhantomBrowser:
    """High-fidelity browser agent (Async Version).
    """
    
    def __init__(self, visible: bool = False):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.visible = visible
        self.is_active = False
        
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed! Run: pip install playwright && playwright install")
            return

    async def _start_browser(self):
        """Start the Playwright browser asynchronously"""
        try:
            if self.is_active:
                return

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=not self.visible,
                args=['--disable-blink-features=AutomationControlled']  # Stealth arg
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = await self.context.new_page()
            self.is_active = True
            logger.info("✓ Phantom Browser initialized (Visible: %s)", self.visible)
        except Exception as e:
            logger.error("Failed to start browser: %s", e)
            self.is_active = False

    async def set_visibility(self, visible: bool):
        """Toggle visibility (requires restart)"""
        if self.visible != visible:
            logger.info("Switching visibility: %s -> %s", self.visible, visible)
            self.visible = visible
            await self.close()
            await self._start_browser()

    async def browse(self, url: str) -> bool:
        """Navigate to a URL"""
        if not self.is_active: 
            await self._start_browser()
            if not self.is_active:
                logger.error("Browser failed to start.")
                return False
            
        if not url.startswith('http'):
            url = 'https://' + url
            
        logger.info("🌐 Navigating to: %s", url)
        try:
            await self.page.goto(url, timeout=30000, wait_until='domcontentloaded')
            await self._human_delay(1, 2)
            return True
        except Exception as e:
            logger.error("Navigation failed: %s", e)
            return False

    async def click(self, selector: str = None, text_match: str = None) -> bool:
        """Human-like click on an element with enhanced robustness."""
        try:
            element = None
            if text_match:
                # Try multiple ways to find text (case-insensitive, contains)
                selectors = [
                    f"text='{text_match}'",
                    f"text=\"{text_match}\"",
                    f"a:has-text('{text_match}')",
                    f"button:has-text('{text_match}')",
                    f"*[role='button']:has-text('{text_match}')"
                ]
                for s in selectors:
                    try:
                        loc = self.page.locator(s).first
                        if await loc.is_visible(timeout=2000):
                            element = loc
                            break
                    except:
                        continue
                
                if not element:
                    # Fallback to get_by_text with regex for fuzzy match
                    import re
                    try:
                        loc = self.page.get_by_text(re.compile(text_match, re.IGNORECASE)).first
                        if await loc.is_visible(timeout=2000):
                            element = loc
                    except:
                        pass
            elif selector:
                element = self.page.locator(selector).first

            if element and await element.is_visible():
                # Scroll into view if needed
                await element.scroll_into_view_if_needed()
                await self._human_delay(0.2, 0.5)
                
                # Human-like mouse movement
                box = await element.bounding_box()
                if box:
                    x = box['x'] + box['width'] / 2 + random.randint(-5, 5)
                    y = box['y'] + box['height'] / 2 + random.randint(-3, 3)
                    await self.page.mouse.move(x, y, steps=15)
                    await self._human_delay(0.1, 0.3)
                
                await element.click()
                logger.info("🖱️ Clicked: %s", selector or text_match)
                await self._human_delay(0.5, 1.5)
                return True
            else:
                logger.warning("Element not found or not visible: %s", selector or text_match)
                return False
        except Exception as e:
            logger.error("Click failed: %s", e)
            return False

    async def type(self, selector: str, text: str) -> bool:
        """Human-like typing"""
        try:
            await self.click(selector) # Focus first
            
            logger.info("⌨️ Typing: '%s'", text)
            for char in text:
                await self.page.keyboard.type(char)
                # Random typing delay between keystrokes
                await asyncio.sleep(random.uniform(0.05, 0.15))
            
            await self._human_delay(0.5, 1.0)
            return True
        except Exception as e:
            logger.error("Typing failed: %s", e)
            return False

    async def scroll(self, direction: str = "down", amount: int = 500):
        """Scroll the page in a human-like manner."""
        try:
            steps = 5
            step_amount = amount // steps
            for _ in range(steps):
                if direction == "down":
                    await self.page.mouse.wheel(0, step_amount)
                else:
                    await self.page.mouse.wheel(0, -step_amount)
                await asyncio.sleep(random.uniform(0.1, 0.3))
            await self._human_delay(0.5, 1.0)
        except Exception as e:
            logger.error("Scroll failed: %s", e)

    async def read_content(self) -> str:
        """Extract main text content from page using simple layout heuristics."""
        try:
            if not self.page: return ""
            
            # Enhanced extraction heuristic
            title = await self.page.title()
            
            main_text = await self.page.evaluate("""() => {
                function getCleanText(node) {
                    let text = "";
                    for (let child of node.childNodes) {
                        if (child.nodeType === Node.TEXT_NODE) {
                            text += child.textContent;
                        } else if (child.nodeType === Node.ELEMENT_NODE) {
                            // Skip noise elements
                            const tag = child.tagName.toLowerCase();
                            const id = (child.id || "").toLowerCase();
                            const cls = (child.className || "").toString().toLowerCase();
                            
                            const isNoise = ["nav", "footer", "header", "aside", "script", "style", "noscript"].includes(tag) ||
                                            id.includes("nav") || id.includes("footer") || id.includes("menu") ||
                                            cls.includes("nav") || cls.includes("footer") || cls.includes("sidebar") ||
                                            cls.includes("cookie") || id.includes("popup");
                                            
                            if (isNoise) continue;
                            text += getCleanText(child) + "\\n";
                        }
                    }
                    return text.trim();
                }
                
                const target = document.querySelector('main') || document.querySelector('article') || document.body;
                return getCleanText(target);
            }""")
            
            # Filter for meaningful lines (skip very short fragments/menus)
            lines = [line.strip() for line in main_text.split('\n') if line.strip() and len(line.strip()) > 30]
            cleaned_text = '\n\n'.join(lines)
            
            if not cleaned_text:
                # Fallback to body innerText if heuristic was too aggressive
                cleaned_text = await self.page.evaluate("() => document.body.innerText")
            
            return f"# {title}\n\n{cleaned_text[:6000]}"
        except Exception as e:
            logger.error("Read content failed: %s", e)
            return ""

    async def get_links(self) -> List[Dict[str, str]]:
        """Extract all links from page"""
        try:
            if not self.page: return []
            links = await self.page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText.trim(),
                    url: a.href
                })).filter(l => l.text && l.url)
            }""")
            return links
        except Exception as e:
            logger.error("Get links failed: %s", e)
            return []

    async def screenshot(self) -> Optional[str]:
        """Take a screenshot (base64)"""
        try:
            if not self.page: return None
            import base64
            bytes_data = await self.page.screenshot()
            return base64.b64encode(bytes_data).decode('utf-8')
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return None

    async def close(self):
        """Close browser resources"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.is_active = False
        logger.info("Browser closed")

    async def _human_delay(self, min_s=0.5, max_s=1.5):
        """Random delay to simulate human pause"""
        await asyncio.sleep(random.uniform(min_s, max_s))

# Integration Helper
async def integrate_phantom_browser(orchestrator):
    """Integrate Phantom Browser into Orchestrator"""
    pb = PhantomBrowser(visible=False) # Start hidden
    await pb._start_browser()
    orchestrator.phantom_browser = pb
    logger.info("✅ Phantom Browser integrated")

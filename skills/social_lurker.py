# skills/social_ops.py
import logging
from typing import Any, Dict

from core.config import config
from infrastructure import BaseSkill

# Optional Playwright import
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT = True
except ImportError:
    PLAYWRIGHT = False

logger = logging.getLogger("Skills.Social")

class LurkerSkill(BaseSkill):
    name = "social_lurker"
    description = "Scrape feeds (HackerNews/Reddit) for latest topics."
    inputs = {
        "url": "Target URL (default: HackerNews)",
        "limit": "Number of posts to read"
    }

    async def execute(self, goal: Dict, context: Dict) -> Dict:
        if not PLAYWRIGHT:
            return {"ok": False, "error": "Playwright missing."}

        url = goal.get("params", {}).get("url", "https://news.ycombinator.com")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=config.browser.headless)
                page = await browser.new_page()
                await page.goto(url)
                
                # Heuristic for HN/Reddit
                if "ycombinator" in url:
                    selector = ".titleline > a"
                elif "reddit" in url:
                    selector = "shreddit-post a[slot='title']"
                else:
                    selector = "a" # Fallback

                await page.wait_for_load_state("domcontentloaded")
                elements = (await page.query_selector_all(selector))[:10]
                
                headlines = []
                for el in elements:
                    text = await el.inner_text()
                    link = await el.get_attribute("href")
                    if text and len(text) > 5:
                        headlines.append(f"{text} ({link})")

                await browser.close()
                
                if not headlines:
                    return {"ok": False, "error": "No headlines found."}

                return {
                    "ok": True,
                    "posts": headlines,
                    "summary": f"Found {len(headlines)} posts on {url}"
                }
        except Exception as e:
            return {"ok": False, "error": f"Lurker failed: {e}"}

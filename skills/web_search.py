import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from core.phantom_browser import PhantomBrowser

logger = logging.getLogger("Skills.WebSearch")

class EnhancedWebSearchSkill:
    """Real web search capability into Aura using PhantomBrowser (Playwright).
    Registered as 'web_search' service.
    """

    name = "search_web"
    description = "Search the open web for information. Use this to find facts, news, or deep dive on topics."
    
    def __init__(self):
        self.browser = PhantomBrowser(visible=False)

    async def execute(self, goal: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a web search.
        Goal args: {"query": "search term", "deep": True/False}
        """
        query = goal.get("query")
        if not query and "parameters" in goal:
            query = goal["parameters"].get("query")
        deep = goal.get("deep", False)
            
        if not query:
            return {"error": "No query provided"}

        logger.info("🔍 Searching web for: %s (Deep: %s)", query, deep)
        
        try:
            if not self.browser.is_active:
                await self.browser._start_browser()
            
            # 1. Search (Try DuckDuckGo first, then Google)
            engines = [
                f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}",
                f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
            ]
            
            success = False
            html = ""
            for search_url in engines:
                success = await self.browser.browse(search_url)
                if success:
                    await self.browser._human_delay(2.5, 4.0)
                    html = await self.browser.page.content()
                    if "Unexpected error" not in html and "robot" not in html.lower():
                        logger.info("✅ Search successful using: %s", search_url)
                        break
                    else:
                        logger.warning("⚠️ Search engine block/error detected: %s", search_url)
                        # Try small scroll to trigger visibility logic if needed
                        await self.browser.scroll("down", 200)
                
            if not success or not html:
               return {"error": "Failed to load any search engine"}

            # 2. Extract results + content
            if deep:
                # Try to find the first real result link
                links = await self.browser.get_links()
                # Expanded target link finding
                target_link = None
                for link in links:
                    u = link.get('url', '')
                    text = link.get('text', '').lower()
                    
                    # Exclude navigation/system links
                    if any(x in u for x in ['duckduckgo.com', 'google.com', 'bing.com', 'googleadservices.com']):
                        continue
                    if any(x in text for x in ['privacy', 'settings', 'help', 'about']):
                        continue
                    if not u.startswith('http'):
                        continue
                    if len(text) < 5:
                        continue
                        
                    target_link = u
                    break
                
                if target_link:
                    logger.info("🌊 Deep Dive: Navigating to %s", target_link)
                    await self.browser.browse(target_link)
                    await self.browser.scroll("down", 500)
                    content = await self.browser.read_content()
                    return {
                        "ok": True,
                        "result": content,
                        "source": target_link,
                        "mode": "deep"
                    }

            # 3. Fallback/Standard: Read search page
            html = await self.browser.page.content()
            
            def parse_html(raw_html: str) -> List[Dict[str, str]]:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw_html, 'html.parser')
                results_data = []
                
                # DuckDuckGo selectors
                items = soup.select(".result__body") or soup.select(".nrn-react-div")
                for item in items[:8]:
                    title_elem = item.select_one(".result__a") or item.select_one("h2 a")
                    snippet_elem = item.select_one(".result__snippet") or item.select_one(".result__body")
                    
                    if title_elem and snippet_elem:
                        results_data.append({
                            "title": title_elem.get_text(strip=True),
                            "url": title_elem.get("href"),
                            "snippet": snippet_elem.get_text(strip=True)
                        })
                
                return results_data
                
            import asyncio
            results = await asyncio.to_thread(parse_html, html)
            
            if not results:
                # Fallback to general text if specialized parsing failed
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    element.extract()
                return {
                    "ok": True,
                    "result": soup.get_text(separator=' ', strip=True)[:8000],
                    "source": "duckduckgo",
                    "mode": "raw_text_hybrid"
                }
            
            return {
                "ok": True,
                "results": results,
                "source": "duckduckgo",
                "mode": "structured"
            }
            
        except Exception as e:
            logger.error("Web search failed: %s", e)
            return {"error": str(e)}

    # Lifecycle hooks
    async def on_stop_async(self):
        await self.browser.close()

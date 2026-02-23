import logging
from typing import Any, Dict

from core.phantom_browser import PhantomBrowser
from core.skill_registry import skill_registry

logger = logging.getLogger("Skills.WebSearch")

from pydantic import BaseModel, Field

from core.skills.base_skill import BaseSkill


class SearchInput(BaseModel):
    query: str = Field(..., description="The search query to execute. Be specific.")

class WebSearchSkill(BaseSkill):
    """Real web search capability into Aura using PhantomBrowser (Playwright).
    """

    name = "search_web"
    description = "Search the open web for information. Use this to find facts, news, or deep dive on topics."
    input_model = SearchInput
    
    def __init__(self):
        self.browser = PhantomBrowser(visible=False)

    async def execute(self, params: SearchInput, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a web search.
        """
        # If passed as dict (legacy path before full migration), validating it manually or relying on previous check?
        # Ideally robust registry handles conversion. For now, assume it might be dict or model.
        if isinstance(params, dict):
             # Manual validation or load
             try:
                 params = SearchInput(**params)
             except Exception as e:
                 return {"error": f"Invalid input: {e}"}
                 
        query = params.query
        
        logger.info("🔍 Searching web for: %s", query)
        
        try:
            # 1. Start browser if needed
            if not self.browser.is_active:
                await self.browser._start_browser()
            
            # 2. Search DuckDuckGo (privacy first!)
            url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            success = await self.browser.browse(url)
            
            if not success:
               return {"error": "Failed to load search engine"}

            # 3. Read results
            # Wait for results
            await self.browser._human_delay(1.0, 2.0)
            # 4. Read results
            content = await self.browser.read_content()
            
            # Legacy sanitization removed (A+ hardening: sanitization handled by IntentRouter/LLM)

            return {
                "ok": True,
                "result": content[:2000],  # Limit context
                "source": "duckduckgo"
            }
            
        except Exception as e:
            logger.error("Web search failed: %s", e)
            return {"error": str(e)}

# Change: Register the skill instance or class? 
# The registry expects a class.
# But wait, skill_registry.register takes a CLASS.
# And load_skill instantiates it.
# So we need to exposing the CLASS.

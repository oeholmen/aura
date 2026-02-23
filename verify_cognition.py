
import asyncio
import logging
import httpx
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from core.config import config
from core.brain.llm.ollama_client import RobustOllamaClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VerifyCognition")

async def test_ollama_connectivity():
    logger.info(f"Testing connectivity to Ollama at {config.llm.base_url}")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{config.llm.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m['name'] for m in resp.json().get('models', [])]
                logger.info(f"✅ Connected to Ollama. Available models: {models}")
                return models
            else:
                logger.error(f"❌ Failed to connect to Ollama: HTTP {resp.status_code}")
                return []
    except Exception as e:
        logger.error(f"❌ Connection error: {e}")
        return []

async def test_generation():
    logger.info(f"Testing generation with model: {config.llm.model}")
    client = RobustOllamaClient(model=config.llm.model)
    try:
        # Simple health check generate
        resp = await client.generate("Hello, are you online?")
        if resp:
            logger.info(f"✅ Generation successful: {resp[:50]}...")
            return True
        else:
            logger.error("❌ Generation returned empty response")
            return False
    except Exception as e:
        logger.error(f"❌ Generation failed: {e}")
        return False

async def main():
    models = await test_ollama_connectivity()
    if not models:
        sys.exit(1)
        
    if config.llm.model not in models:
        logger.warning(f"⚠️ Configured model {config.llm.model} is not in available models!")
    
    gen_ok = await test_generation()
    if gen_ok:
        logger.info("🎉 Verification Successful: Aura's brain is active.")
    else:
        logger.error("💀 Verification Failed: Aura is still stalled.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

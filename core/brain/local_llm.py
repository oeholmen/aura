import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from core.config import config

logger = logging.getLogger("Aura.LocalLLM")

# Configurable timeouts (Increased for Llama 3.1 8b)
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 300.0  # 5 minutes to allow slow model loading
_DEFAULT_TIMEOUT = httpx.Timeout(connect=_CONNECT_TIMEOUT, read=_READ_TIMEOUT, write=30.0, pool=10.0)


class LocalBrain:
    """Sovereign Intelligence Bridge connecting to local Ollama instance.
    v6.1: Retry logic, proper client lifecycle, configurable timeouts.
    """
    
    def __init__(self, model_name: str = None):
        self.base_url = config.llm.base_url
        self.model = model_name or config.llm.model
        self.timeout = getattr(config.llm, "timeout", 300)
        self._client = None
        self._warmed = False
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until = 0.0
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=_DEFAULT_TIMEOUT
            )
        return self._client

    # --- Lifecycle ---
    async def close(self):
        """Close the underlying httpx client to release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # --- Health Checks ---
    def check_health(self) -> bool:
        """Sovereign health check (Synchronous — uses httpx sync client)."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=3) as client:
                response = client.get("/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def check_health_async(self) -> bool:
        """Sovereign health check (Async)."""
        try:
            response = await self.client.get("/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False
    
    async def warmup(self) -> bool:
        """v6.0: Pre-warm the model by sending a minimal generate request.
        This loads the model into GPU memory for faster first-response.
        """
        if self._warmed:
            return True
        try:
            logger.info("🔥 Warming up model: %s", self.model)
            response = await self.client.post("/api/generate", json={
                "model": self.model,
                "prompt": "Hello",
                "stream": False,
                "options": {"num_predict": 1}
            }, timeout=120)
            response.raise_for_status()
            self._warmed = True
            logger.info("🔥 Model %s warmed up successfully", self.model)
            return True
        except Exception as e:
            logger.warning("Model warmup failed: %s", e)
            return False
    
    # --- Circuit Breaker ---
    def _check_circuit(self) -> bool:
        """Check if circuit breaker allows the call."""
        if self._circuit_open:
            if time.time() < self._circuit_open_until:
                logger.warning("Circuit breaker OPEN — skipping LLM call")
                return False
            # Half-open: allow one attempt
            self._circuit_open = False
        return True
    
    def _record_success(self):
        """Record a successful call."""
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until = 0.0
    
    def _record_failure(self):
        """Record a failed call. Opens circuit after 5 consecutive failures."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self._circuit_open = True
            self._circuit_open_until = time.time() + 30.0  # 30s recovery
            logger.error("Circuit breaker OPENED after %s failures. Cooldown: 30s", self._consecutive_failures)
    
    # --- Generation ---
    # --- Helper: DeepSeek Think Filtering ---
    def _strip_think_tags(self, text: str) -> str:
        """Remove <think>...</think> blocks from static text."""
        import re
        # Remove balanced tags
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove stray closing tags if any
        cleaned = cleaned.replace('</think>', '')
        # Remove stray opening tags if at the end (incomplete thought)
        cleaned = cleaned.replace('<think>', '')
        return cleaned.strip()

    # --- Generation ---
    async def generate(self, prompt: str, system_prompt: Optional[str] = None, options: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Send a generation request to the local Ollama instance (Async).
        v13B: Auto-strips <think> tags for DeepSeek R1.
        """
        if not self._check_circuit():
            return "Error: Local brain temporarily unavailable (circuit breaker open)."
        
        # v26 FIX: Hard Memory Ceiling (4k Context / 512 Predict)
        final_options = {
            "temperature": config.llm.temperature,
            "num_predict": 512, # Verbosisty Cap
            "num_ctx": 4096    # Context Ceiling
        }
        if options:
            final_options.update(options)

        url = "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": final_options
        }
        if system_prompt:
            payload["system"] = system_prompt
        
        last_error = None
        for attempt in range(2):  # 1 retry
            try:
                logger.info("Ollama Request: %s | Prompt len: %d | Attempt: %d", self.model, len(prompt), attempt + 1)
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                self._record_success()
                
                # Filter DeepSeek thinking
                raw_response = data.get("response", "").strip()
                return self._strip_think_tags(raw_response)
                
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                if attempt == 0:
                    logger.warning("Transient LLM error (retrying in 1s): %s", e)
                    await asyncio.sleep(1.0)
                    continue
            except Exception as e:
                last_error = e
                break
        
        self._record_failure()
        logger.error("Local LLM Error: %s", last_error)
        return f"Error: Local brain (Ollama) is unreachable. {str(last_error)}"

    async def generate_text_stream_async(self, prompt: str, system_prompt: Optional[str] = None, cancel_event=None, options: Optional[Dict[str, Any]] = None, **kwargs):
        """Stream tokens from the local Ollama instance.
        v13B: Filters <think> blocks in real-time.
        """
        if not self._check_circuit():
            yield "Error: Local brain temporarily unavailable."
            return
        
        # v26 FIX: Hard Memory Ceiling (4k Context / 512 Predict)
        final_options = {
            "temperature": config.llm.temperature,
            "num_predict": 512, # Verbosisty Cap
            "num_ctx": 4096    # Context Ceiling
        }
        if options:
            final_options.update(options)

        url = "/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "30m",
            "options": final_options
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            # Thinking State Machine
            in_think_block = False
            buffer = ""
            
            async with self.client.stream("POST", url, json=payload, timeout=_DEFAULT_TIMEOUT) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event and cancel_event.is_set():
                        logger.info("Stream cancelled by caller")
                        break
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("response", "")
                        
                        if data.get("done"):
                            break
                            
                        # Stream Filtering Logic for <think>
                        if in_think_block:
                            if "</think>" in token:
                                in_think_block = False
                                # Emit whatever follows the closing tag
                                parts = token.split("</think>")
                                if len(parts) > 1:
                                    yield parts[1]
                            continue # Skip token while thinking
                            
                        if "<think>" in token:
                            in_think_block = True
                            # If there was content before the tag, emit it
                            parts = token.split("<think>")
                            if parts[0]:
                                yield parts[0]
                            continue

                        # Check for split tags (simple heuristic: buffering)
                        # For R1, <think> is almost always at the start or distinct tokens.
                        # Complex split-tag handling omitted for performance, relying on token boundaries.
                            
                        if token:
                            # UX Tuning: 50% slower stream for readability
                            await asyncio.sleep(0.03) 
                            yield token
                            
                    except json.JSONDecodeError:
                        continue
            self._record_success()
        except Exception as e:
            self._record_failure()
            logger.error("Streaming Error: %s", e)
            yield f" [Error: Sovereign stream interrupted: {str(e)}]"

    # --- Chat ---
    async def chat(self, messages: List[Dict[str, str]], options: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Async chat interface for the orchestrator.
        v13B: Auto-strips <think> tags.
        """
        if not self._check_circuit():
            return "Error: Local brain temporarily unavailable (circuit breaker open)."
        
        # v26 FIX: Hard Memory Ceiling (4k Context / 512 Predict)
        final_options = {
            "temperature": config.llm.temperature,
            "num_predict": 512, # Verbosisty Cap
            "num_ctx": 4096    # Context Ceiling
        }
        if options:
             final_options.update(options)
        
        url = "/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": final_options
        }
        
        last_error = None
        for attempt in range(2):  # 1 retry
            try:
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                self._record_success()
                
                # Filter DeepSeek thinking
                raw_response = data.get("message", {}).get("content", "").strip()
                return self._strip_think_tags(raw_response)
                
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                if attempt == 0:
                    logger.warning("Transient chat error (retrying in 1s): %s", e)
                    await asyncio.sleep(1.0)
                    continue
            except Exception as e:
                last_error = e
                break
        
        self._record_failure()
        logger.error("Local Chat Error: %s", last_error)
        return "Internal Error: Sovereign cognitive stream interrupted."

    async def chat_stream_async(self, messages: List[Dict[str, str]], cancel_event=None, options: Optional[Dict[str, Any]] = None, **kwargs):
        """Stream chat tokens from the local Ollama instance.
        v13B: Filters <think> blocks in real-time.
        """
        if not self._check_circuit():
            yield "Error: Local brain temporarily unavailable."
            return
        
        # v26 FIX: Hard Memory Ceiling (4k Context / 512 Predict)
        final_options = {
            "temperature": config.llm.temperature,
            "num_predict": 512, # Verbosisty Cap
            "num_ctx": 4096    # Context Ceiling
        }
        if options:
            final_options.update(options)

        url = "/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "30m",
            "options": final_options
        }

        try:
            # Thinking State Machine
            in_think_block = False
            
            async with self.client.stream("POST", url, json=payload, timeout=_DEFAULT_TIMEOUT) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event and cancel_event.is_set():
                        logger.info("Chat stream cancelled by caller")
                        break
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        
                        if data.get("done"):
                            break
                            
                        # Stream Filtering Logic for <think>
                        if in_think_block:
                            if "</think>" in token:
                                in_think_block = False
                                # Emit a clearing signal or just continue (UI appends, so we can't delete)
                                # Strategy: Just let the real text follow.
                                # Future: Emit a special "clear_thought" event if UI supports it.
                                
                                # Emit whatever follows the closing tag
                                parts = token.split("</think>")
                                if len(parts) > 1:
                                    yield parts[1]
                            continue # Skip token while thinking
                            
                        if "<think>" in token:
                            in_think_block = True
                            # Signal to user that work is happening
                            yield "*Thinking...* " 
                            
                            # If there was content before the tag, emit it
                            parts = token.split("<think>")
                            if parts[0]:
                                yield parts[0]
                            continue
                            
                        if token:
                            # UX Tuning: 50% slower stream for readability
                            await asyncio.sleep(0.03)
                            yield token
                            
                    except json.JSONDecodeError:
                        continue
            self._record_success()
        except Exception as e:
            self._record_failure()
            logger.error("Chat Streaming Error: %s (%s)", e, type(e).__name__)
            yield f" [Error: Sovereign chat stream interrupted: {type(e).__name__}: {str(e) or repr(e)}]"

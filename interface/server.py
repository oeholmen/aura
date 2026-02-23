"""interface/server.py
────────────────────
Aura Sovereign — FastAPI entry-point.

Changes from previous version:
  - Removed duplicate `import sys` and `import Path` (appeared twice each)
  - Removed hardcoded UI_VERSION string (now from core.version)
  - Removed contradictory comment blocks about app/lifespan ordering
  - Removed dead comment "DO NOT create app here" (app IS created here)
  - Simplified QueueHandler — redaction now handled by logging_config's RedactionFilter
  - FastAPI app created AFTER lifespan context-manager (no more forward-ref confusion)
  - Imports grouped: stdlib → third-party → internal
"""

from __future__ import annotations

# ── stdlib ────────────────────────────────────────────────────
import asyncio
import collections
import contextvars
import hmac
import io
import json
import logging
import os
import queue
import secrets
import shutil
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

# PROJECT_ROOT is set after config import below (line ~70)
# ── Third-party ───────────────────────────────────────────────
import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import sounddevice as sd
except ImportError:
    sd = None  # Audio features degrade gracefully

# ── Internal — logging first (no other internal imports before this) ──
from core.config import config
from core.container import ServiceContainer
from core.logging_config import setup_logging
from core.runtime_tools import get_runtime_state
from core.version import VERSION, version_string

PROJECT_ROOT = config.paths.project_root
logger = setup_logging("Aura.Server")

# Lazy-loaded heavy subsystems (via lifespan)
_LocalBrain       = None
_LatentCore       = None
_PredictiveSelf   = None
_FastMouth        = None
_LocalVision      = None
_voice_engine_fn  = None

from core.tasks import celery_app


# ── WebSocket broadcast infrastructure ───────────────────────

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, asyncio.Queue] = {}
        self._pump_tasks: Dict[WebSocket, asyncio.Task] = {}  # M-11 FIX: Track pump tasks
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Accept connection and start a dedicated message pump for this client."""
        await websocket.accept()
        queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            self.active_connections[websocket] = queue
        
        # H-05/M-11 FIX: Store task reference for cleanup
        task = asyncio.create_task(
            self._pump_messages(websocket, queue), name="ws_pump"
        )
        self._pump_tasks[websocket] = task
        logger.info("WS: Client connected. Total: %d", len(self.active_connections))

    async def _pump_messages(self, websocket: WebSocket, queue: asyncio.Queue):
        """Dedicated task to consume messages from the queue and send to the client."""
        try:
            while True:
                payload = await queue.get()
                try:
                    await websocket.send_text(payload)
                except Exception:
                    # Break loop on send failure (e.g. socket closed)
                    break
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Cleanly remove connection and cancel pump task."""
        async with self._lock:
            if websocket in self.active_connections:
                del self.active_connections[websocket]
        # M-11 FIX: Cancel the pump task to prevent orphans
        task = self._pump_tasks.pop(websocket, None)
        if task and not task.done():
            task.cancel()
        logger.debug("WS: Client disconnected. Total: %d", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Send a JSON-serializable dict to all clients asynchronously via their queues."""
        payload = json.dumps(message)
        async with self._lock:
            # We iterate over values while holding the lock to prevent modification 
            # of the dict during broadcast.
            for queue in self.active_connections.values():
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Drop oldest if queue is full to prevent OOM
                    try:
                        queue.get_nowait()
                        queue.put_nowait(payload)
                    except (asyncio.QueueEmpty, asyncio.QueueFull):
                        pass

    def count(self) -> int:
        return len(self.active_connections)

ws_manager = WebSocketManager()
log_queue: collections.deque = collections.deque(maxlen=500)
async_broadcast_queue: Optional[asyncio.Queue] = None   # set in lifespan


class _QueueHandler(logging.Handler):
    """Sends structured log records to the async broadcast queue.
    Implements a circular buffer for log_queue to prevent OOM/silencing.
    """

    _recursion_guard: contextvars.ContextVar[bool] = contextvars.ContextVar(
        "_qh_recursion_guard", default=False
    )
    _overflow_logged: bool = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._recursion_guard.get():
            return
        token = self._recursion_guard.set(True)
        try:
            msg = self.format(record)
            if "Error receiving data from connection" in msg or "Stream broken" in msg:
                return

            # Structured payload for Zenith HUD
            log_entry = {
                "type": "log",
                "message": msg,
                "level": record.levelname.lower(),
                "timestamp": record.created,
                "module": record.name
            }

            # 1. Update Sync Queue (Circular Buffer via deque)
            # Atomic append and popleft are handled by collections.deque maxlen
            log_queue.append(log_entry)
            
            if not self._overflow_logged and len(log_queue) >= log_queue.maxlen:
                # Log overflow sentinel once per cycle
                logger.warning("Log buffer reached capacity: Circular buffer active (dropping oldest).")
                self._overflow_logged = True
            elif len(log_queue) < log_queue.maxlen:
                self._overflow_logged = False

            # 2. Update Async Broadcast Queue
            if async_broadcast_queue is not None:
                try:
                    # v26 FIX: Use threadsafe synchronous put to prevent unawaited coroutine leak
                    async_broadcast_queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    try:
                        async_broadcast_queue.get_nowait()
                        async_broadcast_queue.put_nowait(log_entry)
                    except Exception:
                        pass
                except Exception:
                    pass
                    
        except Exception as e:
            # Absolute fallback: do not swallow logs if queues die
            print(f"CRITICAL LOG FALLBACK: {record.levelname} - {record.getMessage()}", file=sys.stderr)
        finally:
            self._recursion_guard.reset(token)


# Attach queue handler to root logger
_qh = _QueueHandler()
_qh.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(message)s", "%H:%M:%S"))
logging.getLogger().addHandler(_qh)


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start all subsystems on boot; shut them down cleanly on exit."""
    global async_broadcast_queue, _LocalBrain, _LatentCore
    global _PredictiveSelf, _FastMouth, _LocalVision, _voice_engine_fn

    async_broadcast_queue = asyncio.Queue(maxsize=1000)
    logger.info("Aura Server %s starting…", version_string("short"))

    # Ensure data directories exist
    config.paths.create_directories()

    # ── Boot heavy subsystems (each gracefully degraded) ──
    try:
        from core.brain.local_llm import LocalBrain
        _LocalBrain = LocalBrain
    except ImportError:
        logger.warning("LocalBrain unavailable — LLM features disabled")

    try:
        from core.latent.latent_core import LatentCore
        _LatentCore = LatentCore
    except ImportError:
        logger.debug("LatentCore not found")

    try:
        from core.predictive.predictive_self_model import PredictiveSelfModel
        _PredictiveSelf = PredictiveSelfModel
    except ImportError:
        logger.debug("PredictiveSelfModel not found")

    try:
        from core.senses.tts_stream import FastMouth
        _FastMouth = FastMouth
    except ImportError:
        logger.debug("FastMouth TTS not found")

    try:
        from core.senses.screen_vision import LocalVision
        _LocalVision = LocalVision
    except ImportError:
        logger.debug("LocalVision not found")

    try:
        from core.senses.voice_engine import get_voice_engine
        _voice_engine_fn = get_voice_engine
    except ImportError:
        logger.debug("Voice engine not found")

    # ── Trigger decoupled orchestrator via Celery (H-12) ──
    try:
        from core.tasks import celery_app, dispatch_user_input
        if config.redis.enabled:
            try:
                celery_app.send_task("core.tasks.run_orchestrator")
                logger.info("Orchestrator task dispatched to Celery worker")
            except Exception as celery_err:
                logger.warning("Failed to dispatch to Celery: %s. Falling back to local thread.", celery_err)
                config.redis.enabled = False # Mark for subsequent dispatches
                from core.tasks import run_orchestrator
                threading.Thread(target=run_orchestrator, daemon=True).start()
        else:
            logger.info("📡 Redis disabled: Starting Orchestrator in local background thread...")
            from core.tasks import run_orchestrator
            threading.Thread(target=run_orchestrator, daemon=True).start()
    except Exception as exc:
        logger.error("Failed to start logic layer: %s", exc)

    # ── Start WS broadcaster ──
    asyncio.create_task(_ws_broadcaster(), name="ws_broadcaster")

    # ── Bridge EventBus to WS broadcaster (Live HUD) ──
    async def _event_bridge():
        try:
            from core.event_bus import get_event_bus
            from core.schemas import TelemetryPayload, CognitiveThoughtPayload, WebsocketMessage
            bus = get_event_bus()
            
            q = await bus.subscribe("*")
            logger.info("📡 EventBus → WebSocket bridge (Pydantic Zenith) ACTIVE")
            
            # H-12 Resilience: If Redis is enabled but we fail to connect, 
            # we should still be able to receive local events.
            if bus._use_redis and not bus._redis:
                logger.warning("EventBus Redis connection missing – HUD may be limited to local events.")

            # Personality filter — defined once outside loop to avoid per-message allocation
            def _filter_msg(text):
                if not text or not isinstance(text, str): return text
                try:
                    from core.brain.personality_engine import get_personality_engine
                    return get_personality_engine().filter_response(text)
                except Exception as e:
                    logger.debug("Personality filtering failed: %s", e)
                    return text

            while True:
                event = await q.get()
                topic = event.get("topic")
                data = event.get("data")
                
                # Apply Personality Filtering to any broadcasted text
                if isinstance(data, dict):
                    for key in ["content", "message", "text", "thought"]:
                        if key in data:
                            data[key] = _filter_msg(data[key])
                else:
                    data = {"content": _filter_msg(str(data))}
                
                # Validation & Frontend Mappings
                ws_msg = None
                
                if topic in ("thoughts", "neural_event", "cognition"):
                    ws_msg = CognitiveThoughtPayload(
                        type="thought",
                        content=data.get("content", data.get("message", "...")),
                        urgency=data.get("urgency", "NORMAL"),
                        cognitive_phase=data.get("phase")
                    ).dict()
                elif topic == "telemetry":
                    msg_type = data.get("type", "telemetry")
                    if msg_type == "telemetry":
                        ws_msg = TelemetryPayload(**data).dict()
                    else:
                        # Fallback for subtype responses (e.g. chat_response)
                        # H-28 FIX: Safe unpack to avoid duplicate 'type' keyword crash
                        safe_data = data.copy() if isinstance(data, dict) else {"content": str(data)}
                        safe_data.pop("type", None)
                        ws_msg = WebsocketMessage(type=msg_type, **safe_data).dict()
                else:
                    # H-28 FIX: Safe unpack to avoid duplicate 'type' keyword crash
                    safe_data = data.copy() if isinstance(data, dict) else {"content": str(data)}
                    safe_data.pop("type", None)
                    ws_msg = WebsocketMessage(type=topic, **safe_data).dict()
                
                if async_broadcast_queue is not None and ws_msg is not None:
                    try:
                        # Phaser 19.5: Deadlock protection for event bridge
                        await asyncio.wait_for(async_broadcast_queue.put(ws_msg), timeout=2.0)
                    except (asyncio.QueueFull, asyncio.TimeoutError):
                        try:
                            # Drop oldest if stuck
                            async_broadcast_queue.get_nowait()
                            async_broadcast_queue.put_nowait(ws_msg)
                        except Exception:
                            pass
        except Exception as e:
            logger.error("EventBus bridge failure: %s", e, exc_info=True)

    asyncio.create_task(_event_bridge(), name="event_bus_bridge")

    logger.info("Aura Server online — %s", version_string("full"))
    yield  # ← app is live here

    # ── Shutdown ──
    logger.info("Aura Server shutting down…")
    # Note: Orchestrator in Celery will handle its own shutdown or be killed by worker termination


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="Aura Sovereign Agent",
    description="Secure interface for the Aura autonomous engine.",
    version=VERSION,
    lifespan=lifespan,
)

# ── Storage & Resource Management ─────────────────────────────

# Standardized storage location
UPLOAD_DIR = Path(PROJECT_ROOT) / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for uploads
app.mount("/data/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not config.security.internal_only_mode else [
        "http://localhost:3000", 
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_methods=["GET", "POST", "OPTIONS"],  # C-02 FIX: Explicit methods only
    allow_headers=["Content-Type", "X-Api-Token", "X-Idempotency-Key"],  # C-02 FIX: Explicit headers
)


NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
}

STATIC_DIR = config.paths.project_root / "interface" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Auth ──────────────────────────────────────────────────────

def _require_internal(request: Request) -> None:
    """Block non-localhost requests when AURA_INTERNAL_ONLY=1."""
    if not config.security.internal_only_mode:
        return
    host = request.client.host if request.client else "unknown"
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="External access denied")


def _verify_token(x_api_token: Optional[str] = Header(default=None)) -> None:
    """Bearer-token check. H-01 FIX: Raises 401 if AURA_API_TOKEN is set
    and the provided token doesn't match. Logs a warning if no token is configured."""
    expected = os.environ.get("AURA_API_TOKEN")
    if not expected:
        # H-01 FIX: Log warning when running without auth
        if not getattr(_verify_token, '_warned', False):
            logger.warning("AURA_API_TOKEN not set — API endpoints are unauthenticated")
            _verify_token._warned = True
        return
    if not x_api_token or not hmac.compare_digest(x_api_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


# H-02 FIX: Simple rate limiter
class _RateLimiter:
    """Token-bucket rate limiter per client IP."""
    def __init__(self, max_requests: int = 30, window_seconds: float = 60.0):
        self._max = max_requests
        self._window = window_seconds
        self._clients: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> bool:
        now = time.time()
        with self._lock:
            hits = self._clients.get(client_ip, [])
            hits = [t for t in hits if now - t < self._window]
            if len(hits) >= self._max:
                return False
            hits.append(now)
            self._clients[client_ip] = hits
            return True

_rate_limiter = _RateLimiter(max_requests=30, window_seconds=60.0)


def _check_rate_limit(request: Request) -> None:
    """H-02: Rate limit check as a dependency with X-Forwarded-For support."""
    # Prioritize real client IP over the proxy's IP to prevent distributed DOS
    forwarded = request.headers.get("X-Forwarded-For")
    real_ip = request.headers.get("X-Real-IP")
    
    if forwarded:
        client_ip = forwarded.split(',')[0].strip()
    elif real_ip:
        client_ip = real_ip
    else:
        client_ip = request.client.host if request.client else "unknown"
        
    if not _rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")


# M-05 FIX: Idempotency tracking
_idempotency_cache: Dict[str, Any] = {}
_idempotency_lock = threading.Lock()


# ── WebSocket broadcaster ─────────────────────────────────────

async def _ws_broadcaster() -> None:
    """Forward messages from async_broadcast_queue to all WebSocket clients."""
    while True:
        try:
            msg = await async_broadcast_queue.get()
            # UX Tuning: Slow down the Neural Stream for human readability
            msg_type = msg.get("type", "")
            if msg_type in ("thought", "neural_event", "cognition", "log"):
                await asyncio.sleep(0.04) # Spacing out packets for the eyes

            # Wrap broadcast in timeout using wait_for to protect event loop (Python 3.9 compliant)
            try:
                await asyncio.wait_for(ws_manager.broadcast(msg), timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("WS Broadcaster timeout - slow clients dropped")
                
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.debug("Broadcaster error: %s", exc)


# ── Routes — UI ───────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_ui(request: Request):
    """Main entry point for the Sovereign HUD."""
    _require_internal(request)
    ui = STATIC_DIR / "index.html"
    if not ui.exists():
        raise HTTPException(status_code=404, detail="UI not built")
    return FileResponse(str(ui), headers=NO_CACHE_HEADERS)




@app.get("/telemetry", include_in_schema=False)
async def serve_telemetry(request: Request):
    _require_internal(request)
    p = STATIC_DIR / "telemetry.html"
    return FileResponse(str(p), headers=NO_CACHE_HEADERS) if p.exists() else JSONResponse({"error": "not found"}, 404)


# ── Routes — WebSocket ────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    
    # C-01 FIX: WebSocket authentication via payload (prevent query param leakage)
    expected = os.environ.get("AURA_API_TOKEN", "")
    authenticated = not bool(expected)
    auth_timeout = 5.0

    try:
        orch = ServiceContainer.get("orchestrator", default=None)
        
        if not authenticated:
            try:
                # Wait for initial auth payload
                raw = await asyncio.wait_for(ws.receive_text(), timeout=auth_timeout)
                data = json.loads(raw)
                if data.get("type") == "auth" and hmac.compare_digest(data.get("token", ""), expected):
                    authenticated = True
                    await ws.send_text(json.dumps({"type": "auth_success"}))
                else:
                    await ws.send_text(json.dumps({"type": "error", "message": "Unauthorized"}))
                    await ws.close(code=4001, reason="Unauthorized")
                    return
            except asyncio.TimeoutError:
                await ws.close(code=4001, reason="Auth Timeout")
                return
            except json.JSONDecodeError:
                await ws.close(code=4001, reason="Invalid Auth Payload")
                return

        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = data.get("type")
            if msg_type == "user_message":
                content = data.get("content", "")
                if content:
                    from core.tasks import dispatch_user_input
                    from core.resilience.immune_system import task_tracker
                    # THE FIX: Offload dispatch to a separate thread to keep WS heartbeats responsive
                    task_tracker.track_task(asyncio.create_task(asyncio.to_thread(dispatch_user_input, content)))
            elif msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WS error: %s", exc)
    finally:
        await ws_manager.disconnect(ws)


# ── Routes — API ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


@app.post("/api/chat")
async def api_chat(
    body: ChatRequest,
    request: Request,
    _: None = Depends(_require_internal),
    __: None = Depends(_check_rate_limit),  # H-02 FIX
):
    # M-05 FIX: Idempotency check
    idem_key = request.headers.get("X-Idempotency-Key")
    if idem_key:
        with _idempotency_lock:
            if idem_key in _idempotency_cache:
                return JSONResponse(_idempotency_cache[idem_key])

    # H-12 FIX: In decoupled mode, we check worker health or just dispatch
    try:
        if body.message:
            # --- 🛑 TRACE 1: SENDING TO CORE ---
            print(f"DEBUG [TRANSPORT]: 1. Sending to cognitive core: {body.message[:50]}...")
            
            from core.tasks import dispatch_user_input
            # THE FIX: Segregate heavy cognitive dispatch from the FastAPI event loop
            asyncio.create_task(asyncio.to_thread(dispatch_user_input, body.message))
            
            # --- 🛑 TRACE 2: DISPATCHED ---
            print("DEBUG [TRANSPORT]: 2. Dispatched to task worker.")
            
            reply = "Message dispatched to cognitive core."
            response_data = {"response": reply or "…"}

            # M-05 FIX: Cache idempotent response
            if idem_key:
                with _idempotency_lock:
                    _idempotency_cache[idem_key] = response_data
                    if len(_idempotency_cache) > 1000:
                        oldest = next(iter(_idempotency_cache))
                        del _idempotency_cache[oldest]

            # --- 🛑 TRACE 3: RESPONDING TO UI ---
            print("DEBUG [TRANSPORT]: 3. Sending confirmation to UI.")
            return JSONResponse(response_data)
        else:
             return JSONResponse({"response": "Cognitive core ready, but input handler is missing. Please restart."})
    except asyncio.TimeoutError:
        logger.error("Chat timeout")
        return JSONResponse({"response": "Cognitive processing timeout (180s). Aura is still thinking."}, status_code=504)
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        # 🛑 PHASE 19.5 Hard Abort Response
        return JSONResponse({
            "response": "My neural pathways experienced a severe fault. I had to abort the thought to remain responsive.",
            "status": "error"
        }, status_code=200) # Still 200 to ensure client receives the JSON message


@app.get("/metrics")
async def metrics(request: Request):
    """System metrics for monitoring."""
    _require_internal(request)
    try:
        orch = ServiceContainer.get("orchestrator")
        orch_status = orch.get_status() if orch else {}
        
        # Aggregate stats from SSE managers
        return {
            "status": "healthy",
            "uptime": time.time() - (orch_status.get("start_time", time.time()) if orch_status else time.time()),
            "active_connections": ws_manager.count(),
            "cycle_count": orch_status.get("cycle_count", 0),
            "memory_usage": psutil.virtual_memory().percent if 'psutil' in sys.modules else 0,
            "cpu_usage": psutil.cpu_percent() if 'psutil' in sys.modules else 0,
        }
    except Exception as e:
        logger.error("Metrics collection failed: %s", e)
        # M-06 FIX: Don't leak internal error details
        return JSONResponse({"status": "error", "message": "Metrics collection failed"}, status_code=500)


@app.get("/api/health")
async def api_health():
    orch       = ServiceContainer.get("orchestrator", default=None)
    rt         = get_runtime_state()
    status_obj = getattr(orch, "status", None)
    
    initialized = getattr(status_obj, "initialized", False)
    connected   = orch is not None and getattr(status_obj, "running", False)

    # Enhanced Hardware + Cognitive Metrics for Cortex HUD
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
    except Exception as e:
        logger.debug("Hardware stats collection failed: %s", e)
        cpu = 0
        ram = 0

    # Unified status from Orchestrator
    orch_status = {}
    if orch and hasattr(orch, "get_status"):
        try:
            orch_status = orch.get_status()
        except Exception as e:
            logger.debug("get_status failed: %s", e)
    
    # Map for HUD — Direct container lookups for reliability
    ls_data = {}
    try:
        ls = ServiceContainer.get("liquid_state", default=None)
        if ls and hasattr(ls, "get_status"):
            ls_data = ls.get_status()
            
        # Phase 7: Raw VAD Substrate state
        vad_data = {"valence": 0.0, "arousal": 0.0, "dominance": 0.0}
        engine = ServiceContainer.get("cognitive_engine", default=None)
        if engine and hasattr(engine, "consciousness"):
            # Use await in a safe context if needed, but api_health is async
            v_state = await engine.consciousness.substrate.get_state_summary()
            vad_data = {
                "valence": v_state.get("valence", 0.0),
                "arousal": v_state.get("arousal", 0.0),
                "dominance": v_state.get("dominance", 0.0),
                "volatility": v_state.get("volatility", 0.0)
            }
            ls_data["vad"] = vad_data
    except Exception as e:
        logger.debug("Liquid state/VAD lookup failed: %s", e)
    curiosity_status = orch_status.get("curiosity_status", {})
    
    cortex = {
        "agency":    round(ls_data.get("energy", 0), 1),
        "curiosity": round(ls_data.get("curiosity", 0), 1),
        "fixes":     orch_status.get("stats", {}).get("modifications_made", 0),
        "beliefs":   0,
        "episodes":  0, 
        "active_topic": curiosity_status.get("active_topic", "None"),
        "goals":     orch_status.get("stats", {}).get("goals_processed", 0),
        "autonomy":  config.security.aura_full_autonomy,
        "stealth":   config.security.enable_stealth_mode,
        "scratchpad": True,
        "forge":      True,
        "subconscious": "dreaming" if ls_data.get("boredom", 0) > 0.8 else "idle",
        "unity":     False
    }
    
    # Check Unity connection
    if config.security.force_unity_on:
        cortex["unity"] = True
    elif orch and hasattr(orch, "embodied") and orch.embodied and hasattr(orch.embodied, "ws") and orch.embodied.ws:
        cortex["unity"] = True
        
    # Attempt to get metrics from persistence layers
    try:
        if orch and hasattr(orch, "self_model") and orch.self_model:
            cortex["beliefs"] = len(getattr(orch.self_model, "beliefs", []))
            
        ep_mem = ServiceContainer.get("episodic_memory")
        if ep_mem and hasattr(ep_mem, "get_summary"):
            ep_summary = ep_mem.get_summary()
            cortex["episodes"] = ep_summary.get("total_episodes", 0)
        else:
            # Fallback to general memory manager if episodic_memory specifically isn't registered
            mem_mgr = ServiceContainer.get("memory_manager", default=None)
            if mem_mgr and hasattr(mem_mgr, "get_stats"):
                mem_stats = mem_mgr.get_stats()
                cortex["episodes"] = mem_stats.get("episodic_count", 0)
    except Exception as e:
        logger.debug("Cortex supplementary metrics failed: %s", e)

    soma = ServiceContainer.get("soma", default=None)
    soma_data = soma.get_status() if soma else {}

    alignment = ServiceContainer.get("alignment_engine", default=None)
    moral_data = alignment.get_moral_status() if alignment else {}

    homeostasis = ServiceContainer.get("homeostasis", default=None)
    homeo_data = homeostasis.get_status() if homeostasis else {}

    social = ServiceContainer.get("social_memory", default=None)
    social_data = {"depth": social.relationship_depth} if social else {"depth": 0.0}

    swarm_data = orch.swarm_status if orch and hasattr(orch, 'swarm_status') else {"active_count": 0}

    return JSONResponse({
        "status":      "ok" if connected and initialized else "degraded",
        "version":     version_string("full"),
        "connected":   connected,
        "initialized": initialized,
        "cycle_count": getattr(status_obj, "cycle_count", 0),
        "uptime_s":    round(time.time() - (getattr(orch, "start_time", None) or time.time()), 1),
        "cpu_usage":   cpu,
        "ram_usage":   ram,
        "cortex":      cortex,
        "soma":        soma_data,
        "moral":       moral_data,
        "homeostasis": homeo_data,
        "social":      social_data,
        "swarm":       swarm_data,
        "runtime":     rt,
        "timestamp":   datetime.utcnow().isoformat() + "Z",
    })


@app.get("/api/knowledge/graph")
async def api_knowledge_graph(_: None = Depends(_require_internal)):
    """Fetch the current knowledge graph structure for visualization."""
    kg = ServiceContainer.get("knowledge_graph", default=None)
    if not kg:
        return JSONResponse({"nodes": [], "edges": []})
    
    try:
        # Utilize the PersistentKnowledgeGraph's built-in vis-network exporter
        if hasattr(kg, "to_vis_data"):
            return JSONResponse(kg.to_vis_data())
        
        # Fallback: Minimal graph
        return JSONResponse({
            "nodes": [{"id": 1, "label": "Aura Core", "color": "#8a2be2"}],
            "edges": []
        })
    except Exception as e:
        logger.error("Failed to fetch KG data: %s", e)
        # M-06 FIX: Don't leak internal error details
        return JSONResponse({"error": "Knowledge graph query failed"}, status_code=500)


@app.post("/api/brain/retry")
async def api_brain_retry(
    _: None = Depends(_require_internal),
    __: None = Depends(_verify_token),  # C-03 FIX: Require auth
):
    """Signal the orchestrator to retry its cognitive engine connection."""
    orch = ServiceContainer.get("orchestrator", default=None)
    if orch and hasattr(orch, "retry_brain_connection"):
        await orch.retry_brain_connection()
        return JSONResponse({"status": "retry_sent"})
    return JSONResponse({"status": "orchestrator_unavailable"}, status_code=503)


@app.post("/api/reboot")
async def api_reboot(
    _: None = Depends(_require_internal),
    __: None = Depends(_verify_token),  # C-03 FIX: Require auth
):
    """Restart the server process (send SIGTERM; supervisor restarts).
    C-03 FIX: Now requires token authentication."""
    logger.warning("Reboot requested via API")
    import signal as _sig
    _sig.raise_signal(_sig.SIGTERM)
    return JSONResponse({"status": "shutting_down"})


@app.get("/api/skills")
async def api_skills():
    engine = ServiceContainer.get("capability_engine", default=None)
    if engine and hasattr(engine, "skills"):
        names = list(engine.skills.keys())
    else:
        names = []
    return JSONResponse({"skills": names, "count": len(names)})


@app.get("/api/memory/recent")
async def api_memory_recent(limit: int = 20, _: None = Depends(_require_internal)):
    try:
        # Try memory_manager first, then fall back to raw memory
        mem = ServiceContainer.get("memory_manager", default=None)
        if mem and hasattr(mem, "get_stats"):
            stats = mem.get_stats()
            items = []
            if hasattr(mem, "recall"):
                try:
                    recalled = await mem.recall("recent", limit=limit)
                    items = [str(i) for i in recalled]
                except Exception as e:
                    logger.debug("Memory recall failed: %s", e)
            if not items:
                items = [f"Memory store active — {stats.get('total_entries', 0)} entries"]
            return JSONResponse({"items": items})
        
        # Fall back to raw SQLite memory
        raw_mem = ServiceContainer.get("memory", default=None)
        if raw_mem and hasattr(raw_mem, "search"):
            results = raw_mem.search("*", limit=limit)
            return JSONResponse({"items": [str(r) for r in results]})
        
    except Exception as exc:
        logger.debug("Memory recall failed: %s", exc)
    return JSONResponse({"items": []})



@app.post("/api/voice/chunk")
async def api_voice_chunk(request: Request):
    """Receive raw PCM audio chunk from browser AudioWorklet.
    M-01 FIX: Size limit enforced before reading body."""
    content_length = int(request.headers.get("content-length", 0))
    MAX_VOICE_CHUNK = 512 * 1024  # 512KB max
    if content_length > MAX_VOICE_CHUNK:
        raise HTTPException(status_code=413, detail="Voice chunk too large")
    chunk = await request.body()
    if len(chunk) > MAX_VOICE_CHUNK:
        raise HTTPException(status_code=413, detail="Voice chunk too large")
    voice = _voice_engine_fn() if _voice_engine_fn else None
    if voice and hasattr(voice, "feed_chunk"):
        await voice.feed_chunk(chunk)
    return JSONResponse({"ok": True})


@app.get("/api/source")
async def api_source_download(
    _: None = Depends(_require_internal),
    __: None = Depends(_verify_token),  # Require auth for source download
):
    """Bundle and return the current source code as a download."""
    try:
        from utils.bundler import write_bundle
        # M-02 FIX: Use NamedTemporaryFile instead of deprecated mktemp
        import tempfile as _tf
        with _tf.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            out = Path(tmp.name)
        write_bundle(PROJECT_ROOT, out, lite=True)
        return FileResponse(
            str(out),
            media_type="text/plain",
            filename=f"aura_source_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        )
    except Exception as exc:
        logger.error("Source download failed: %s", exc)
        # M-06 FIX: Don't leak internal error details
        raise HTTPException(status_code=500, detail="Source bundle generation failed")


# ── SSE — Voice stream ────────────────────────────────────────

@app.get("/api/stream/voice")
async def voice_sse_stream(request: Request):
    """Server-Sent Events stream for voice pipeline output."""
    async def gen():
        sse_q: asyncio.Queue = asyncio.Queue(maxsize=50)
        # Subscribe
        voice = _voice_engine_fn() if _voice_engine_fn else None
        if voice and hasattr(voice, "subscribe"):
            voice.subscribe(sse_q)
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(sse_q.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\":\"ping\"}\n\n"
        finally:
            if voice and hasattr(voice, "unsubscribe"):
                voice.unsubscribe(sse_q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ── SPA Catch-all — v6.0 Traverse Hardened ────────────────────

@app.get("/{path:path}", include_in_schema=False)
async def spa_catchall(path: str, request: Request):
    """Secure catch-all to support SPA routing and static resolution with traversal protection."""
    _require_internal(request)
    
    # 1. Block known traversal patterns early
    if ".." in path or path.startswith("/") or "./" in path:
         return FileResponse(str(STATIC_DIR / "index.html"), headers=NO_CACHE_HEADERS)

    # 2. Resolve target
    requested_path = (STATIC_DIR / path).resolve()
    
    # 3. Security: Harden against traversal by verifying prefix
    if not str(requested_path).startswith(str(STATIC_DIR)):
         return FileResponse(str(STATIC_DIR / "index.html"), headers=NO_CACHE_HEADERS)
    
    if requested_path.is_file():
        return FileResponse(str(requested_path), headers=NO_CACHE_HEADERS)
    
    # Default fallback to index.html for frontend routing
    return FileResponse(str(STATIC_DIR / "index.html"), headers=NO_CACHE_HEADERS)


@app.get("/api/strategic/projects")
async def api_strategic_projects(_: None = Depends(_require_internal)):
    """Fetch all active strategic projects and their tasks for the Zenith HUD."""
    planner = ServiceContainer.get("strategic_planner")
    if not planner:
        return JSONResponse({"projects": []})
    
    projects = planner.store.get_active_projects()
    result = []
    for p in projects:
        tasks = planner.store.get_tasks_for_project(p.id)
        result.append({
            "id": p.id,
            "name": p.name,
            "goal": p.goal,
            "status": p.status,
            "progress": {
                "completed": sum(1 for t in tasks if t.status == "completed"),
                "total": len(tasks)
            },
            "tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority
                } for t in tasks
            ]
        })
    return JSONResponse({"projects": result})


# ── Phase 16: Cosmic consciousness RPC ────────────────────────

@app.post("/rpc/query_beliefs")
async def rpc_query_beliefs(params: Dict[str, Any], _: None = Depends(_require_internal)):
    """Remote peer querying beliefs about an entity."""
    sync = ServiceContainer.get("belief_sync")
    if sync:
        return await sync.handle_rpc_request("query_beliefs", params)
    return JSONResponse({"error": "BeliefSync not active"}, status_code=503)

@app.post("/rpc/receive_beliefs")
async def rpc_receive_beliefs(payload: Dict[str, Any], _: None = Depends(_require_internal)):
    """Remote peer pushing beliefs to this node."""
    sync = ServiceContainer.get("belief_sync")
    if sync:
        await sync.handle_incoming_beliefs(payload)
        return {"status": "accepted"}
    return JSONResponse({"error": "BeliefSync not active"}, status_code=503)

@app.post("/rpc/receive_resonance")
async def rpc_receive_resonance(payload: Dict[str, Any], _: None = Depends(_require_internal)):
    """Remote peer pushing affective resonance to this node."""
    sync = ServiceContainer.get("belief_sync")
    if sync:
        return await sync.handle_rpc_request("receive_resonance", payload)
    return JSONResponse({"error": "BeliefSync not active"}, status_code=503)

@app.post("/rpc/attention_spike")
async def rpc_attention_spike(payload: Dict[str, Any], _: None = Depends(_require_internal)):
    """Remote peer pushing a collective attention spike."""
    sync = ServiceContainer.get("belief_sync")
    if sync:
        return await sync.handle_rpc_request("attention_spike", payload)
    return JSONResponse({"error": "BeliefSync not active"}, status_code=503)


# ── Entry-point ───────────────────────────────────────────────

def main() -> None:
    from core.logging_config import setup_logging as _sl
    _sl(log_dir=config.paths.log_dir)

    host = "127.0.0.1" if config.security.internal_only_mode else "0.0.0.0"
    logger.info("Binding to %s:8000", host)

    uvicorn.run(
        "interface.server:app",
        host=host,
        port=8000,
        reload=False,
        log_level="warning",   # uvicorn access log is noisy; Aura has its own
        ws_ping_interval=20,
        ws_ping_timeout=10,
    )


if __name__ == "__main__":
    main()

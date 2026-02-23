"""core/schemas.py
Strict Pydantic payloads for all internal state passing in the new Zenith architecture.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class WebsocketMessage(BaseModel):
    """Base schema for any message sent down the websocket."""
    type: str = Field(..., description="The type of the message (e.g. 'thought', 'telemetry')")
    timestamp: Optional[float] = None
    
    class Config:
         extra = 'allow'  # Allow arbitrary extra fields for dynamic data

class TelemetryPayload(WebsocketMessage):
    type: str = "telemetry"
    energy: float = 1.0
    curiosity: float = 0.5
    frustration: float = 0.0
    confidence: float = 1.0
    
    # Consciousness Fields (v6)
    gwt_winner: str = "--"
    coherence: float = 0.0
    vitality: float = 0.0
    surprise: float = 0.0
    narrative: str = ""
    
    consciousness: Dict[str, Any] = Field(default_factory=dict)
    
class CognitiveThoughtPayload(WebsocketMessage):
    type: str = "thought"
    content: str
    urgency: str = "NORMAL"
    cognitive_phase: Optional[str] = None
    
class UserMessagePayload(WebsocketMessage):
    type: str = "user_message"
    content: str

class ErrorPayload(WebsocketMessage):
    type: str = "error"
    message: str

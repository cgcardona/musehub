"""Pydantic models for the Muse API."""
from __future__ import annotations

from musehub.models.requests import MuseRequest, GenerateRequest
from musehub.models.responses import (
    MuseResponse,
    SSEMessage,
    SSEStatus,
    SSEReasoning,
    SSEToolCall,
    SSEComplete,
    SSEError,
)
from musehub.models.tools import (
    ToolResult,
    MidiNote,
    AutomationPoint,
)

# Back-compat aliases — remove once all callers are updated.
MaestroRequest = MuseRequest
MaestroResponse = MuseResponse

__all__ = [
    "MuseRequest",
    "GenerateRequest",
    "MuseResponse",
    # Back-compat aliases
    "MaestroRequest",
    "MaestroResponse",
    "SSEMessage",
    "SSEStatus",
    "SSEReasoning",
    "SSEToolCall",
    "SSEComplete",
    "SSEError",
    "ToolResult",
    "MidiNote",
    "AutomationPoint",
]

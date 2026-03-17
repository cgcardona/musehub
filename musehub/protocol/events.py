"""Muse Hub protocol event models.

``MuseEvent`` is the base class for all typed events on this server.
Currently the server defines two concrete event types, both in the MCP
relay path.  The ``type`` field is a discriminating literal on every
subclass; ``seq`` and ``protocol_version`` are meta-fields injected by
the caller, not set by event constructors.

Wire-format rules:
  - All keys are camelCase via ``CamelModel.alias_generator``.
  - Serialise with ``model_dump(by_alias=True, exclude_none=True)``.
  - ``extra="forbid"`` enforces the strict outbound contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from musehub.models.base import CamelModel
from musehub.protocol.version import MUSE_VERSION


class MuseEvent(CamelModel):
    """Base class for all protocol events."""

    model_config = ConfigDict(extra="forbid")

    type: str
    seq: int = -1
    protocol_version: str = MUSE_VERSION


# ═══════════════════════════════════════════════════════════════════════
# MCP relay events
# ═══════════════════════════════════════════════════════════════════════


class MCPMessageEvent(MuseEvent):
    """MCP tool-call message relayed over SSE."""

    type: Literal["mcp.message"] = "mcp.message"
    payload: dict[str, object] = Field(default_factory=dict)


class MCPPingEvent(MuseEvent):
    """MCP SSE keepalive heartbeat."""

    type: Literal["mcp.ping"] = "mcp.ping"

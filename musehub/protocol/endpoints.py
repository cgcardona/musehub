"""Protocol introspection endpoints.

Exposes the protocol version, hash, event schemas, and MCP tool schemas
so clients can detect contract drift without reading source code.
"""

from __future__ import annotations

from fastapi import APIRouter

from musehub.contracts.mcp_types import MCPToolDefWire
from musehub.contracts.pydantic_types import PydanticJson
from musehub.protocol.hash import compute_protocol_hash
from musehub.protocol.registry import ALL_EVENT_TYPES, EVENT_REGISTRY
from musehub.protocol.responses import (
    ProtocolEventsResponse,
    ProtocolInfoResponse,
    ProtocolSchemaResponse,
    ProtocolToolsResponse,
)
from musehub.protocol.version import MUSE_VERSION

router = APIRouter()


@router.get("/protocol")
async def protocol_info() -> ProtocolInfoResponse:
    """Protocol version, hash, and registered event types."""
    return ProtocolInfoResponse(
        protocolVersion=MUSE_VERSION,
        protocolHash=compute_protocol_hash(),
        eventTypes=sorted(ALL_EVENT_TYPES),
        eventCount=len(EVENT_REGISTRY),
    )


@router.get("/protocol/events.json")
async def protocol_events() -> ProtocolEventsResponse:
    """JSON Schema for every registered event type."""
    return ProtocolEventsResponse(
        protocolVersion=MUSE_VERSION,
        events={
            event_type: PydanticJson.model_validate(
                EVENT_REGISTRY[event_type].model_json_schema()
            )
            for event_type in sorted(EVENT_REGISTRY)
        },
    )


@router.get("/protocol/tools.json")
async def protocol_tools() -> ProtocolToolsResponse:
    """MCP tool definitions for all registered server-side tools."""
    from musehub.mcp.tools import MUSEHUB_TOOLS

    return ProtocolToolsResponse(
        protocolVersion=MUSE_VERSION,
        tools=[MCPToolDefWire.model_validate(t) for t in MUSEHUB_TOOLS],
        toolCount=len(MUSEHUB_TOOLS),
    )


@router.get("/protocol/schema.json")
async def protocol_schema() -> ProtocolSchemaResponse:
    """Unified protocol schema — version + hash + events + tools in one fetch."""
    from musehub.mcp.tools import MUSEHUB_TOOLS

    return ProtocolSchemaResponse(
        protocolVersion=MUSE_VERSION,
        protocolHash=compute_protocol_hash(),
        events={
            event_type: PydanticJson.model_validate(
                EVENT_REGISTRY[event_type].model_json_schema()
            )
            for event_type in sorted(EVENT_REGISTRY)
        },
        tools=[MCPToolDefWire.model_validate(t) for t in MUSEHUB_TOOLS],
        toolCount=len(MUSEHUB_TOOLS),
        eventCount=len(EVENT_REGISTRY),
    )

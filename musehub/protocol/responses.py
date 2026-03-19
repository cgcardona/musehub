"""Pydantic response models for protocol introspection endpoints.

Each model names the exact entity returned by a protocol endpoint, making
the contract between the route handler, its serializer, and any caller
explicit.  Field names are camelCase by declaration to match the wire
format already consumed by clients.
"""
from __future__ import annotations



from pydantic import BaseModel, Field

from musehub.contracts.mcp_types import MCPToolDefWire
from musehub.contracts.pydantic_types import PydanticJson


class ProtocolInfoResponse(BaseModel):
    """Summary response for ``GET /protocol``."""

    protocolVersion: str = Field(
        description="Semver string (e.g. '1.4.2'). Bumped on any schema-breaking change."
    )
    protocolHash: str = Field(
        description="SHA-256 content hash of the full serialised schema (hex string)."
    )
    eventTypes: list[str] = Field(
        description="Alphabetically sorted list of every registered event type name."
    )
    eventCount: int = Field(
        description="Number of registered event types. Equals len(eventTypes)."
    )


class ProtocolEventsResponse(BaseModel):
    """Response for ``GET /protocol/events.json``."""

    protocolVersion: str = Field(
        description="Semver string of the protocol version that produced these schemas."
    )
    events: dict[str, PydanticJson] = Field(
        description="Map from event type name to its JSON Schema draft-07 object."
    )


class ProtocolToolsResponse(BaseModel):
    """Response for ``GET /protocol/tools.json``."""

    protocolVersion: str = Field(
        description="Semver string of the protocol version that produced these tool definitions."
    )
    tools: list[MCPToolDefWire] = Field(
        description="Ordered list of every registered MCP tool definition."
    )
    toolCount: int = Field(
        description="Number of tool definitions. Equals len(tools)."
    )


class ProtocolSchemaResponse(BaseModel):
    """Response for ``GET /protocol/schema.json``.

    Unified schema snapshot — version, hash, all event schemas, and tool
    definitions in one fetch.  Cacheable by ``protocolHash``.
    """

    protocolVersion: str = Field(
        description="Semver string of the protocol version that produced this snapshot."
    )
    protocolHash: str = Field(
        description="SHA-256 content hash of this snapshot."
    )
    events: dict[str, PydanticJson] = Field(
        description="Map from event type name to its JSON Schema object."
    )
    tools: list[MCPToolDefWire] = Field(
        description="Ordered list of every registered MCP tool definition."
    )
    toolCount: int = Field(
        description="Number of tool definitions. Equals len(tools)."
    )
    eventCount: int = Field(
        description="Number of registered event types. Equals len(events)."
    )

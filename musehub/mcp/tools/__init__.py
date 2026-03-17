"""MCP tool registry for MuseHub tools (reads + writes).

``MUSEHUB_TOOLS``           — all 27 musehub_* tool definitions (reads + writes).
``MUSEHUB_TOOL_NAMES``      — set of all tool names for routing.
``MUSEHUB_WRITE_TOOL_NAMES`` — set of write-only tool names (auth required).
``MCP_TOOLS``               — combined list of all registered MCP tools.
``TOOL_CATEGORIES``         — maps tool name → category string.
"""
from __future__ import annotations

from musehub.contracts.mcp_types import MCPToolDef
from musehub.mcp.tools.musehub import (
    MUSEHUB_TOOLS,
    MUSEHUB_TOOL_NAMES,
    MUSEHUB_WRITE_TOOL_NAMES,
)

MCP_TOOLS: list[MCPToolDef] = list(MUSEHUB_TOOLS)

TOOL_CATEGORIES: dict[str, str] = {
    name: ("musehub-write" if name in MUSEHUB_WRITE_TOOL_NAMES else "musehub-read")
    for name in MUSEHUB_TOOL_NAMES
}

__all__ = [
    "MUSEHUB_TOOLS",
    "MUSEHUB_TOOL_NAMES",
    "MUSEHUB_WRITE_TOOL_NAMES",
    "MCP_TOOLS",
    "TOOL_CATEGORIES",
]

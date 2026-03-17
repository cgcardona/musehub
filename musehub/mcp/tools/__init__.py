"""MCP tool registry for MuseHub browsing tools.

``MUSEHUB_TOOLS`` — all ``musehub_*`` MCP tool definitions.
``MUSEHUB_TOOL_NAMES`` — set of tool names for routing.
``MCP_TOOLS`` — combined list of all registered MCP tools.
``TOOL_CATEGORIES`` — maps tool name → category string.
"""
from __future__ import annotations

from musehub.contracts.mcp_types import MCPToolDef
from musehub.mcp.tools.musehub import MUSEHUB_TOOLS, MUSEHUB_TOOL_NAMES

MCP_TOOLS: list[MCPToolDef] = list(MUSEHUB_TOOLS)

TOOL_CATEGORIES: dict[str, str] = {name: "musehub" for name in MUSEHUB_TOOL_NAMES}

__all__ = [
    "MUSEHUB_TOOLS",
    "MUSEHUB_TOOL_NAMES",
    "MCP_TOOLS",
    "TOOL_CATEGORIES",
]

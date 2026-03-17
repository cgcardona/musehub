"""MCP tool registry for MuseHub browsing tools.

``MUSEHUB_TOOLS`` — all ``musehub_*`` MCP tool definitions.
``MUSEHUB_TOOL_NAMES`` — set of tool names for routing.
"""
from __future__ import annotations

from musehub.mcp.tools.musehub import MUSEHUB_TOOLS, MUSEHUB_TOOL_NAMES

__all__ = [
    "MUSEHUB_TOOLS",
    "MUSEHUB_TOOL_NAMES",
]

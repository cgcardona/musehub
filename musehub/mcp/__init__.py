"""MCP (Model Context Protocol) server for MuseHub."""
from __future__ import annotations

from musehub.mcp.server import MuseMCPServer
from musehub.mcp.tools import MUSEHUB_TOOLS, MUSEHUB_TOOL_NAMES

__all__ = ["MuseMCPServer", "MUSEHUB_TOOLS", "MUSEHUB_TOOL_NAMES"]

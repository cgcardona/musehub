"""MCP (Model Context Protocol) server for DAW control."""
from __future__ import annotations

from musehub.mcp.server import MuseMCPServer
from musehub.mcp.tools import MCP_TOOLS

# Back-compat alias — remove once all callers are updated.
MaestroMCPServer = MuseMCPServer

__all__ = ["MuseMCPServer", "MaestroMCPServer", "MCP_TOOLS"]

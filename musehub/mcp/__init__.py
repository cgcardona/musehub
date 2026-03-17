"""MCP (Model Context Protocol) server for DAW control."""
from __future__ import annotations

from musehub.mcp.server import MaestroMCPServer
from musehub.mcp.tools import MCP_TOOLS

__all__ = ["MaestroMCPServer", "MCP_TOOLS"]

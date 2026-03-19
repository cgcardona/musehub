"""MCP tool registry for MuseHub tools (reads + writes + elicitation).

``MUSEHUB_TOOLS``                — all 32 musehub_* tool definitions.
``MUSEHUB_TOOL_NAMES``           — set of all tool names for routing.
``MUSEHUB_WRITE_TOOL_NAMES``     — set of write/interactive tool names (auth required).
``MUSEHUB_ELICITATION_TOOL_NAMES`` — set of elicitation-powered tool names.
``MCP_TOOLS``                    — combined list of all registered MCP tools.
``TOOL_CATEGORIES``              — maps tool name → category string.
"""

from musehub.contracts.mcp_types import MCPToolDef
from musehub.mcp.tools.musehub import (
    MUSEHUB_TOOLS,
    MUSEHUB_TOOL_NAMES,
    MUSEHUB_WRITE_TOOL_NAMES,
    MUSEHUB_ELICITATION_TOOL_NAMES,
)

MCP_TOOLS: list[MCPToolDef] = list(MUSEHUB_TOOLS)

TOOL_CATEGORIES: dict[str, str] = {
    name: (
        "musehub-elicitation" if name in MUSEHUB_ELICITATION_TOOL_NAMES
        else "musehub-write" if name in MUSEHUB_WRITE_TOOL_NAMES
        else "musehub-read"
    )
    for name in MUSEHUB_TOOL_NAMES
}

__all__ = [
    "MUSEHUB_TOOLS",
    "MUSEHUB_TOOL_NAMES",
    "MUSEHUB_WRITE_TOOL_NAMES",
    "MUSEHUB_ELICITATION_TOOL_NAMES",
    "MCP_TOOLS",
    "TOOL_CATEGORIES",
]

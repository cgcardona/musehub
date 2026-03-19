"""MuseHub MCP server — routes musehub_* tool calls to the executor layer."""


import json
import logging
from dataclasses import dataclass, field

from musehub.mcp.tools import MUSEHUB_TOOL_NAMES
from musehub.services import musehub_mcp_executor as executor
from musehub.services.musehub_mcp_executor import MusehubToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ToolCallResult:
    """Uniform result returned by ``MuseMCPServer.call_tool``.

    Attributes:
        success: True when the tool call produced a usable result.
        is_error: True when the result represents a non-recoverable error.
        bad_request: True when the caller sent invalid parameters.
        content: MCP-style list of content blocks (e.g. ``[{"type": "text",
            "text": "..."}]``). Always contains at least one block.
    """

    success: bool = True
    is_error: bool = False
    bad_request: bool = False
    content: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class MuseMCPServer:
    """Lightweight MCP server that routes musehub_* tool calls."""

    async def call_tool(self, name: str, params: dict[str, object]) -> ToolCallResult:
        """Dispatch a tool call by name and return a ``ToolCallResult``."""
        if name not in MUSEHUB_TOOL_NAMES:
            return ToolCallResult(
                success=False,
                is_error=True,
                content=[{"type": "text", "text": f"Unknown tool: {name}"}],
            )
        result = await self._execute_musehub_tool(name, params)
        return self._build_result(result)

    async def _execute_musehub_tool(
        self, name: str, params: dict[str, object]
    ) -> MusehubToolResult:
        repo_id = str(params.get("repo_id", ""))
        match name:
            case "musehub_browse_repo":
                return await executor.execute_browse_repo(repo_id)
            case "musehub_list_branches":
                return await executor.execute_list_branches(repo_id)
            case "musehub_list_commits":
                raw_limit = params.get("limit", 20)
                limit = int(raw_limit) if isinstance(raw_limit, (int, float)) else 20
                branch_raw = params.get("branch")
                branch = str(branch_raw) if branch_raw is not None else None
                return await executor.execute_list_commits(repo_id, branch=branch, limit=limit)
            case "musehub_read_file":
                object_id = str(params.get("object_id", ""))
                return await executor.execute_read_file(repo_id, object_id)
            case "musehub_get_analysis":
                dimension = str(params.get("dimension", "overview"))
                return await executor.execute_get_analysis(repo_id, dimension=dimension)
            case "musehub_search":
                query = str(params.get("query", ""))
                mode = str(params.get("mode", "path"))
                return await executor.execute_search(repo_id, query=query, mode=mode)
            case "musehub_get_context":
                return await executor.execute_get_context(repo_id)
            case _:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"No executor for tool: {name}",
                )

    def _build_result(self, result: MusehubToolResult) -> ToolCallResult:
        if result.ok:
            text = json.dumps(result.data, default=str)
            return ToolCallResult(
                success=True,
                content=[{"type": "text", "text": text}],
            )

        bad_request = result.error_code in ("invalid_dimension", "invalid_mode")
        message = result.error_message or result.error_code or "Unknown error"
        return ToolCallResult(
            success=False,
            is_error=True,
            bad_request=bad_request,
            content=[{"type": "text", "text": message}],
        )

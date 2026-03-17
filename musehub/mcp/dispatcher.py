"""MuseHub MCP Dispatcher — async JSON-RPC 2.0 engine.

This is the protocol core: it receives a parsed JSON-RPC 2.0 message dict
and returns the appropriate JSON-RPC 2.0 response dict.

Supported methods:
  initialize              → server capabilities handshake
  tools/list              → full 27-tool catalogue
  tools/call              → route to read or write executor
  resources/list          → static resource catalogue
  resources/templates/list → RFC 6570 URI templates
  resources/read          → musehub:// URI dispatcher
  prompts/list            → prompt catalogue
  prompts/get             → assembled prompt messages

Design principles (from agentception):
  - JSON-RPC envelope is always success (200 OK / no envelope error).
  - Tool errors are signalled via ``isError: true`` on the content block.
  - No external MCP SDK dependency — pure Python async.
  - All DB access happens inside executor/resource functions, never here.
  - Notifications (no ``id`` field) return None — callers return 202.
"""
from __future__ import annotations

import json
import logging
from typing import Literal

from musehub.contracts.json_types import JSONObject, JSONValue
from musehub.contracts.mcp_types import (
    MCPContentBlock,
    MCPErrorDetail,
    MCPErrorResponse,
    MCPRequest,
    MCPSuccessResponse,
    MCPToolDef,
)
from musehub.mcp.prompts import PROMPT_CATALOGUE, PROMPT_NAMES, get_prompt
from musehub.mcp.resources import (
    RESOURCE_TEMPLATES,
    STATIC_RESOURCES,
    read_resource,
)
from musehub.mcp.tools import MCP_TOOLS, MUSEHUB_WRITE_TOOL_NAMES

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2025-03-26"
_SERVER_NAME = "musehub-mcp"
_SERVER_VERSION = "1.0.0"

# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


# ── Public entry point ────────────────────────────────────────────────────────


async def handle_request(
    raw: JSONObject,
    *,
    user_id: str | None = None,
) -> JSONObject | None:
    """Dispatch a single JSON-RPC 2.0 request and return the response dict.

    Args:
        raw: Parsed JSON-RPC 2.0 request dict.
        user_id: Authenticated user ID from JWT (``None`` for anonymous).

    Returns:
        JSON-serialisable response dict, or ``None`` for notifications
        (requests without an ``id`` field).
    """
    req_id: str | int | None = raw.get("id")  # type: ignore[assignment]
    method = raw.get("method")

    if not isinstance(method, str):
        return _error(req_id, _INVALID_REQUEST, "Missing or invalid 'method' field")

    # Notifications (no id) are fire-and-forget — return None.
    is_notification = "id" not in raw

    raw_params = raw.get("params")
    params: JSONObject = raw_params if isinstance(raw_params, dict) else {}

    try:
        result = await _dispatch(method, params, user_id=user_id)
        if is_notification:
            return None
        return _success(req_id, result)
    except _MCPError as exc:
        if is_notification:
            return None
        return _error(req_id, exc.code, exc.message, exc.data)
    except Exception as exc:
        logger.exception("Unhandled error in MCP dispatcher (method=%s): %s", method, exc)
        if is_notification:
            return None
        return _error(req_id, _INTERNAL_ERROR, f"Internal error: {exc}")


async def handle_batch(
    requests: list[JSONObject],
    *,
    user_id: str | None = None,
) -> list[JSONObject]:
    """Dispatch a JSON-RPC 2.0 batch and return all non-notification responses.

    Args:
        requests: List of parsed JSON-RPC 2.0 request dicts.
        user_id: Authenticated user ID (``None`` for anonymous).

    Returns:
        List of response dicts (excluding None responses for notifications).
    """
    results: list[JSONObject] = []
    for req in requests:
        resp = await handle_request(req, user_id=user_id)
        if resp is not None:
            results.append(resp)
    return results


# ── Internal dispatcher ───────────────────────────────────────────────────────


class _MCPError(Exception):
    def __init__(self, code: int, message: str, data: JSONValue | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


async def _dispatch(
    method: str,
    params: JSONObject,
    *,
    user_id: str | None,
) -> JSONObject:
    """Route a method name to its handler and return the result dict."""

    if method == "initialize":
        return _handle_initialize(params)

    if method == "tools/list":
        return _handle_tools_list()

    if method == "tools/call":
        return await _handle_tools_call(params, user_id=user_id)

    if method == "resources/list":
        return _handle_resources_list()

    if method == "resources/templates/list":
        return _handle_resources_templates_list()

    if method == "resources/read":
        return await _handle_resources_read(params, user_id=user_id)

    if method == "prompts/list":
        return _handle_prompts_list()

    if method == "prompts/get":
        return _handle_prompts_get(params)

    # ping / other standard methods
    if method == "ping":
        return {}

    raise _MCPError(_METHOD_NOT_FOUND, f"Method not found: {method!r}")


# ── Method handlers ───────────────────────────────────────────────────────────


def _handle_initialize(params: JSONObject) -> JSONObject:
    """Return server capabilities and protocol version."""
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "serverInfo": {
            "name": _SERVER_NAME,
            "version": _SERVER_VERSION,
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {},
            },
        },
        "capabilities": {
            "tools": {},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {},
        },
    }


def _handle_tools_list() -> JSONObject:
    """Return the full tool catalogue."""
    # Strip the internal ``server_side`` flag before sending to clients.
    # Serialise via json round-trip to produce a plain dict[str, JSONValue].
    import json as _json
    raw = _json.dumps([{k: v for k, v in t.items() if k != "server_side"} for t in MCP_TOOLS])
    tools: list[JSONValue] = _json.loads(raw)
    return {"tools": tools}


async def _handle_tools_call(params: JSONObject, *, user_id: str | None) -> JSONObject:
    """Route a ``tools/call`` request to the appropriate executor."""
    name = params.get("name")
    arguments = params.get("arguments") or {}

    if not isinstance(name, str):
        raise _MCPError(_INVALID_PARAMS, "tools/call requires a 'name' string parameter")
    if not isinstance(arguments, dict):
        raise _MCPError(_INVALID_PARAMS, "tools/call 'arguments' must be an object")

    # Auth gate: write tools require an authenticated user.
    if name in MUSEHUB_WRITE_TOOL_NAMES and user_id is None:
        return _tool_error(f"Tool '{name}' requires authentication. Provide a Bearer JWT.")

    # Route to the appropriate executor.
    try:
        return await _call_tool(name, arguments, user_id=user_id)
    except Exception as exc:
        logger.exception("Tool execution error (tool=%s): %s", name, exc)
        return _tool_error(f"Internal error executing tool '{name}': {exc}")


async def _call_tool(
    name: str,
    arguments: JSONObject,
    *,
    user_id: str | None,
) -> JSONObject:
    """Delegate to the correct executor and wrap result in MCP content block."""
    from musehub.services import musehub_mcp_executor as exe

    def _str(key: str) -> str:
        v = arguments.get(key, "")
        return str(v) if v is not None else ""

    def _int(key: str, default: int = 20) -> int:
        v = arguments.get(key)
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        return default

    def _bool(key: str, default: bool = False) -> bool:
        v = arguments.get(key)
        if isinstance(v, bool):
            return v
        return default

    def _float_or_none(key: str) -> float | None:
        v = arguments.get(key)
        if isinstance(v, (int, float)):
            return float(v)
        return None

    def _str_or_none(key: str) -> str | None:
        v = arguments.get(key)
        return str(v) if v is not None else None

    def _list_str(key: str) -> list[str]:
        v = arguments.get(key)
        if isinstance(v, list):
            return [str(x) for x in v]
        return []

    # ── Read tools ────────────────────────────────────────────────────────────

    if name == "musehub_browse_repo":
        result = await exe.execute_browse_repo(_str("repo_id"))
    elif name == "musehub_list_branches":
        result = await exe.execute_list_branches(_str("repo_id"))
    elif name == "musehub_list_commits":
        result = await exe.execute_list_commits(
            _str("repo_id"),
            branch=_str_or_none("branch"),
            limit=_int("limit", 20),
        )
    elif name == "musehub_read_file":
        result = await exe.execute_read_file(_str("repo_id"), _str("object_id"))
    elif name == "musehub_get_analysis":
        result = await exe.execute_get_analysis(
            _str("repo_id"),
            dimension=_str_or_none("dimension") or "overview",
        )
    elif name == "musehub_search":
        result = await exe.execute_search(
            _str("repo_id"),
            query=_str("query"),
            mode=_str_or_none("mode") or "path",
        )
    elif name == "musehub_get_context":
        result = await exe.execute_get_context(_str("repo_id"))
    elif name == "musehub_get_commit":
        result = await exe.execute_get_commit(_str("repo_id"), _str("commit_id"))
    elif name == "musehub_compare":
        result = await exe.execute_compare(
            _str("repo_id"),
            base_ref=_str("base_ref"),
            head_ref=_str("head_ref"),
        )
    elif name == "musehub_list_issues":
        result = await exe.execute_list_issues(
            _str("repo_id"),
            state=_str_or_none("state") or "open",
            label=_str_or_none("label"),
        )
    elif name == "musehub_get_issue":
        result = await exe.execute_get_issue(_str("repo_id"), _int("issue_number", 0))
    elif name == "musehub_list_prs":
        result = await exe.execute_list_prs(
            _str("repo_id"),
            state=_str_or_none("state") or "all",
        )
    elif name == "musehub_get_pr":
        result = await exe.execute_get_pr(_str("repo_id"), _str("pr_id"))
    elif name == "musehub_list_releases":
        result = await exe.execute_list_releases(_str("repo_id"))
    elif name == "musehub_search_repos":
        result = await exe.execute_search_repos(
            query=_str_or_none("query"),
            key_signature=_str_or_none("key_signature"),
            tempo_min=_int("tempo_min", 0) or None,
            tempo_max=_int("tempo_max", 0) or None,
            tags=_list_str("tags"),
            limit=_int("limit", 20),
        )

    # ── Write tools ───────────────────────────────────────────────────────────

    elif name == "musehub_create_repo":
        from musehub.mcp.write_tools.repos import execute_create_repo

        result = await execute_create_repo(
            name=_str("name"),
            owner=user_id or "",
            owner_user_id=user_id or "",
            description=_str_or_none("description") or "",
            visibility=_str_or_none("visibility") or "public",
            tags=_list_str("tags") or None,
            key_signature=_str_or_none("key_signature"),
            tempo_bpm=_int("tempo_bpm", 0) or None,
            initialize=_bool("initialize", True),
        )
    elif name == "musehub_create_issue":
        from musehub.mcp.write_tools.issues import execute_create_issue

        result = await execute_create_issue(
            repo_id=_str("repo_id"),
            title=_str("title"),
            body=_str_or_none("body") or "",
            labels=_list_str("labels") or None,
            actor=user_id or "",
        )
    elif name == "musehub_update_issue":
        from musehub.mcp.write_tools.issues import execute_update_issue

        result = await execute_update_issue(
            repo_id=_str("repo_id"),
            issue_number=_int("issue_number", 0),
            title=_str_or_none("title"),
            body=_str_or_none("body"),
            labels=_list_str("labels") if "labels" in arguments else None,
            state=_str_or_none("state"),
            assignee=_str_or_none("assignee"),
        )
    elif name == "musehub_create_issue_comment":
        from musehub.mcp.write_tools.issues import execute_create_issue_comment

        result = await execute_create_issue_comment(
            repo_id=_str("repo_id"),
            issue_number=_int("issue_number", 0),
            body=_str("body"),
            actor=user_id or "",
        )
    elif name == "musehub_create_pr":
        from musehub.mcp.write_tools.pulls import execute_create_pr

        result = await execute_create_pr(
            repo_id=_str("repo_id"),
            title=_str("title"),
            from_branch=_str("from_branch"),
            to_branch=_str("to_branch"),
            body=_str_or_none("body") or "",
            actor=user_id or "",
        )
    elif name == "musehub_merge_pr":
        from musehub.mcp.write_tools.pulls import execute_merge_pr

        result = await execute_merge_pr(
            repo_id=_str("repo_id"),
            pr_id=_str("pr_id"),
            merge_strategy=_str_or_none("merge_strategy") or "merge_commit",
        )
    elif name == "musehub_create_pr_comment":
        from musehub.mcp.write_tools.pulls import execute_create_pr_comment

        result = await execute_create_pr_comment(
            repo_id=_str("repo_id"),
            pr_id=_str("pr_id"),
            body=_str("body"),
            actor=user_id or "",
            target_type=_str_or_none("target_type") or "general",
            target_track=_str_or_none("target_track"),
            target_beat_start=_float_or_none("target_beat_start"),
            target_beat_end=_float_or_none("target_beat_end"),
        )
    elif name == "musehub_submit_pr_review":
        from musehub.mcp.write_tools.pulls import execute_submit_pr_review

        result = await execute_submit_pr_review(
            repo_id=_str("repo_id"),
            pr_id=_str("pr_id"),
            event=_str("event"),
            body=_str_or_none("body") or "",
            reviewer=user_id or "",
        )
    elif name == "musehub_create_release":
        from musehub.mcp.write_tools.releases import execute_create_release

        result = await execute_create_release(
            repo_id=_str("repo_id"),
            tag=_str("tag"),
            title=_str("title"),
            body=_str_or_none("body") or "",
            commit_id=_str_or_none("commit_id"),
            is_prerelease=_bool("is_prerelease", False),
            actor=user_id or "",
        )
    elif name == "musehub_star_repo":
        from musehub.mcp.write_tools.social import execute_star_repo

        result = await execute_star_repo(repo_id=_str("repo_id"), actor=user_id or "")
    elif name == "musehub_fork_repo":
        from musehub.mcp.write_tools.repos import execute_fork_repo

        result = await execute_fork_repo(repo_id=_str("repo_id"), actor=user_id or "")
    elif name == "musehub_create_label":
        from musehub.mcp.write_tools.social import execute_create_label

        result = await execute_create_label(
            repo_id=_str("repo_id"),
            name=_str("name"),
            color=_str("color"),
            description=_str_or_none("description") or "",
            actor=user_id or "",
        )
    else:
        return _tool_error(f"Unknown tool: {name!r}")

    # Wrap MusehubToolResult in an MCP content block.
    if result.ok:
        text = json.dumps(result.data, default=str)
        return {
            "content": [{"type": "text", "text": text}],
            "isError": False,
        }
    else:
        error_text = json.dumps({
            "error_code": result.error_code,
            "error_message": result.error_message,
        })
        return {
            "content": [{"type": "text", "text": error_text}],
            "isError": True,
        }


def _handle_resources_list() -> JSONObject:
    """Return the static resource catalogue."""
    import json as _json
    raw: list[JSONValue] = _json.loads(_json.dumps(list(STATIC_RESOURCES)))
    return {"resources": raw}


def _handle_resources_templates_list() -> JSONObject:
    """Return the RFC 6570 URI template catalogue."""
    import json as _json
    raw: list[JSONValue] = _json.loads(_json.dumps(list(RESOURCE_TEMPLATES)))
    return {"resourceTemplates": raw}


async def _handle_resources_read(
    params: JSONObject,
    *,
    user_id: str | None,
) -> JSONObject:
    """Read a ``musehub://`` resource by URI."""
    uri = params.get("uri")
    if not isinstance(uri, str):
        raise _MCPError(_INVALID_PARAMS, "resources/read requires a 'uri' string parameter")

    data = await read_resource(uri, user_id=user_id)
    text = json.dumps(data, default=str)
    contents: list[JSONValue] = [{"uri": uri, "mimeType": "application/json", "text": text}]
    return {"contents": contents}


def _handle_prompts_list() -> JSONObject:
    """Return the prompt catalogue."""
    import json as _json
    raw: list[JSONValue] = _json.loads(_json.dumps(list(PROMPT_CATALOGUE)))
    return {"prompts": raw}


def _handle_prompts_get(params: JSONObject) -> JSONObject:
    """Assemble and return a prompt by name."""
    name = params.get("name")
    arguments = params.get("arguments") or {}

    if not isinstance(name, str):
        raise _MCPError(_INVALID_PARAMS, "prompts/get requires a 'name' string parameter")
    if name not in PROMPT_NAMES:
        raise _MCPError(_METHOD_NOT_FOUND, f"Prompt not found: {name!r}")

    args: dict[str, str] = {}
    if isinstance(arguments, dict):
        for k, v in arguments.items():
            if isinstance(v, str):
                args[k] = v

    prompt_result = get_prompt(name, args)
    if prompt_result is None:
        raise _MCPError(_METHOD_NOT_FOUND, f"Prompt not found: {name!r}")
    import json as _json
    resp: JSONObject = _json.loads(_json.dumps(prompt_result))
    return resp


# ── JSON-RPC helpers ──────────────────────────────────────────────────────────


def _success(req_id: str | int | None, result: JSONObject) -> JSONObject:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(
    req_id: str | int | None,
    code: int,
    message: str,
    data: JSONValue | None = None,
) -> JSONObject:
    error: dict[str, JSONValue] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


def _tool_error(message: str) -> JSONObject:
    """Build a tool-level error (envelope success, isError=true content)."""
    return {
        "content": [{"type": "text", "text": json.dumps({"error": message})}],
        "isError": True,
    }

"""MuseHub MCP Dispatcher — async JSON-RPC 2.0 engine (MCP 2025-11-25).

This is the protocol core: it receives a parsed JSON-RPC 2.0 message dict
and returns the appropriate JSON-RPC 2.0 response dict.

Supported methods:
  initialize              → server capabilities handshake (2025-11-25)
  tools/list              → full tool catalogue (27 standard + 5 elicitation-powered)
  tools/call              → route to read, write, or elicitation-powered executor
  resources/list          → static resource catalogue
  resources/templates/list → RFC 6570 URI templates
  resources/read          → musehub:// URI dispatcher
  prompts/list            → prompt catalogue
  prompts/get             → assembled prompt messages
  notifications/cancelled → cancel pending elicitation Futures
  notifications/elicitation/complete → resolve URL-mode elicitation Futures
  ping                    → liveness check

Design principles (from agentception):
  - JSON-RPC envelope is always success (200 OK / no envelope error).
  - Tool errors are signalled via ``isError: true`` on the content block.
  - No external MCP SDK dependency — pure Python async.
  - All DB access happens inside executor/resource functions, never here.
  - Notifications (no ``id`` field) return None — callers return 202.
  - Session context is optional; tools without elicitation work stateless.
"""
from __future__ import annotations


import json
import logging
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from musehub.mcp.context import ToolCallContext
    from musehub.mcp.session import MCPSession

logger = logging.getLogger(__name__)

_PROTOCOL_VERSION = "2025-11-25"
_SERVER_NAME = "musehub-mcp"
_SERVER_VERSION = "1.1.0"

# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_URL_ELICITATION_REQUIRED = -32042  # MCP 2025-11-25 new error code


# ── Public entry points ───────────────────────────────────────────────────────


async def handle_request(
    raw: JSONObject,
    *,
    user_id: str | None = None,
    session: "MCPSession | None" = None,
    is_agent: bool = False,
    agent_name: str | None = None,
) -> JSONObject | None:
    """Dispatch a single JSON-RPC 2.0 request and return the response dict.

    Args:
        raw: Parsed JSON-RPC 2.0 request dict.
        user_id: Authenticated user ID from JWT (``None`` for anonymous).
        session: Active MCP session for elicitation and progress features,
            or ``None`` for stateless (non-elicitation) clients.
        is_agent: ``True`` when the caller presents an agent JWT token.
        agent_name: Optional display name of the agent (from ``agent_name`` claim).

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
        result = await _dispatch(
            method, params, user_id=user_id, session=session,
            is_agent=is_agent, agent_name=agent_name,
        )
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
    session: "MCPSession | None" = None,
    is_agent: bool = False,
    agent_name: str | None = None,
) -> list[JSONObject]:
    """Dispatch a JSON-RPC 2.0 batch and return all non-notification responses.

    Args:
        requests: List of parsed JSON-RPC 2.0 request dicts.
        user_id: Authenticated user ID (``None`` for anonymous).
        session: Active MCP session, or ``None`` for stateless clients.
        is_agent: ``True`` when the caller presents an agent JWT token.
        agent_name: Optional display name of the agent.

    Returns:
        List of response dicts (excluding None responses for notifications).
    """
    results: list[JSONObject] = []
    for req in requests:
        resp = await handle_request(
            req, user_id=user_id, session=session,
            is_agent=is_agent, agent_name=agent_name,
        )
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
    session: "MCPSession | None",
    is_agent: bool = False,
    agent_name: str | None = None,
) -> JSONObject:
    """Route a method name to its handler and return the result dict."""

    if method == "initialize":
        return _handle_initialize(params)

    if method == "tools/list":
        return _handle_tools_list()

    if method == "tools/call":
        return await _handle_tools_call(
            params, user_id=user_id, session=session,
            is_agent=is_agent, agent_name=agent_name,
        )

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

    # ── MCP 2025-11-25 notification methods ───────────────────────────────────

    if method == "notifications/cancelled":
        _handle_notifications_cancelled(params, session=session)
        return {}

    if method == "notifications/elicitation/complete":
        _handle_elicitation_complete(params, session=session)
        return {}

    if method == "notifications/initialized":
        # Acknowledgement from client after initialize — no-op.
        return {}

    # ── MCP 2025-11-25 additional methods ────────────────────────────────────

    if method == "completions/complete":
        # Stub autocomplete — returns empty values; can be populated per-arg later.
        return {"completion": {"values": [], "hasMore": False, "total": 0}}

    if method == "logging/setLevel":
        level = params.get("level")
        if isinstance(level, str):
            import logging as _logging
            _logging.getLogger("musehub").setLevel(level.upper())
        return {}

    # ── Standard methods ──────────────────────────────────────────────────────

    if method == "ping":
        return {}

    raise _MCPError(_METHOD_NOT_FOUND, f"Method not found: {method!r}")


# ── Method handlers ───────────────────────────────────────────────────────────


def _handle_initialize(params: JSONObject) -> JSONObject:
    """Return server capabilities and protocol version per MCP 2025-11-25.

    Spec fix applied: ``serverInfo`` contains only ``name`` and ``version``.
    Capabilities live exclusively at the top level of the result.
    """
    return {
        "protocolVersion": _PROTOCOL_VERSION,
        "serverInfo": {
            "name": _SERVER_NAME,
            "version": _SERVER_VERSION,
        },
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
            "elicitation": {
                "form": {},
                "url": {},
            },
            "logging": {},
        },
            "instructions": (
                "MuseHub is the collaboration hub for Muse — the world's first "
                "domain-agnostic, multi-dimensional version control system. "
                "Muse tracks multidimensional state across any domain: MIDI (21 dimensions), "
                "Code (10 languages), Genomics, Circuit Design, and any custom domain plugin. "
                "Start with musehub_get_context to orient yourself within a repository, "
                "musehub_list_domains to discover domain plugins, "
                "musehub_get_domain to read a domain manifest, "
                "and musehub_get_view to inspect full multidimensional state. "
                "All repo-scoped tools accept either repo_id (UUID) or owner + slug. "
                "Elicitation (MCP 2025-11-25) is fully supported for interactive workflows. "
                "AI agents are first-class citizens: use an agent JWT for higher rate limits "
                "and activity feed visibility."
            ),
    }


def _handle_tools_list() -> JSONObject:
    """Return the full tool catalogue with MCP 2025-11-25 annotations injected."""
    from musehub.mcp.tools.musehub import MUSEHUB_WRITE_TOOL_NAMES, MUSEHUB_ELICITATION_TOOL_NAMES

    _READ_HINTS: dict[str, bool] = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
    _WRITE_HINTS: dict[str, bool] = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}
    _ELICIT_HINTS: dict[str, bool] = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": True}
    _DESTRUCTIVE_NAMES = {"muse_push"}

    import json as _json
    stripped = [{k: v for k, v in t.items() if k != "server_side"} for t in MCP_TOOLS]
    for t in stripped:
        if "annotations" not in t:
            name = t.get("name", "")
            if name in MUSEHUB_ELICITATION_TOOL_NAMES:
                t["annotations"] = _ELICIT_HINTS
            elif name in MUSEHUB_WRITE_TOOL_NAMES:
                hints = dict(_WRITE_HINTS)
                if name in _DESTRUCTIVE_NAMES:
                    hints["destructiveHint"] = True
                t["annotations"] = hints
            else:
                t["annotations"] = _READ_HINTS

    raw = _json.dumps(stripped)
    tools: list[JSONValue] = _json.loads(raw)
    return {"tools": tools}


async def _handle_tools_call(
    params: JSONObject,
    *,
    user_id: str | None,
    session: "MCPSession | None",
    is_agent: bool = False,
    agent_name: str | None = None,
) -> JSONObject:
    """Route a ``tools/call`` request to the appropriate executor."""
    name = params.get("name")
    arguments = params.get("arguments") or {}
    meta = params.get("_meta") or {}

    if not isinstance(name, str):
        raise _MCPError(_INVALID_PARAMS, "tools/call requires a 'name' string parameter")
    if not isinstance(arguments, dict):
        raise _MCPError(_INVALID_PARAMS, "tools/call 'arguments' must be an object")

    # Auth gate: write tools require an authenticated user.
    if name in MUSEHUB_WRITE_TOOL_NAMES and user_id is None:
        return _tool_error(f"Tool '{name}' requires authentication. Provide a Bearer JWT.")

    # Build tool call context with session for elicitation/progress support.
    from musehub.mcp.context import ToolCallContext
    progress_token: str | None = None
    if isinstance(meta, dict):
        pt = meta.get("progressToken")
        if isinstance(pt, str):
            progress_token = pt

    ctx = ToolCallContext(
        user_id=user_id,
        session=session,
        is_agent=is_agent,
        agent_name=agent_name,
    )

    # Resolve owner+slug → repo_id transparently so all repo-scoped tools
    # can be called with either addressing scheme.
    if not arguments.get("repo_id") and arguments.get("owner") and arguments.get("slug"):
        resolved_id, resolve_err = await _resolve_repo_id(
            str(arguments["owner"]), str(arguments["slug"])
        )
        if resolve_err:
            return _tool_error(resolve_err)
        arguments = {**arguments, "repo_id": resolved_id}

    try:
        return await _call_tool(name, arguments, ctx=ctx)
    except Exception as exc:
        logger.exception("Tool execution error (tool=%s): %s", name, exc)
        return _tool_error(f"Internal error executing tool '{name}': {exc}")


async def _resolve_repo_id(owner: str, slug: str) -> tuple[str, str | None]:
    """Resolve a repo_id from owner/slug addressing.

    Returns ``(repo_id, None)`` on success or ``("", error_message)`` on failure.
    Used so that all repo-scoped tools can accept either ``repo_id`` or
    ``owner`` + ``slug`` interchangeably.
    """
    try:
        from musehub.services.musehub_mcp_executor import _check_db_available
        if (err := _check_db_available()) is not None:
            return "", err.error_message or "Database unavailable"
        from musehub.db.database import AsyncSessionLocal
        from musehub.services import musehub_repository as _repo_svc
        async with AsyncSessionLocal() as db:
            repo = await _repo_svc.get_repo_by_owner_slug(db, owner, slug)
            if repo is None:
                return "", f"Repository '{owner}/{slug}' not found."
            return repo.repo_id, None
    except Exception as exc:
        return "", f"Failed to resolve repository '{owner}/{slug}': {exc}"


async def _call_tool(
    name: str,
    arguments: JSONObject,
    *,
    ctx: "ToolCallContext",
) -> JSONObject:
    """Delegate to the correct executor and wrap result in MCP content block."""
    from musehub.services import musehub_mcp_executor as exe

    user_id = ctx.user_id

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

    if name == "musehub_list_branches":
        result = await exe.execute_list_branches(_str("repo_id"))
    elif name == "musehub_list_commits":
        result = await exe.execute_list_commits(
            _str("repo_id"),
            branch=_str_or_none("branch"),
            limit=_int("limit", 20),
        )
    elif name == "musehub_read_file":
        result = await exe.execute_read_file(_str("repo_id"), _str("object_id"))
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
            domain=_str_or_none("domain"),
            tags=_list_str("tags"),
            limit=_int("limit", 20),
        )
    elif name == "musehub_list_domains":
        result = await exe.execute_list_domains(
            query=_str_or_none("query"),
            viewer_type=_str_or_none("viewer_type"),
            verified=bool(arguments["verified"]) if "verified" in arguments else None,
            limit=_int("limit", 20),
            offset=_int("offset", 0),
        )
    elif name == "musehub_get_domain":
        result = await exe.execute_get_domain(_str("scoped_id"))
    elif name == "musehub_get_domain_insights":
        result = await exe.execute_get_domain_insights(
            repo_id=_str("repo_id"),
            dimension=_str_or_none("dimension") or "overview",
            ref=_str_or_none("ref"),
        )
    elif name == "musehub_get_view":
        result = await exe.execute_get_view(
            repo_id=_str("repo_id"),
            ref=_str_or_none("ref"),
            dimension=_str_or_none("dimension"),
        )

    # ── Standard write tools ──────────────────────────────────────────────────

    elif name == "musehub_create_repo":
        from musehub.mcp.write_tools.repos import execute_create_repo
        result = await execute_create_repo(
            name=_str("name"),
            owner=user_id or "",
            owner_user_id=user_id or "",
            description=_str_or_none("description") or "",
            visibility=_str_or_none("visibility") or "public",
            tags=_list_str("tags") or None,
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
        _dim_ref = arguments.get("dimension_ref") or {}
        if not isinstance(_dim_ref, dict):
            _dim_ref = {}
        result = await execute_create_pr_comment(
            repo_id=_str("repo_id"),
            pr_id=_str("pr_id"),
            body=_str("body"),
            actor=user_id or "",
            target_type=str(_dim_ref.get("type", "general")),
            target_track=str(_dim_ref["track"]) if "track" in _dim_ref else None,
            target_beat_start=float(_dim_ref["beat_start"]) if "beat_start" in _dim_ref else None,  # type: ignore[arg-type]
            target_beat_end=float(_dim_ref["beat_end"]) if "beat_end" in _dim_ref else None,  # type: ignore[arg-type]
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

    # ── Elicitation-powered tools (MCP 2025-11-25) ────────────────────────────

    elif name == "musehub_create_with_preferences":
        from musehub.mcp.write_tools.elicitation_tools import execute_compose_with_preferences
        _raw_prefs = arguments.get("preferences")
        _prefs: dict[str, JSONValue] | None = (
            dict(_raw_prefs) if isinstance(_raw_prefs, dict) else None
        )
        result = await execute_compose_with_preferences(
            repo_id=_str_or_none("repo_id"),
            preferences=_prefs,
            ctx=ctx,
        )
    elif name == "musehub_review_pr_interactive":
        from musehub.mcp.write_tools.elicitation_tools import execute_review_pr_interactive
        result = await execute_review_pr_interactive(
            repo_id=_str("repo_id"),
            pr_id=_str("pr_id"),
            dimension=_str_or_none("dimension"),
            depth=_str_or_none("depth"),
            ctx=ctx,
        )
    elif name == "musehub_connect_streaming_platform":
        from musehub.mcp.write_tools.elicitation_tools import execute_connect_streaming_platform
        result = await execute_connect_streaming_platform(
            platform=_str_or_none("platform"),
            repo_id=_str_or_none("repo_id"),
            ctx=ctx,
        )
    elif name == "musehub_connect_daw_cloud":
        from musehub.mcp.write_tools.elicitation_tools import execute_connect_daw_cloud
        result = await execute_connect_daw_cloud(
            service=_str_or_none("service"),
            ctx=ctx,
        )
    elif name == "musehub_create_release_interactive":
        from musehub.mcp.write_tools.elicitation_tools import execute_create_release_interactive
        result = await execute_create_release_interactive(
            repo_id=_str("repo_id"),
            tag=_str_or_none("tag"),
            title=_str_or_none("title"),
            notes=_str_or_none("notes"),
            ctx=ctx,
        )

    # ── Muse CLI + auth tools ─────────────────────────────────────────────────

    elif name == "musehub_whoami":
        result = await exe.execute_whoami(user_id=user_id)
    elif name == "musehub_create_agent_token":
        result = await exe.execute_create_agent_token(
            user_id=user_id or "",
            agent_name=_str("agent_name"),
            expires_in_days=_int("expires_in_days", 90),
        )
    elif name == "muse_push":
        _raw_commits = arguments.get("commits")
        _raw_snapshots = arguments.get("snapshots")
        _raw_objects = arguments.get("objects")
        result = await exe.execute_muse_push(
            repo_id=_str("repo_id"),
            branch=_str("branch"),
            head_commit_id=_str("head_commit_id"),
            commits=list(_raw_commits) if isinstance(_raw_commits, list) else [],
            snapshots=list(_raw_snapshots) if isinstance(_raw_snapshots, list) else None,
            objects=list(_raw_objects) if isinstance(_raw_objects, list) else None,
            force=_bool("force", False),
            user_id=user_id or "",
        )
    elif name == "muse_pull":
        result = await exe.execute_muse_pull(
            repo_id=_str("repo_id"),
            branch=_str_or_none("branch"),
            since_commit_id=_str_or_none("since_commit_id"),
            object_ids=_list_str("object_ids"),
        )
    elif name == "muse_remote":
        result = await exe.execute_muse_remote(
            owner=_str("owner"),
            slug=_str("slug"),
            ref=_str_or_none("ref"),
        )
    elif name == "muse_config":
        result = await exe.execute_muse_config(
            key=_str_or_none("key"),
            value=_str_or_none("value"),
        )
    elif name == "musehub_publish_domain":
        _raw_capabilities = arguments.get("capabilities")
        result = await exe.execute_musehub_publish_domain(
            author_slug=_str("author_slug"),
            slug=_str("slug"),
            display_name=_str("display_name"),
            description=_str("description"),
            capabilities=dict(_raw_capabilities) if isinstance(_raw_capabilities, dict) else {},
            viewer_type=_str("viewer_type"),
            version=_str("version") or "0.1.0",
            user_id=user_id or "",
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


def _handle_notifications_cancelled(
    params: JSONObject,
    *,
    session: "MCPSession | None",
) -> None:
    """Cancel a pending elicitation Future on client cancellation.

    Called when the client sends ``notifications/cancelled`` with the request
    ID of an outstanding ``elicitation/create`` request.
    """
    if session is None:
        return
    request_id = params.get("requestId")
    if request_id is None:
        return
    from musehub.mcp.session import cancel_elicitation
    cancelled = cancel_elicitation(session, request_id)  # type: ignore[arg-type]
    if cancelled:
        logger.info(
            "Elicitation cancelled by client (session %.8s..., id=%s)",
            session.session_id,
            request_id,
        )


def _handle_elicitation_complete(
    params: JSONObject,
    *,
    session: "MCPSession | None",
) -> None:
    """Resolve a pending URL-mode elicitation when the out-of-band flow completes.

    The server sends ``notifications/elicitation/complete`` after an external
    OAuth / URL flow finishes. The client echoes it here; we resolve the Future
    that the tool is awaiting.
    """
    if session is None:
        return
    elicitation_id = params.get("elicitationId")
    if not isinstance(elicitation_id, str):
        return
    # URL-mode elicitations use the elicitation_id as the pending key.
    from musehub.mcp.session import resolve_elicitation
    resolved = resolve_elicitation(session, elicitation_id, {"action": "accept"})
    if resolved:
        logger.info(
            "URL elicitation completed (session %.8s..., id=%s)",
            session.session_id,
            elicitation_id,
        )


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

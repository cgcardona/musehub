"""MuseHub MCP — Full Streamable HTTP transport (MCP 2025-11-25).

Implements the complete Streamable HTTP transport spec:

  POST /mcp — client → server messages (requests, notifications, responses).
    - Returns ``application/json`` for most requests (resources, prompts, ping).
    - Returns ``text/event-stream`` when a tool needs SSE (elicitation, progress).
    - Returns 202 Accepted for notifications (no body).
    - Issues ``Mcp-Session-Id`` header on successful ``initialize``.
    - Validates ``Mcp-Session-Id`` on all subsequent requests.
    - Validates ``MCP-Protocol-Version`` header on non-initialize requests.
    - Validates ``Origin`` header to prevent DNS-rebinding attacks.

  GET /mcp — server → client SSE push channel.
    - Opens a persistent ``text/event-stream`` for server-initiated messages.
    - Supports ``Last-Event-ID`` for reconnection replay.
    - Injects heartbeat comments every 15 s to keep proxies alive.

  DELETE /mcp — client-initiated session termination.
    - Returns 200 on success, 404 if session unknown.

Auth model (unchanged from 2025-03-26):
  - ``Authorization: Bearer <jwt>`` → authenticated; user_id from JWT ``sub``.
  - No token → anonymous; read-only tools work, write tools return isError=true.
  - Invalid/expired token → 401.

Security:
  - Origin header validated on all POST/GET/DELETE requests.
  - Allowed origins configured via ``MUSEHUB_ALLOWED_ORIGINS`` env var
    (comma-separated). Defaults to localhost in dev mode.
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from musehub.rate_limits import limiter, MCP_LIMIT

from musehub.contracts.json_types import JSONObject, JSONValue
from musehub.mcp.dispatcher import handle_batch, handle_request
from musehub.mcp.session import (
    MCPSession,
    SessionCapacityError,
    create_session,
    delete_session,
    get_session,
    push_to_session,
    register_sse_queue,
    resolve_elicitation,
)
from musehub.mcp.sse import SSE_CONTENT_TYPE, heartbeat_stream, sse_heartbeat

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP"])

_PROTOCOL_VERSION = "2025-11-25"

# ── Origin validation ─────────────────────────────────────────────────────────

_ALLOWED_ORIGINS: frozenset[str] = frozenset(
    o.strip()
    for o in os.environ.get(
        "MUSEHUB_ALLOWED_ORIGINS",
        "http://localhost,http://127.0.0.1,https://musehub.app",
    ).split(",")
    if o.strip()
)

_ALWAYS_ALLOW_ORIGINS: frozenset[str] = frozenset({
    "http://localhost",
    "http://127.0.0.1",
})


def _validate_origin(request: Request) -> bool:
    """Return True if the request origin is allowed.

    Per the Streamable HTTP spec, servers MUST validate Origin to prevent
    DNS-rebinding attacks. Requests without an Origin header are allowed
    (e.g. curl, Postman, stdio bridge tools).
    """
    origin = request.headers.get("Origin")
    if origin is None:
        return True  # Non-browser clients don't send Origin.

    # Normalise: strip path component, keep scheme+host+port.
    try:
        parsed = urlparse(origin)
        normalised = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return False

    return normalised in _ALLOWED_ORIGINS or normalised in _ALWAYS_ALLOW_ORIGINS


# ── Auth helper ───────────────────────────────────────────────────────────────


class _AuthResult:
    """Parsed authentication result from a Bearer JWT."""

    __slots__ = ("user_id", "is_agent", "agent_name")

    def __init__(
        self,
        user_id: str | None,
        is_agent: bool = False,
        agent_name: str | None = None,
    ) -> None:
        self.user_id = user_id
        self.is_agent = is_agent
        self.agent_name = agent_name


async def _extract_auth(request: Request) -> _AuthResult | Response:
    """Return an :class:`_AuthResult` from JWT, anonymous result, or a 401 Response.

    Returns a ``Response`` object (not an ``_AuthResult``) when the token is
    invalid. Callers must check ``isinstance(result, Response)`` and return early.

    Agent tokens (``token_type: "agent"`` JWT claim) are identified here and
    propagated into the :class:`~musehub.mcp.context.ToolCallContext` so that
    downstream services can apply higher rate limits and tag activity events
    with the "agent" badge.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _AuthResult(user_id=None)

    token_str = auth_header[7:]
    try:
        from musehub.auth.tokens import validate_access_code
        claims = validate_access_code(token_str)
        is_agent = claims.get("token_type") == "agent"
        return _AuthResult(
            user_id=claims.get("sub"),
            is_agent=is_agent,
            agent_name=claims.get("agent_name") if is_agent else None,
        )
    except Exception:
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid or expired access token."},
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── POST /mcp ─────────────────────────────────────────────────────────────────


@router.post(
    "/mcp",
    operation_id="mcpEndpoint",
    summary="MCP Streamable HTTP — POST endpoint (2025-11-25)",
    include_in_schema=True,
)
@limiter.limit(MCP_LIMIT)
async def mcp_post(request: Request) -> Response:
    """MCP Streamable HTTP POST endpoint.

    Handles all client→server JSON-RPC messages. Returns ``application/json``
    for most requests, ``text/event-stream`` when the response requires SSE
    (tool calls that use elicitation or progress streaming), and
    ``202 Accepted`` for notifications.

    The ``initialize`` method issues an ``Mcp-Session-Id`` response header.
    All subsequent requests must include that header.
    """
    # ── Security: Origin validation ───────────────────────────────────────────
    if not _validate_origin(request):
        return JSONResponse(
            status_code=403,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Forbidden: invalid Origin header"},
            },
        )

    # ── Auth ──────────────────────────────────────────────────────────────────
    auth_or_resp = await _extract_auth(request)
    if isinstance(auth_or_resp, Response):
        return auth_or_resp
    auth: _AuthResult = auth_or_resp
    user_id: str | None = auth.user_id

    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = await request.body()
        raw = json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            },
        )

    # ── Determine if this is initialize or a subsequent request ──────────────
    # For batches, use the method of the first request.
    def _first_method(r: object) -> str | None:
        if isinstance(r, dict):
            m = r.get("method")
            return m if isinstance(m, str) else None
        if isinstance(r, list) and r:
            return r[0].get("method") if isinstance(r[0], dict) else None
        return None

    first_method = _first_method(raw)
    is_initialize = first_method == "initialize"

    # ── Session management ────────────────────────────────────────────────────
    session: MCPSession | None = None
    session_id_header = request.headers.get("Mcp-Session-Id")

    if not is_initialize:
        # Validate MCP-Protocol-Version on non-initialize requests.
        proto_ver = request.headers.get("MCP-Protocol-Version")
        if proto_ver and proto_ver not in ("2025-11-25", "2025-03-26"):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": f"Unsupported MCP-Protocol-Version: {proto_ver!r}",
                    },
                },
            )

        if session_id_header:
            session = get_session(session_id_header)
            if session is None:
                # Session expired or unknown → client must re-initialize.
                return JSONResponse(
                    status_code=404,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32600,
                            "message": "Session not found. Send a new InitializeRequest without Mcp-Session-Id.",
                        },
                    },
                )

    # ── Check if this is an elicitation response (client→server) ─────────────
    # When the client sends the result of an elicitation/create back, it's a
    # JSON-RPC *response* (has "result" or "error" but no "method"). Route it
    # to the session's pending Future resolver.
    if session and isinstance(raw, dict) and "method" not in raw and "id" in raw:
        req_id = raw.get("id")
        if "result" in raw and req_id is not None:
            resolved = resolve_elicitation(session, req_id, raw["result"])
            if resolved:
                return Response(status_code=202)
        # Unknown response — ignore per spec.
        return Response(status_code=202)

    # ── Dispatch ──────────────────────────────────────────────────────────────
    try:
        if isinstance(raw, list):
            responses = await handle_batch(
                raw, user_id=user_id, session=session,
                is_agent=auth.is_agent, agent_name=auth.agent_name,
            )
            if not responses:
                return Response(status_code=202)
            return JSONResponse(content=responses)

        elif isinstance(raw, dict):
            # Detect if tool needs SSE streaming (elicitation tools set this).
            needs_sse = _method_needs_sse(raw) and session is not None

            if needs_sse and session is not None:
                return _make_sse_tool_response(
                    raw, user_id=user_id, session=session,
                    is_agent=auth.is_agent, agent_name=auth.agent_name,
                )

            resp = await handle_request(
                raw, user_id=user_id, session=session,
                is_agent=auth.is_agent, agent_name=auth.agent_name,
            )
            if resp is None:
                return Response(status_code=202)

            # Attach Mcp-Session-Id on initialize.
            if is_initialize:
                try:
                    new_session = _create_session_from_initialize(raw, user_id)
                except SessionCapacityError as cap_exc:
                    logger.warning("MCP session capacity exceeded: %s", cap_exc)
                    return JSONResponse(
                        status_code=503,
                        content={
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": -32000,
                                "message": str(cap_exc),
                            },
                        },
                        headers={"Retry-After": "5"},
                    )
                return JSONResponse(
                    content=resp,
                    headers={"Mcp-Session-Id": new_session.session_id},
                )

            return JSONResponse(content=resp)

        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": "Request must be an object or array",
                    },
                },
            )

    except Exception as exc:
        logger.exception("Unhandled error in POST /mcp: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            },
        )


# ── GET /mcp ──────────────────────────────────────────────────────────────────


@router.get(
    "/mcp",
    operation_id="mcpSseStream",
    summary="MCP Streamable HTTP — GET SSE push channel (2025-11-25)",
    include_in_schema=True,
)
async def mcp_get(request: Request) -> Response:
    """Open a persistent SSE stream for server-initiated messages.

    The client MUST include ``Accept: text/event-stream`` and a valid
    ``Mcp-Session-Id``. Returns 405 if SSE is not accepted.

    Supports ``Last-Event-ID`` header for reconnection and event replay.
    Heartbeat comments are sent every 15 s to keep proxies alive.

    Server-initiated messages delivered on this stream:
    - ``notifications/progress`` — tool progress updates.
    - ``elicitation/create`` — requests for user input.
    - ``notifications/elicitation/complete`` — URL mode completion signals.
    """
    if not _validate_origin(request):
        return Response(status_code=403)

    accept = request.headers.get("Accept", "")
    if "text/event-stream" not in accept:
        return Response(status_code=405, content="SSE requires Accept: text/event-stream")

    session_id = request.headers.get("Mcp-Session-Id")
    if not session_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Mcp-Session-Id header required for GET /mcp SSE stream"},
        )

    session = get_session(session_id)
    if session is None:
        return Response(status_code=404, content="Session not found or expired")

    last_event_id = request.headers.get("Last-Event-ID")

    async def event_generator() -> AsyncIterator[str]:
        async for event_text in heartbeat_stream(
            register_sse_queue(session, last_event_id),
            interval_seconds=15.0,
        ):
            yield event_text

    return StreamingResponse(
        event_generator(),
        media_type=SSE_CONTENT_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering.
        },
    )


# ── DELETE /mcp ───────────────────────────────────────────────────────────────


@router.delete(
    "/mcp",
    operation_id="mcpDeleteSession",
    summary="MCP Streamable HTTP — DELETE session (2025-11-25)",
    include_in_schema=True,
)
async def mcp_delete(request: Request) -> Response:
    """Client-initiated session termination.

    Closes all open SSE streams for the session and cancels any pending
    elicitation Futures. Returns 200 on success, 404 if unknown.
    """
    if not _validate_origin(request):
        return Response(status_code=403)

    session_id = request.headers.get("Mcp-Session-Id")
    if not session_id:
        return JSONResponse(
            status_code=400,
            content={"error": "Mcp-Session-Id header required"},
        )

    deleted = delete_session(session_id)
    if not deleted:
        return Response(status_code=404, content="Session not found")

    logger.info("MCP session terminated by client: %.8s...", session_id)
    return Response(status_code=200)


# ── GET /mcp/docs.json ────────────────────────────────────────────────────────


@router.get(
    "/mcp/docs.json",
    operation_id="mcpDocsJson",
    summary="MCP capability manifest — machine-readable JSON",
    include_in_schema=True,
)
async def mcp_docs_json() -> JSONResponse:
    """Return a machine-readable JSON manifest of all MCP capabilities.

    This endpoint is the programmatic complement to ``GET /mcp/docs``.
    AI agents and tool integrators can fetch this to discover:
    - The full tool catalogue (names, descriptions, input schemas)
    - All static and templated resources (URIs, names, descriptions)
    - All available prompts (names, descriptions, arguments)
    - Server info and protocol version

    No authentication required — this is intentionally public so agents
    can bootstrap without prior credentials.
    """
    from musehub.mcp.tools import MCP_TOOLS
    from musehub.mcp.resources import STATIC_RESOURCES, RESOURCE_TEMPLATES
    from musehub.mcp.prompts import PROMPT_CATALOGUE

    tools_out = [
        {k: v for k, v in t.items() if k != "server_side"}
        for t in MCP_TOOLS
    ]
    resources_out = [
        {
            "uri": r.get("uri"),
            "name": r.get("name"),
            "description": r.get("description"),
            "mimeType": r.get("mimeType"),
        }
        for r in STATIC_RESOURCES
    ]
    templates_out = [
        {
            "uriTemplate": t.get("uriTemplate"),
            "name": t.get("name"),
            "description": t.get("description"),
            "mimeType": t.get("mimeType"),
        }
        for t in RESOURCE_TEMPLATES
    ]
    prompts_out = [
        {
            "name": p["name"],
            "description": p["description"],
            "arguments": p.get("arguments", []),
        }
        for p in PROMPT_CATALOGUE
    ]

    return JSONResponse(
        content={
            "server": {
                "name": "musehub-mcp",
                "version": "1.1.0",
                "protocolVersion": _PROTOCOL_VERSION,
                "endpoint": "/mcp",
                "docsUrl": "/mcp/docs",
            },
            "tools": tools_out,
            "resources": resources_out,
            "resourceTemplates": templates_out,
            "prompts": prompts_out,
        },
        headers={"Cache-Control": "public, max-age=300"},
    )


# ── GET /mcp/docs ─────────────────────────────────────────────────────────────


@router.get(
    "/mcp/docs",
    operation_id="mcpDocs",
    summary="MCP reference — human-readable documentation page",
    include_in_schema=True,
)
async def mcp_docs(request: Request) -> Response:
    """Render a human-readable reference page for the MuseHub MCP server.

    Lists all tools, resources, resource templates, and prompts with their
    descriptions and input schemas. Also shows:
    - Connection instructions (endpoint URL, auth model, protocol version)
    - Agent onboarding quick-start guide
    - Link to ``/mcp/docs.json`` for machine-readable access

    No authentication required.
    """
    try:
        from musehub.api.routes.musehub._templates import templates
        from musehub.mcp.tools import MCP_TOOLS
        from musehub.mcp.resources import STATIC_RESOURCES, RESOURCE_TEMPLATES
        from musehub.mcp.prompts import PROMPT_CATALOGUE

        ctx = {
            "request": request,
            "tools": MCP_TOOLS,
            "static_resources": STATIC_RESOURCES,
            "resource_templates": RESOURCE_TEMPLATES,
            "prompts": PROMPT_CATALOGUE,
            "protocol_version": _PROTOCOL_VERSION,
        }
        return templates.TemplateResponse(request, "musehub/pages/mcp_docs.html", ctx)
    except Exception as exc:
        logger.warning("MCP docs template missing, falling back to JSON redirect: %s", exc)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/mcp/docs.json")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_session_from_initialize(
    raw: JSONObject,
    user_id: str | None,
) -> MCPSession:
    """Extract client capabilities from initialize params and create a session."""
    params = raw.get("params") or {}
    client_caps: JSONObject = {}
    if isinstance(params, dict):
        caps = params.get("capabilities")
        if isinstance(caps, dict):
            client_caps = caps
    return create_session(user_id, client_capabilities=client_caps)


# Tools that may use elicitation or progress streaming (SSE required).
_SSE_TOOL_NAMES: frozenset[str] = frozenset({
    "musehub_create_with_preferences",
    "musehub_review_pr_interactive",
    "musehub_connect_streaming_platform",
    "musehub_connect_daw_cloud",
    "musehub_create_release_interactive",
})


def _method_needs_sse(raw: JSONObject) -> bool:
    """Return True if this request should be streamed as SSE."""
    if raw.get("method") != "tools/call":
        return False
    params = raw.get("params")
    if not isinstance(params, dict):
        return False
    name = params.get("name")
    return name in _SSE_TOOL_NAMES


def _make_sse_tool_response(
    raw: JSONObject,
    *,
    user_id: str | None,
    session: MCPSession,
    is_agent: bool = False,
    agent_name: str | None = None,
) -> StreamingResponse:
    """Return a StreamingResponse that runs the tool and streams results via SSE."""
    from musehub.mcp.sse import sse_response, sse_notification

    raw_id = raw.get("id")
    req_id: str | int | None = raw_id if isinstance(raw_id, (str, int)) else None

    async def generator() -> AsyncIterator[str]:
        try:
            result = await handle_request(
                raw, user_id=user_id, session=session,
                is_agent=is_agent, agent_name=agent_name,
            )
            if result is not None:
                yield sse_response(req_id, result)
        except Exception as exc:
            logger.exception("SSE tool call error: %s", exc)
            error_payload: dict[str, JSONValue] = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(exc)},
            }
            from musehub.mcp.sse import sse_event
            yield sse_event(error_payload)

    return StreamingResponse(
        generator(),
        media_type=SSE_CONTENT_TYPE,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

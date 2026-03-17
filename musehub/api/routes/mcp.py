"""MuseHub MCP — POST /mcp HTTP Streamable endpoint.

Single-endpoint JSON-RPC 2.0 transport following the MCP 2025-03-26 specification.

Auth model:
  - ``Authorization: Bearer <jwt>`` → authenticated; user_id extracted from JWT ``sub``
  - No token → anonymous; read-only tools succeed, write tools return isError=true
  - Invalid/expired/revoked token → 401

Request shapes:
  - Single request object → single response object
  - JSON array of requests → batch; responses for all non-notifications returned
  - Notification (no ``id``) → 202 Accepted, no body

Response codes:
  - 200 OK  — normal response (single or batch)
  - 202 Accepted — notification received (no body)
  - 400 Bad Request — malformed JSON or invalid request shape
  - 401 Unauthorized — invalid/expired/revoked token (only when token is provided)
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from musehub.auth.dependencies import optional_token
from musehub.contracts.json_types import JSONObject
from musehub.mcp.dispatcher import handle_batch, handle_request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP"])


@router.post(
    "/mcp",
    operation_id="mcpEndpoint",
    summary="MCP JSON-RPC 2.0 endpoint (HTTP Streamable transport)",
    response_class=JSONResponse,
    include_in_schema=True,
)
async def mcp_endpoint(request: Request) -> Response:
    """MCP HTTP Streamable transport — single ``POST /mcp`` endpoint.

    Accepts ``application/json`` bodies containing either a single JSON-RPC 2.0
    request object or a batch array. Returns the corresponding response(s).

    **Authentication**: Pass ``Authorization: Bearer <jwt>`` for write access.
    Without a token, read-only tools work; write tools return ``isError=true``.

    **Batch support**: Send a JSON array to dispatch multiple calls in one
    request. Responses are returned in the same order, excluding notifications.
    """
    # ── Extract user identity ─────────────────────────────────────────────────
    user_id: str | None = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_str = auth_header[7:]
        try:
            from musehub.auth.tokens import validate_access_code, AccessCodeError
            from musehub.auth.dependencies import _check_and_register_token
            claims = validate_access_code(token_str)
            user_id = claims.get("sub")
        except Exception:
            # Invalid token → 401
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired access token."},
                headers={"WWW-Authenticate": "Bearer"},
            )

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

    # ── Dispatch ──────────────────────────────────────────────────────────────
    try:
        if isinstance(raw, list):
            # Batch request
            responses = await handle_batch(raw, user_id=user_id)
            if not responses:
                # All were notifications
                return Response(status_code=202)
            return JSONResponse(content=responses)

        elif isinstance(raw, dict):
            # Single request
            resp = await handle_request(raw, user_id=user_id)
            if resp is None:
                # Notification — no response body
                return Response(status_code=202)
            return JSONResponse(content=resp)

        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Request must be an object or array"},
                },
            )

    except Exception as exc:
        logger.exception("Unhandled error in /mcp endpoint: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            },
        )

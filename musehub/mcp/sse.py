"""SSE (Server-Sent Events) helpers for MCP Streamable HTTP transport.

Provides event formatting per the HTML Living Standard:
  https://html.spec.whatwg.org/multipage/server-sent-events.html

Every outbound MCP server-to-client message (elicitation/create, progress
notifications, tool responses) is formatted with :func:`sse_event` before being
pushed into session SSE queues or streamed via :func:`sse_stream_response`.

Design notes:
- ``data:`` lines must not contain bare newlines — each embedded newline
  is split into a separate ``data:`` line per the spec.
- ``event_id`` monotonically increments per session using a simple counter;
  callers that need replay support should pass the counter value.
- The heartbeat (``": heartbeat"`` comment) keeps proxies alive without
  affecting the event stream semantics.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from musehub.contracts.json_types import JSONObject, JSONValue

logger = logging.getLogger(__name__)

# SSE content type required by the spec.
SSE_CONTENT_TYPE = "text/event-stream"

# Heartbeat comment text — sent every N seconds on GET /mcp streams.
_HEARTBEAT = ": heartbeat\n\n"


def sse_event(
    data: JSONObject,
    *,
    event_id: str | None = None,
    event_type: str | None = None,
    retry_ms: int | None = None,
) -> str:
    """Format a JSON object as an SSE event string.

    Args:
        data: The JSON-serialisable payload. Encoded as compact JSON on a
            single ``data:`` line (embedded newlines are split per the spec).
        event_id: Optional ``id:`` field. Clients use this as ``Last-Event-ID``
            on reconnection.
        event_type: Optional ``event:`` field (default stream type if omitted).
        retry_ms: Optional ``retry:`` reconnection timeout in milliseconds.

    Returns:
        A fully-formatted SSE event string ending with ``\\n\\n``.
    """
    parts: list[str] = []

    if event_id is not None:
        parts.append(f"id: {event_id}")

    if event_type is not None:
        parts.append(f"event: {event_type}")

    if retry_ms is not None:
        parts.append(f"retry: {retry_ms}")

    # Encode data as compact JSON, splitting on newlines per spec.
    encoded = json.dumps(data, separators=(",", ":"), default=str)
    for line in encoded.split("\n"):
        parts.append(f"data: {line}")

    return "\n".join(parts) + "\n\n"


def sse_heartbeat() -> str:
    """Return the SSE heartbeat comment string."""
    return _HEARTBEAT


def sse_notification(
    method: str,
    params: JSONObject | None = None,
    *,
    event_id: str | None = None,
) -> str:
    """Format an MCP JSON-RPC notification as an SSE event.

    Args:
        method: JSON-RPC method name (e.g. ``"notifications/progress"``).
        params: Optional parameters dict.
        event_id: Optional SSE event ID.

    Returns:
        Formatted SSE event string.
    """
    payload: dict[str, JSONValue] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    return sse_event(payload, event_id=event_id)


def sse_request(
    req_id: str | int,
    method: str,
    params: JSONObject | None = None,
    *,
    event_id: str | None = None,
) -> str:
    """Format an MCP JSON-RPC request (server→client) as an SSE event.

    Used for server-initiated requests such as ``elicitation/create``.

    Args:
        req_id: JSON-RPC request ID. The client echoes this in its response.
        method: JSON-RPC method name.
        params: Optional parameters dict.
        event_id: Optional SSE event ID.

    Returns:
        Formatted SSE event string.
    """
    payload: dict[str, JSONValue] = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params
    return sse_event(payload, event_id=event_id)


def sse_response(
    req_id: str | int | None,
    result: JSONObject,
    *,
    event_id: str | None = None,
) -> str:
    """Format an MCP JSON-RPC success response as an SSE event.

    Used to stream tool call results back to the client when the POST response
    is a ``text/event-stream`` rather than a single JSON body.

    Args:
        req_id: JSON-RPC request ID from the original client request.
        result: The result payload dict.
        event_id: Optional SSE event ID.

    Returns:
        Formatted SSE event string.
    """
    payload: dict[str, JSONValue] = {"jsonrpc": "2.0", "id": req_id, "result": result}
    return sse_event(payload, event_id=event_id)


async def heartbeat_stream(
    event_stream: AsyncIterator[str],
    *,
    interval_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Interleave heartbeat SSE comments into an existing async event stream.

    Yields events from ``event_stream`` unchanged and injects a heartbeat
    comment if no event has been sent for ``interval_seconds``.

    Args:
        event_stream: Upstream async iterator of SSE event strings.
        interval_seconds: Maximum silence duration before injecting a heartbeat.

    Yields:
        SSE event strings, including injected heartbeat comments.
    """
    import asyncio

    aiter = event_stream.__aiter__()
    pending: asyncio.Task[str] | None = None

    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(aiter.__anext__())

            try:
                event = await asyncio.wait_for(
                    asyncio.shield(pending), timeout=interval_seconds
                )
                pending = None
                yield event
            except asyncio.TimeoutError:
                yield _HEARTBEAT
    except StopAsyncIteration:
        return
    finally:
        if pending is not None and not pending.done():
            pending.cancel()

"""MCP Session Store — stateful connection management for MCP 2025-11-25.

Manages per-client sessions required by the Streamable HTTP transport:
- Cryptographically secure session IDs returned in ``Mcp-Session-Id`` header
- Pending elicitation Futures (correlate elicitation/create ↔ client response)
- SSE queues for GET /mcp push channels
- TTL-based expiry with background cleanup

Design: In-process only. Documented upgrade path to Redis for multi-replica
deployments — replace the module-level ``_SESSIONS`` dict with a Redis hash
and use ``asyncio.Event`` cross-process synchronisation.
"""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from musehub.contracts.json_types import JSONObject

logger = logging.getLogger(__name__)

# Session TTL in seconds (1 hour); reset on each activity.
_SESSION_TTL_SECONDS = 3600

# Maximum number of recent SSE events buffered per session for Last-Event-ID replay.
_SSE_BUFFER_SIZE = 50


@dataclass
class MCPSession:
    """Stateful MCP session for the Streamable HTTP transport.

    Attributes:
        session_id: Cryptographically secure, globally unique session identifier.
        user_id: Authenticated user derived from JWT ``sub`` claim, or ``None``
            for anonymous sessions.
        client_capabilities: Capabilities advertised by the client during
            ``initialize``, including elicitation mode support.
        pending: Mapping from elicitation request ID → ``asyncio.Future`` whose
            result is set when the client sends the elicitation response.
        sse_queues: Active GET /mcp SSE consumers. Each entry is an
            ``asyncio.Queue`` fed by :func:`push_to_session`.
        event_buffer: Ring buffer of recent (event_id, data) pairs for
            ``Last-Event-ID`` replay on reconnection.
        created_at: Unix timestamp of session creation.
        last_active: Unix timestamp of last activity (reset on each request).
    """

    session_id: str
    user_id: str | None
    client_capabilities: JSONObject
    pending: dict[str | int, asyncio.Future[JSONObject]] = field(
        default_factory=dict
    )
    sse_queues: list[asyncio.Queue[str | None]] = field(default_factory=list)
    event_buffer: list[tuple[str, str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        """Reset the activity timestamp to defer session expiry."""
        self.last_active = time.monotonic()

    def is_expired(self) -> bool:
        """Return True if the session TTL has elapsed since last activity."""
        return (time.monotonic() - self.last_active) > _SESSION_TTL_SECONDS

    def supports_elicitation_form(self) -> bool:
        """Return True if the client declared form-mode elicitation support."""
        elicitation = self.client_capabilities.get("elicitation")
        if not isinstance(elicitation, dict):
            return False
        # Empty dict ≡ form-only per spec backwards compat.
        return "form" in elicitation or len(elicitation) == 0

    def supports_elicitation_url(self) -> bool:
        """Return True if the client declared URL-mode elicitation support."""
        elicitation = self.client_capabilities.get("elicitation")
        if not isinstance(elicitation, dict):
            return False
        return "url" in elicitation


# ── Module-level registry ─────────────────────────────────────────────────────

_SESSIONS: dict[str, MCPSession] = {}
_cleanup_task: asyncio.Task[None] | None = None


def create_session(
    user_id: str | None,
    client_capabilities: JSONObject,
) -> MCPSession:
    """Create a new MCP session and register it in the store.

    Args:
        user_id: Authenticated user ID from JWT, or ``None`` for anonymous.
        client_capabilities: Client capability map from ``initialize`` params.

    Returns:
        The newly created :class:`MCPSession`.
    """
    session_id = secrets.token_urlsafe(32)
    session = MCPSession(
        session_id=session_id,
        user_id=user_id,
        client_capabilities=client_capabilities,
    )
    _SESSIONS[session_id] = session
    logger.info("MCP session created: %.8s... user=%s", session_id, user_id)
    _ensure_cleanup_running()
    return session


def get_session(session_id: str) -> MCPSession | None:
    """Look up a session by ID and touch its activity timestamp.

    Returns ``None`` if the session does not exist or has expired.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        return None
    if session.is_expired():
        delete_session(session_id)
        return None
    session.touch()
    return session


def delete_session(session_id: str) -> bool:
    """Terminate a session, closing all open SSE streams.

    Args:
        session_id: Session to delete.

    Returns:
        ``True`` if the session existed and was deleted, ``False`` otherwise.
    """
    session = _SESSIONS.pop(session_id, None)
    if session is None:
        return False

    # Signal all open GET /mcp SSE streams to close.
    for queue in session.sse_queues:
        queue.put_nowait(None)  # None is the sentinel for stream termination.

    # Cancel any pending elicitation Futures.
    for fut in session.pending.values():
        if not fut.done():
            fut.cancel()

    logger.info("MCP session deleted: %.8s...", session_id)
    return True


# ── SSE push ──────────────────────────────────────────────────────────────────


def push_to_session(session: MCPSession, event_text: str) -> None:
    """Broadcast a serialised SSE event string to all open GET /mcp streams.

    Buffers the event for ``Last-Event-ID`` replay.

    Args:
        session: Target session.
        event_text: Fully-formatted SSE event string (including trailing ``\\n\\n``).
    """
    # Append to ring buffer (drop oldest if full).
    if len(session.event_buffer) >= _SSE_BUFFER_SIZE:
        session.event_buffer.pop(0)
    session.event_buffer.append(("", event_text))

    for queue in list(session.sse_queues):
        try:
            queue.put_nowait(event_text)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for session %.8s..., dropping event", session.session_id)


async def register_sse_queue(
    session: MCPSession,
    last_event_id: str | None = None,
) -> AsyncIterator[str]:
    """Register a new SSE consumer and yield events until disconnection.

    Replays buffered events if ``last_event_id`` is provided, then streams
    live events from the queue. Yields ``None``-sentinel as end-of-stream.

    Args:
        session: Active session to attach to.
        last_event_id: ``Last-Event-ID`` header value for replay, or ``None``.

    Yields:
        Serialised SSE event strings.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)
    session.sse_queues.append(queue)

    try:
        # Replay buffered events after the given last_event_id.
        if last_event_id is not None:
            replaying = False
            for buf_id, buf_text in session.event_buffer:
                if replaying:
                    yield buf_text
                elif buf_id == last_event_id:
                    replaying = True

        # Stream live events.
        while True:
            item = await queue.get()
            if item is None:
                break  # Session terminated.
            yield item
    finally:
        try:
            session.sse_queues.remove(queue)
        except ValueError:
            pass


# ── Elicitation pending request helpers ───────────────────────────────────────


def create_pending_elicitation(
    session: MCPSession,
    request_id: str | int,
) -> asyncio.Future[JSONObject]:
    """Register a pending elicitation and return its Future.

    The Future is resolved by :func:`resolve_elicitation` when the client
    sends the elicitation response.

    Args:
        session: Session on which the elicitation is pending.
        request_id: JSON-RPC ID of the ``elicitation/create`` request.

    Returns:
        ``asyncio.Future`` that will be set to the client's response dict.
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[JSONObject] = loop.create_future()
    session.pending[request_id] = fut
    return fut


def resolve_elicitation(
    session: MCPSession,
    request_id: str | int,
    result: JSONObject,
) -> bool:
    """Resolve a pending elicitation Future with the client's response.

    Args:
        session: Session owning the pending elicitation.
        request_id: JSON-RPC ID matching the ``elicitation/create`` request.
        result: Client elicitation result dict (``action`` + optional ``content``).

    Returns:
        ``True`` if the pending Future was found and resolved, ``False`` otherwise.
    """
    fut = session.pending.pop(request_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(result)
    return True


def cancel_elicitation(session: MCPSession, request_id: str | int) -> bool:
    """Cancel a pending elicitation Future (e.g. on ``notifications/cancelled``).

    Args:
        session: Session owning the pending elicitation.
        request_id: JSON-RPC ID to cancel.

    Returns:
        ``True`` if the Future was found and cancelled.
    """
    fut = session.pending.pop(request_id, None)
    if fut is None or fut.done():
        return False
    fut.cancel()
    return True


# ── Background cleanup ────────────────────────────────────────────────────────


def _ensure_cleanup_running() -> None:
    """Start the background cleanup task if it is not already running."""
    global _cleanup_task
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = loop.create_task(_cleanup_loop(), name="mcp-session-cleanup")


async def _cleanup_loop() -> None:
    """Periodically expire stale sessions (runs every 5 minutes)."""
    while True:
        await asyncio.sleep(300)
        expired = [sid for sid, s in list(_SESSIONS.items()) if s.is_expired()]
        for sid in expired:
            delete_session(sid)
        if expired:
            logger.info("MCP session cleanup: expired %d session(s)", len(expired))

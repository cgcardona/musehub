"""MCP Tool Call Context — passes session state into elicitation-aware tools.

``ToolCallContext`` is created by the dispatcher for every ``tools/call``
invocation and passed into tools that support elicitation or progress
streaming. Tools that don't use these features receive the context too but
may ignore it.

Elicitation flow:
  1. Tool calls ``await ctx.elicit_form(schema_key, message)``.
  2. Context generates a unique request ID and creates an ``asyncio.Future``
     in the session's ``pending`` registry.
  3. Context pushes an ``elicitation/create`` SSE event into the session's
     SSE queues (the POST response is already an open SSE stream at this point).
  4. The client receives the event, shows the form/URL to the user, then
     POSTs the ``elicitation/create`` response back to ``POST /mcp``.
  5. The dispatcher sees the response, calls ``resolve_elicitation()``.
  6. The awaited Future resolves and the tool receives the user's data.

Progress flow:
  Tool calls ``await ctx.progress(token, value, total, label)``.
  This pushes a ``notifications/progress`` SSE event without blocking.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from musehub.contracts.json_types import JSONObject
from musehub.mcp.session import (
    MCPSession,
    cancel_elicitation,
    create_pending_elicitation,
    push_to_session,
)
from musehub.mcp.sse import sse_notification, sse_request

logger = logging.getLogger(__name__)

# Timeout for elicitation responses: 5 minutes. After this the tool receives
# None and should handle gracefully (skip or return partial result).
_ELICITATION_TIMEOUT_SECONDS = 300.0


@dataclass
class ToolCallContext:
    """Runtime context for an MCP ``tools/call`` invocation.

    Carries session state and provides high-level async helpers for
    elicitation and progress reporting. Passed to all tool executors;
    tools that don't use it can accept and ignore it.

    Attributes:
        user_id: Authenticated user from the JWT ``sub`` claim, or ``None``.
        session: Active :class:`~musehub.mcp.session.MCPSession`, or ``None``
            for clients that did not send an ``Mcp-Session-Id`` header. When
            ``None``, elicitation is unavailable and progress events are silent.
        _elicitation_counter: Monotonic counter for unique elicitation IDs.
    """

    user_id: str | None
    session: MCPSession | None
    _elicitation_counter: int = field(default=0, init=False)

    # ── Public API ────────────────────────────────────────────────────────────

    async def elicit_form(
        self,
        schema: JSONObject,
        message: str,
    ) -> dict[str, Any] | None:
        """Request structured data from the user via form-mode elicitation.

        Sends an ``elicitation/create`` request with ``mode: "form"`` to the
        client via the session's SSE stream, then awaits the user's response.

        Args:
            schema: A restricted JSON Schema object (flat, primitive properties
                only) describing the fields to collect. See the elicitation
                module for pre-built musical schemas.
            message: Human-readable explanation shown to the user in the client.

        Returns:
            The ``content`` dict from the accepted elicitation response, or
            ``None`` if the user declined, cancelled, or the session timed out.

        Raises:
            RuntimeError: If no session is attached (no ``Mcp-Session-Id``).
        """
        if self.session is None:
            logger.warning("elicit_form called without an active session — returning None")
            return None

        if not self.session.supports_elicitation_form():
            logger.warning(
                "Client does not support form elicitation (session %.8s...) — returning None",
                self.session.session_id,
            )
            return None

        req_id = self._next_elicitation_id()
        fut = create_pending_elicitation(self.session, req_id)

        params: JSONObject = {
            "mode": "form",
            "message": message,
            "requestedSchema": schema,  # type: ignore[assignment]
        }
        event_text = sse_request(req_id, "elicitation/create", params)
        push_to_session(self.session, event_text)

        try:
            result = await asyncio.wait_for(
                asyncio.shield(fut), timeout=_ELICITATION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            cancel_elicitation(self.session, req_id)
            logger.info(
                "Elicitation timed out for session %.8s...", self.session.session_id
            )
            return None
        except asyncio.CancelledError:
            return None

        action = result.get("action")
        if action != "accept":
            return None
        content = result.get("content")
        return content if isinstance(content, dict) else {}

    async def elicit_url(
        self,
        url: str,
        message: str,
        elicitation_id: str | None = None,
    ) -> bool:
        """Direct the user to an external URL for out-of-band interaction.

        Sends an ``elicitation/create`` request with ``mode: "url"`` to the
        client. Returns ``True`` when the user accepts (clicks through), or
        ``False`` on decline/cancel/timeout.

        Typical use cases: OAuth to connect a DAW cloud account or streaming
        platform, payment flows, API key entry on a trusted branded page.

        Args:
            url: The URL to open. Must be HTTPS in production.
            message: Human-readable reason shown to the user.
            elicitation_id: Stable ID used in ``notifications/elicitation/complete``.
                Auto-generated if not provided.

        Returns:
            ``True`` if the user accepted, ``False`` otherwise.
        """
        if self.session is None:
            logger.warning("elicit_url called without an active session — returning False")
            return False

        if not self.session.supports_elicitation_url():
            logger.warning(
                "Client does not support URL elicitation (session %.8s...) — returning False",
                self.session.session_id,
            )
            return False

        if elicitation_id is None:
            elicitation_id = secrets.token_urlsafe(16)

        req_id = self._next_elicitation_id()
        fut = create_pending_elicitation(self.session, req_id)

        params: JSONObject = {
            "mode": "url",
            "message": message,
            "url": url,
            "elicitationId": elicitation_id,
        }
        event_text = sse_request(req_id, "elicitation/create", params)
        push_to_session(self.session, event_text)

        try:
            result = await asyncio.wait_for(
                asyncio.shield(fut), timeout=_ELICITATION_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            cancel_elicitation(self.session, req_id)
            return False
        except asyncio.CancelledError:
            return False

        return result.get("action") == "accept"

    async def progress(
        self,
        token: str,
        value: int | float,
        total: int | float | None = None,
        label: str | None = None,
    ) -> None:
        """Emit a ``notifications/progress`` event to the client.

        Silent no-op when no session is attached (stateless clients).

        Args:
            token: Progress token identifying this operation (from the original
                ``tools/call`` ``_meta.progressToken`` if provided, else a
                tool-generated string).
            value: Current progress value.
            total: Optional total (enables percentage calculation in clients).
            label: Optional human-readable status message.
        """
        if self.session is None:
            return

        params: JSONObject = {
            "progressToken": token,  # type: ignore[assignment]
            "progress": value,
        }
        if total is not None:
            params["total"] = total  # type: ignore[assignment]
        if label is not None:
            params["message"] = label  # type: ignore[assignment]

        event_text = sse_notification("notifications/progress", params)
        push_to_session(self.session, event_text)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_elicitation_id(self) -> str:
        self._elicitation_counter += 1
        return f"elicit-{self._elicitation_counter}-{secrets.token_hex(4)}"

    @property
    def has_session(self) -> bool:
        """True if a session is attached and SSE-based features are available."""
        return self.session is not None

    @property
    def has_elicitation(self) -> bool:
        """True if the client supports at least form-mode elicitation."""
        return self.session is not None and self.session.supports_elicitation_form()

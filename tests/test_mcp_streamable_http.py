"""Tests for MCP 2025-11-25 Streamable HTTP transport.

Covers:
  POST /mcp:
    - Origin header validation (valid, invalid, absent)
    - initialize: returns Mcp-Session-Id header, correct protocolVersion
    - Non-initialize with Mcp-Session-Id: routes correctly
    - Non-initialize without Mcp-Session-Id: still routes (no strict requirement)
    - Unsupported MCP-Protocol-Version header: 400
    - Elicitation response routing (client sends result back)
    - Batch request handling
    - Notification returns 202
    - JSON parse error returns 400

  GET /mcp:
    - Requires Accept: text/event-stream (405 otherwise)
    - Requires Mcp-Session-Id (400 otherwise)
    - Valid session: opens SSE stream
    - Unknown session: 404

  DELETE /mcp:
    - Requires Mcp-Session-Id (400 otherwise)
    - Valid session: 200
    - Unknown session: 404

  Session store:
    - create_session, get_session, delete_session, TTL, SSE queue, elicitation Futures
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.main import app
from musehub.mcp.session import (
    MCPSession,
    create_session,
    delete_session,
    get_session,
    create_pending_elicitation,
    resolve_elicitation,
    cancel_elicitation,
    push_to_session,
    register_sse_queue,
)


# ── Test fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def http_client(db_session: AsyncSession) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
    ) as client:
        yield client


# ── Helpers ───────────────────────────────────────────────────────────────────


def _init_body() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "clientInfo": {"name": "test-client", "version": "1.0"},
            "capabilities": {"elicitation": {"form": {}, "url": {}}},
        },
    }


# ── Origin validation ─────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_post_mcp_no_origin_allowed(http_client: AsyncClient) -> None:
    """Requests without Origin header (e.g. curl) must be allowed."""
    resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_post_mcp_localhost_origin_allowed(http_client: AsyncClient) -> None:
    """localhost Origin must always be permitted."""
    resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={
            "Content-Type": "application/json",
            "Origin": "http://localhost",
        },
    )
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_post_mcp_invalid_origin_rejected(http_client: AsyncClient) -> None:
    """Requests from non-allow-listed Origins must be rejected with 403."""
    resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={
            "Content-Type": "application/json",
            "Origin": "https://evil-attacker.example.com",
        },
    )
    assert resp.status_code == 403


# ── POST /mcp — initialize ────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_post_mcp_initialize_returns_session_id(http_client: AsyncClient) -> None:
    """POST initialize must return Mcp-Session-Id header and 2025-11-25 version."""
    resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers
    session_id = resp.headers["mcp-session-id"]
    assert len(session_id) > 10

    data = resp.json()
    assert data["result"]["protocolVersion"] == "2025-11-25"
    assert "elicitation" in data["result"]["capabilities"]


@pytest.mark.anyio
async def test_post_mcp_initialize_session_persists(http_client: AsyncClient) -> None:
    """Session created by initialize must be retrievable by get_session."""
    resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    session_id = resp.headers["mcp-session-id"]
    session = get_session(session_id)
    assert session is not None
    assert session.session_id == session_id

    delete_session(session_id)


# ── POST /mcp — protocol version validation ───────────────────────────────────


@pytest.mark.anyio
async def test_post_mcp_unsupported_protocol_version_rejected(
    http_client: AsyncClient,
) -> None:
    """Non-initialize POST with an unsupported MCP-Protocol-Version must return 400."""
    session = create_session(None, {"elicitation": {}})
    try:
        resp = await http_client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session.session_id,
                "MCP-Protocol-Version": "9999-99-99",
            },
        )
        assert resp.status_code == 400
        assert "error" in resp.json()
    finally:
        delete_session(session.session_id)


@pytest.mark.anyio
async def test_post_mcp_missing_session_returns_404(http_client: AsyncClient) -> None:
    """Non-initialize POST with an unknown session ID must return 404."""
    resp = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={
            "Content-Type": "application/json",
            "Mcp-Session-Id": "nonexistent-session-id",
        },
    )
    assert resp.status_code == 404


# ── POST /mcp — misc ──────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_post_mcp_notification_returns_202(http_client: AsyncClient) -> None:
    """JSON-RPC notifications (no id) must return 202 Accepted."""
    resp = await http_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 202


@pytest.mark.anyio
async def test_post_mcp_json_parse_error_returns_400(http_client: AsyncClient) -> None:
    """Malformed JSON body must return 400."""
    resp = await http_client.post(
        "/mcp",
        content=b"{invalid json}",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == -32700


@pytest.mark.anyio
async def test_post_mcp_batch_returns_list(http_client: AsyncClient) -> None:
    """Batch requests must return a list of responses."""
    batch = [
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    ]
    resp = await http_client.post(
        "/mcp",
        json=batch,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2


@pytest.mark.anyio
async def test_post_mcp_elicitation_response_returns_202(http_client: AsyncClient) -> None:
    """A JSON-RPC response (no 'method') from the client must return 202."""
    session = create_session(None, {"elicitation": {"form": {}}})
    try:
        resp = await http_client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": "elicit-1", "result": {"action": "decline"}},
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": session.session_id,
            },
        )
        assert resp.status_code == 202
    finally:
        delete_session(session.session_id)


# ── GET /mcp ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_get_mcp_requires_sse_accept(http_client: AsyncClient) -> None:
    """GET /mcp without Accept: text/event-stream must return 405."""
    session = create_session(None, {})
    try:
        resp = await http_client.get(
            "/mcp",
            headers={"Mcp-Session-Id": session.session_id},
        )
        assert resp.status_code == 405
    finally:
        delete_session(session.session_id)


@pytest.mark.anyio
async def test_get_mcp_requires_session_id(http_client: AsyncClient) -> None:
    """GET /mcp without Mcp-Session-Id must return 400."""
    resp = await http_client.get(
        "/mcp",
        headers={"Accept": "text/event-stream"},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_get_mcp_unknown_session_returns_404(http_client: AsyncClient) -> None:
    """GET /mcp with an unknown session ID must return 404."""
    resp = await http_client.get(
        "/mcp",
        headers={
            "Accept": "text/event-stream",
            "Mcp-Session-Id": "unknown-session-xyz",
        },
    )
    assert resp.status_code == 404


# ── DELETE /mcp ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_delete_mcp_requires_session_id(http_client: AsyncClient) -> None:
    """DELETE /mcp without Mcp-Session-Id must return 400."""
    resp = await http_client.delete("/mcp")
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_delete_mcp_unknown_session_returns_404(http_client: AsyncClient) -> None:
    """DELETE /mcp with an unknown session must return 404."""
    resp = await http_client.delete(
        "/mcp",
        headers={"Mcp-Session-Id": "unknown-session-xyz"},
    )
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_delete_mcp_valid_session_returns_200(http_client: AsyncClient) -> None:
    """DELETE /mcp with a valid session must return 200 and remove the session."""
    # First initialize to get a session.
    init_resp = await http_client.post(
        "/mcp",
        json=_init_body(),
        headers={"Content-Type": "application/json"},
    )
    assert init_resp.status_code == 200
    session_id = init_resp.headers["mcp-session-id"]

    # Delete it.
    del_resp = await http_client.delete(
        "/mcp",
        headers={"Mcp-Session-Id": session_id},
    )
    assert del_resp.status_code == 200

    # Confirm it's gone.
    assert get_session(session_id) is None


# ── Session store unit tests ──────────────────────────────────────────────────


def test_session_create_and_get() -> None:
    """create_session + get_session should round-trip."""
    session = create_session("user-123", {"elicitation": {"form": {}}})
    try:
        fetched = get_session(session.session_id)
        assert fetched is not None
        assert fetched.user_id == "user-123"
        assert fetched.supports_elicitation_form()
    finally:
        delete_session(session.session_id)


def test_session_delete() -> None:
    """delete_session should remove the session from the store."""
    session = create_session(None, {})
    sid = session.session_id
    assert delete_session(sid) is True
    assert get_session(sid) is None


def test_session_double_delete() -> None:
    """Deleting a session twice should return False the second time."""
    session = create_session(None, {})
    sid = session.session_id
    assert delete_session(sid) is True
    assert delete_session(sid) is False


def test_session_elicitation_form_support() -> None:
    """Session should correctly report form elicitation support."""
    session_with = create_session(None, {"elicitation": {"form": {}}})
    session_without = create_session(None, {})
    try:
        assert session_with.supports_elicitation_form() is True
        assert session_without.supports_elicitation_form() is False
    finally:
        delete_session(session_with.session_id)
        delete_session(session_without.session_id)


def test_session_url_elicitation_support() -> None:
    """Session should correctly report URL elicitation support."""
    session_both = create_session(None, {"elicitation": {"form": {}, "url": {}}})
    session_form_only = create_session(None, {"elicitation": {"form": {}}})
    try:
        assert session_both.supports_elicitation_url() is True
        assert session_form_only.supports_elicitation_url() is False
    finally:
        delete_session(session_both.session_id)
        delete_session(session_form_only.session_id)


@pytest.mark.anyio
async def test_elicitation_future_resolve() -> None:
    """create_pending_elicitation + resolve_elicitation should set the Future result."""
    session = create_session(None, {"elicitation": {"form": {}}})
    try:
        fut = create_pending_elicitation(session, "elicit-1")
        result = {"action": "accept", "content": {"key": "C major"}}
        resolved = resolve_elicitation(session, "elicit-1", result)
        assert resolved is True
        assert fut.done()
        assert fut.result() == result
    finally:
        delete_session(session.session_id)


@pytest.mark.anyio
async def test_elicitation_future_cancel() -> None:
    """cancel_elicitation should cancel the Future."""
    session = create_session(None, {"elicitation": {"form": {}}})
    try:
        fut = create_pending_elicitation(session, "elicit-2")
        cancelled = cancel_elicitation(session, "elicit-2")
        assert cancelled is True
        assert fut.cancelled()
    finally:
        delete_session(session.session_id)


@pytest.mark.anyio
async def test_push_to_session_delivers_to_queue() -> None:
    """push_to_session should deliver events to all registered SSE queues."""
    session = create_session(None, {})
    try:
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        session.sse_queues.append(queue)

        push_to_session(session, "data: test\n\n")

        item = queue.get_nowait()
        assert item == "data: test\n\n"
    finally:
        delete_session(session.session_id)

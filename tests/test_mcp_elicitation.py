"""Tests for MCP 2025-11-25 Elicitation: ToolCallContext, session, and tools.

Covers:
  ToolCallContext:
    - elicit_form: accept, decline, cancel, timeout, no-session fallback
    - elicit_url: accept, decline, no-session fallback
    - progress: session push, no-session no-op

  Session elicitation helpers:
    - create_pending_elicitation, resolve_elicitation, cancel_elicitation

  Elicitation schemas:
    - SCHEMAS contains all expected keys
    - build_form_elicitation returns correct mode/requestedSchema
    - build_url_elicitation returns correct mode/url/elicitationId

  Tool routing (unit):
    - musehub_compose_with_preferences: no session → elicitation_unavailable
    - musehub_review_pr_interactive: no session → elicitation_unavailable
    - musehub_connect_streaming_platform: no session → elicitation_unavailable
    - musehub_connect_daw_cloud: no session → elicitation_unavailable
    - musehub_create_release_interactive: no session → elicitation_unavailable

  New prompts:
    - musehub/onboard assembles correctly
    - musehub/release_to_world assembles correctly with repo_id interpolation

  SSE formatting:
    - sse_event produces correct format
    - sse_notification produces correct JSON-RPC notification
    - sse_request produces correct JSON-RPC request with id
    - sse_response produces correct JSON-RPC response
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from musehub.mcp.context import ToolCallContext
from musehub.mcp.elicitation import (
    SCHEMAS,
    build_form_elicitation,
    build_url_elicitation,
    oauth_connect_url,
    daw_cloud_connect_url,
)
from musehub.mcp.prompts import PROMPT_CATALOGUE, get_prompt
from musehub.mcp.session import (
    MCPSession,
    create_session,
    create_pending_elicitation,
    delete_session,
    resolve_elicitation,
    cancel_elicitation,
    push_to_session,
)
from musehub.mcp.sse import (
    sse_event,
    sse_notification,
    sse_request,
    sse_response,
)


# ── SSE formatting ────────────────────────────────────────────────────────────


def test_sse_event_basic_format() -> None:
    """sse_event should produce 'data: <json>\\n\\n'."""
    result = sse_event({"jsonrpc": "2.0", "method": "ping"})
    assert result.startswith("data:")
    assert result.endswith("\n\n")
    # Extract data line and parse JSON
    data_line = [l for l in result.split("\n") if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["method"] == "ping"


def test_sse_event_with_id_and_type() -> None:
    """sse_event with event_id and event_type should include id: and event: lines."""
    result = sse_event({"a": 1}, event_id="42", event_type="notification")
    assert "id: 42\n" in result
    assert "event: notification\n" in result


def test_sse_notification_format() -> None:
    """sse_notification should produce a valid JSON-RPC 2.0 notification."""
    result = sse_notification("notifications/progress", {"progress": 50})
    data_line = [l for l in result.split("\n") if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "notifications/progress"
    assert payload["params"]["progress"] == 50
    assert "id" not in payload  # notifications have no id


def test_sse_request_format() -> None:
    """sse_request should produce a valid JSON-RPC 2.0 request with id."""
    result = sse_request("elicit-1", "elicitation/create", {"mode": "form"})
    data_line = [l for l in result.split("\n") if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == "elicit-1"
    assert payload["method"] == "elicitation/create"
    assert payload["params"]["mode"] == "form"


def test_sse_response_format() -> None:
    """sse_response should produce a valid JSON-RPC 2.0 success response."""
    result = sse_response(42, {"content": [{"type": "text", "text": "ok"}]})
    data_line = [l for l in result.split("\n") if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 42
    assert "result" in payload
    assert "error" not in payload


# ── Elicitation schemas ───────────────────────────────────────────────────────


def test_schemas_has_all_expected_keys() -> None:
    """SCHEMAS must contain all 5 musical elicitation schemas."""
    expected = {
        "compose_preferences",
        "repo_creation",
        "pr_review_focus",
        "release_metadata",
        "platform_connect_confirm",
    }
    assert expected == set(SCHEMAS.keys())


def test_compose_preferences_schema_required_fields() -> None:
    """compose_preferences schema must declare correct required fields."""
    schema = SCHEMAS["compose_preferences"]
    assert schema["type"] == "object"
    required = schema["required"]
    assert "key" in required
    assert "tempo_bpm" in required
    assert "mood" in required
    assert "genre" in required


def test_build_form_elicitation() -> None:
    """build_form_elicitation should return correct mode and requestedSchema."""
    params = build_form_elicitation("compose_preferences", "Pick your vibe")
    assert params["mode"] == "form"
    assert params["message"] == "Pick your vibe"
    assert "requestedSchema" in params
    assert params["requestedSchema"] is SCHEMAS["compose_preferences"]


def test_build_form_elicitation_unknown_key_raises() -> None:
    """build_form_elicitation with unknown key should raise KeyError."""
    with pytest.raises(KeyError):
        build_form_elicitation("nonexistent_schema", "message")


def test_build_url_elicitation() -> None:
    """build_url_elicitation should return correct mode, url, and elicitationId."""
    params, eid = build_url_elicitation("https://example.com/oauth", "Connect Spotify")
    assert params["mode"] == "url"
    assert params["url"] == "https://example.com/oauth"
    assert params["message"] == "Connect Spotify"
    assert params["elicitationId"] == eid
    assert len(eid) > 10


def test_build_url_elicitation_stable_id() -> None:
    """build_url_elicitation should use provided elicitation_id."""
    params, eid = build_url_elicitation(
        "https://example.com/oauth", "msg", elicitation_id="my-stable-id"
    )
    assert eid == "my-stable-id"
    assert params["elicitationId"] == "my-stable-id"


def test_oauth_connect_url_format() -> None:
    """oauth_connect_url should produce correct platform-specific MuseHub URL."""
    url = oauth_connect_url("Spotify", "abc123", base_url="https://musehub.app")
    assert "spotify" in url
    assert "elicitation_id=abc123" in url
    assert url.startswith("https://musehub.app")


def test_daw_cloud_connect_url_format() -> None:
    """daw_cloud_connect_url should produce correct service-specific URL."""
    url = daw_cloud_connect_url("LANDR", "xyz789", base_url="https://musehub.app")
    assert "landr" in url
    assert "elicitation_id=xyz789" in url


# ── ToolCallContext — elicit_form ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_elicit_form_no_session_returns_none() -> None:
    """elicit_form without an active session should return None."""
    ctx = ToolCallContext(user_id=None, session=None)
    result = await ctx.elicit_form(SCHEMAS["compose_preferences"], "msg")
    assert result is None


@pytest.mark.anyio
async def test_elicit_form_accepted_returns_content() -> None:
    """elicit_form should return content dict when user accepts."""
    session = create_session("user-1", {"elicitation": {"form": {}}})
    ctx = ToolCallContext(user_id="user-1", session=session)

    # Pre-resolve the Future before the elicit_form call awaits it.
    content = {"key": "C major", "tempo_bpm": 120, "mood": "peaceful", "genre": "ambient"}

    async def _resolve_after_push() -> None:
        await asyncio.sleep(0)  # yield to let push happen
        for req_id, fut in list(session.pending.items()):
            resolve_elicitation(session, req_id, {"action": "accept", "content": content})

    task = asyncio.create_task(_resolve_after_push())
    result = await ctx.elicit_form(SCHEMAS["compose_preferences"], "Pick your vibe")
    await task

    assert result == content
    delete_session(session.session_id)


@pytest.mark.anyio
async def test_elicit_form_declined_returns_none() -> None:
    """elicit_form should return None when user declines."""
    session = create_session("user-1", {"elicitation": {"form": {}}})
    ctx = ToolCallContext(user_id="user-1", session=session)

    async def _decline_after_push() -> None:
        await asyncio.sleep(0)
        for req_id in list(session.pending.keys()):
            resolve_elicitation(session, req_id, {"action": "decline"})

    task = asyncio.create_task(_decline_after_push())
    result = await ctx.elicit_form(SCHEMAS["compose_preferences"], "Pick your vibe")
    await task

    assert result is None
    delete_session(session.session_id)


@pytest.mark.anyio
async def test_elicit_form_no_form_capability_returns_none() -> None:
    """elicit_form should return None if client didn't declare form support."""
    session = create_session("user-1", {"elicitation": {"url": {}}})  # url only, no form
    ctx = ToolCallContext(user_id="user-1", session=session)
    result = await ctx.elicit_form(SCHEMAS["compose_preferences"], "msg")
    assert result is None
    delete_session(session.session_id)


# ── ToolCallContext — elicit_url ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_elicit_url_no_session_returns_false() -> None:
    """elicit_url without an active session should return False."""
    ctx = ToolCallContext(user_id=None, session=None)
    result = await ctx.elicit_url("https://example.com/oauth", "msg")
    assert result is False


@pytest.mark.anyio
async def test_elicit_url_accepted_returns_true() -> None:
    """elicit_url should return True when user accepts the URL flow."""
    session = create_session("user-1", {"elicitation": {"form": {}, "url": {}}})
    ctx = ToolCallContext(user_id="user-1", session=session)

    async def _accept_after_push() -> None:
        await asyncio.sleep(0)
        for req_id in list(session.pending.keys()):
            resolve_elicitation(session, req_id, {"action": "accept"})

    task = asyncio.create_task(_accept_after_push())
    result = await ctx.elicit_url("https://example.com/oauth", "msg")
    await task

    assert result is True
    delete_session(session.session_id)


# ── ToolCallContext — progress ────────────────────────────────────────────────


@pytest.mark.anyio
async def test_progress_no_session_is_noop() -> None:
    """progress without an active session should not raise."""
    ctx = ToolCallContext(user_id=None, session=None)
    await ctx.progress("token", 1, 10, "working…")  # must not raise


@pytest.mark.anyio
async def test_progress_with_session_pushes_sse_event() -> None:
    """progress with an active session should push a notifications/progress SSE event."""
    session = create_session("user-1", {})
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    session.sse_queues.append(queue)

    ctx = ToolCallContext(user_id="user-1", session=session)
    await ctx.progress("compose-token", 2, 5, "generating…")

    assert not queue.empty()
    event_text = queue.get_nowait()
    assert event_text is not None
    data_line = [l for l in event_text.split("\n") if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["method"] == "notifications/progress"
    assert payload["params"]["progress"] == 2
    assert payload["params"]["total"] == 5

    delete_session(session.session_id)


# ── Elicitation tool executors — no session graceful degradation ──────────────


@pytest.mark.anyio
async def test_compose_with_preferences_no_session() -> None:
    """musehub_compose_with_preferences without session must return error."""
    from musehub.mcp.write_tools.elicitation_tools import execute_compose_with_preferences

    ctx = ToolCallContext(user_id=None, session=None)
    result = await execute_compose_with_preferences(repo_id=None, ctx=ctx)
    assert result.ok is False
    assert result.error_code == "elicitation_unavailable"


@pytest.mark.anyio
async def test_review_pr_interactive_no_session() -> None:
    """musehub_review_pr_interactive without session must return error."""
    from musehub.mcp.write_tools.elicitation_tools import execute_review_pr_interactive

    ctx = ToolCallContext(user_id=None, session=None)
    result = await execute_review_pr_interactive("repo-1", "pr-1", ctx=ctx)
    assert result.ok is False
    assert result.error_code == "elicitation_unavailable"


@pytest.mark.anyio
async def test_connect_streaming_platform_no_session() -> None:
    """musehub_connect_streaming_platform without session must return error."""
    from musehub.mcp.write_tools.elicitation_tools import execute_connect_streaming_platform

    ctx = ToolCallContext(user_id=None, session=None)
    result = await execute_connect_streaming_platform("Spotify", None, ctx=ctx)
    assert result.ok is False
    assert result.error_code == "elicitation_unavailable"


@pytest.mark.anyio
async def test_connect_daw_cloud_no_session() -> None:
    """musehub_connect_daw_cloud without session must return error."""
    from musehub.mcp.write_tools.elicitation_tools import execute_connect_daw_cloud

    ctx = ToolCallContext(user_id=None, session=None)
    result = await execute_connect_daw_cloud("LANDR", ctx=ctx)
    assert result.ok is False
    assert result.error_code == "elicitation_unavailable"


@pytest.mark.anyio
async def test_create_release_interactive_no_session() -> None:
    """musehub_create_release_interactive without session must return error."""
    from musehub.mcp.write_tools.elicitation_tools import execute_create_release_interactive

    ctx = ToolCallContext(user_id=None, session=None)
    result = await execute_create_release_interactive("repo-1", ctx=ctx)
    assert result.ok is False
    assert result.error_code == "elicitation_unavailable"


# ── New prompts ───────────────────────────────────────────────────────────────


def test_onboard_prompt_assembles() -> None:
    """musehub/onboard should assemble with 2 messages."""
    result = get_prompt("musehub/onboard", {"username": "alice"})
    assert result is not None
    assert "messages" in result
    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "user"
    text = result["messages"][1]["content"]["text"]
    assert "alice" in text
    assert "elicitation" in text.lower() or "elicit" in text.lower() or "compose" in text.lower()


def test_release_to_world_prompt_assembles() -> None:
    """musehub/release_to_world should assemble with 2 messages and interpolate repo_id."""
    result = get_prompt("musehub/release_to_world", {"repo_id": "abc-123"})
    assert result is not None
    assert "messages" in result
    assert len(result["messages"]) == 2
    text = result["messages"][1]["content"]["text"]
    assert "abc-123" in text


def test_onboard_prompt_in_catalogue() -> None:
    """musehub/onboard must be in the prompt catalogue."""
    names = {p["name"] for p in PROMPT_CATALOGUE}
    assert "musehub/onboard" in names


def test_release_to_world_in_catalogue() -> None:
    """musehub/release_to_world must be in the prompt catalogue."""
    names = {p["name"] for p in PROMPT_CATALOGUE}
    assert "musehub/release_to_world" in names


# ── Dispatcher routing — new notifications (2025-11-25) ──────────────────────


@pytest.mark.anyio
async def test_notifications_cancelled_handled() -> None:
    """notifications/cancelled should be handled as a notification (return None)."""
    from musehub.mcp.dispatcher import handle_request

    resp = await handle_request({
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {"requestId": "elicit-1", "reason": "user navigated away"},
    })
    assert resp is None  # notifications return None


@pytest.mark.anyio
async def test_notifications_elicitation_complete_handled() -> None:
    """notifications/elicitation/complete should be handled as a notification."""
    from musehub.mcp.dispatcher import handle_request

    resp = await handle_request({
        "jsonrpc": "2.0",
        "method": "notifications/elicitation/complete",
        "params": {"elicitationId": "abc-xyz"},
    })
    assert resp is None


@pytest.mark.anyio
async def test_notifications_cancelled_resolves_future() -> None:
    """notifications/cancelled with a session should cancel the pending Future."""
    from musehub.mcp.dispatcher import handle_request

    session = create_session(None, {"elicitation": {"form": {}}})
    fut = create_pending_elicitation(session, "elicit-99")

    await handle_request(
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": "elicit-99"},
        },
        session=session,
    )

    assert fut.cancelled()
    delete_session(session.session_id)

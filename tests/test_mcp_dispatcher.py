"""Tests for the MuseHub MCP dispatcher, resources, and prompts.

Covers:
  - JSON-RPC 2.0 protocol correctness (initialize, tools/list, resources/list,
    resources/templates/list, prompts/list, prompts/get, ping, unknown method)
  - tools/call routing: known read tools, unknown tool, write tool auth gate
  - resources/read: musehub:// URI dispatch and unknown URI handling
  - prompts/get: known prompt assembly and unknown prompt error
  - Batch request handling
  - Notification handling (no id → returns None)
  - Tool catalogue completeness (43 tools)
  - Resource catalogue completeness (12 static, 17 templated)
  - Prompt catalogue completeness (12 prompts)
  - MCP 2025-11-25: elicitation capability in initialize, new notifications
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from musehub.mcp.dispatcher import handle_batch, handle_request
from musehub.mcp.prompts import PROMPT_CATALOGUE, get_prompt
from musehub.mcp.resources import RESOURCE_TEMPLATES, STATIC_RESOURCES, read_resource
from musehub.mcp.tools import MCP_TOOLS, MUSEHUB_WRITE_TOOL_NAMES


# ── Helpers ───────────────────────────────────────────────────────────────────


def _req(method: str, params: dict | None = None, req_id: int = 1) -> dict:
    """Build a minimal JSON-RPC 2.0 request dict."""
    msg: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def _notification(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 notification (no id)."""
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


# ── Protocol correctness ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_returns_capabilities() -> None:
    """initialize should return protocolVersion 2025-11-25 and capabilities."""
    resp = await handle_request(_req("initialize", {"protocolVersion": "2025-11-25"}))
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    result = resp["result"]
    assert isinstance(result, dict)
    assert result["protocolVersion"] == "2025-11-25"
    assert "capabilities" in result
    assert "tools" in result["capabilities"]
    assert "resources" in result["capabilities"]
    assert "prompts" in result["capabilities"]
    assert "elicitation" in result["capabilities"]
    assert "form" in result["capabilities"]["elicitation"]
    assert "url" in result["capabilities"]["elicitation"]
    # serverInfo must only contain name and version (not capabilities)
    assert "name" in result["serverInfo"]
    assert "version" in result["serverInfo"]
    assert "capabilities" not in result["serverInfo"]


@pytest.mark.asyncio
async def test_ping_returns_empty_result() -> None:
    """ping should return an empty result dict."""
    resp = await handle_request(_req("ping"))
    assert resp is not None
    assert resp["result"] == {}


@pytest.mark.asyncio
async def test_unknown_method_returns_error() -> None:
    """Unknown methods should return a JSON-RPC method-not-found error."""
    resp = await handle_request(_req("musehub/does-not-exist"))
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_completions_complete_returns_empty() -> None:
    """completions/complete stub returns empty values list (MCP 2025-11-25)."""
    resp = await handle_request(_req("completions/complete", {"ref": {}, "argument": {"name": "x", "value": "y"}}))
    assert resp is not None
    assert "result" in resp
    assert resp["result"]["completion"]["values"] == []


@pytest.mark.asyncio
async def test_logging_set_level_returns_empty() -> None:
    """logging/setLevel should return an empty result dict (MCP 2025-11-25)."""
    resp = await handle_request(_req("logging/setLevel", {"level": "info"}))
    assert resp is not None
    assert resp["result"] == {}


@pytest.mark.asyncio
async def test_notification_returns_none() -> None:
    """Notifications (no id) should return None from handle_request."""
    result = await handle_request(_notification("ping"))
    assert result is None


# ── Tool catalogue ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tools_list_returns_43_tools() -> None:
    """tools/list should return all 43 registered tools."""
    resp = await handle_request(_req("tools/list"))
    assert resp is not None
    result = resp["result"]
    assert isinstance(result, dict)
    tools = result["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 43  # 23 read + 15 write + 5 elicitation


@pytest.mark.asyncio
async def test_tools_list_no_server_side_field() -> None:
    """tools/list should strip the internal server_side field."""
    resp = await handle_request(_req("tools/list"))
    assert resp is not None
    for tool in resp["result"]["tools"]:
        assert "server_side" not in tool, f"Tool {tool['name']} exposes server_side"


@pytest.mark.asyncio
async def test_tools_list_all_have_required_fields() -> None:
    """Every tool in tools/list must have name, description, inputSchema, and annotations."""
    resp = await handle_request(_req("tools/list"))
    assert resp is not None
    for tool in resp["result"]["tools"]:
        assert "name" in tool, f"Missing name: {tool}"
        assert "description" in tool, f"Missing description for {tool.get('name')}"
        assert "inputSchema" in tool, f"Missing inputSchema for {tool.get('name')}"
        assert "annotations" in tool, f"Missing MCP 2025-11-25 annotations for {tool.get('name')}"


def test_tool_catalogue_has_43_tools() -> None:
    """The MCP_TOOLS list must contain exactly 43 tools."""
    assert len(MCP_TOOLS) == 43


def test_write_tool_names_all_in_catalogue() -> None:
    """Every write tool name must appear in the full catalogue."""
    all_names = {t["name"] for t in MCP_TOOLS}
    for name in MUSEHUB_WRITE_TOOL_NAMES:
        assert name in all_names, f"Write tool {name!r} not in MCP_TOOLS"


# ── tools/call routing ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tools_call_unknown_tool_returns_iserror() -> None:
    """Calling an unknown tool should return isError=true (not a JSON-RPC error)."""
    resp = await handle_request(
        _req("tools/call", {"name": "nonexistent_tool", "arguments": {}})
    )
    assert resp is not None
    # Envelope is success (has "result", not "error")
    assert "result" in resp
    result = resp["result"]
    assert result.get("isError") is True


@pytest.mark.asyncio
async def test_tools_call_write_tool_requires_auth() -> None:
    """Calling a write tool without a user_id should return isError=true."""
    resp = await handle_request(
        _req("tools/call", {"name": "musehub_create_repo", "arguments": {"name": "test"}}),
        user_id=None,
    )
    assert resp is not None
    assert "result" in resp
    assert resp["result"].get("isError") is True


@pytest.mark.asyncio
async def test_tools_call_write_tool_passes_with_auth() -> None:
    """Calling a write tool with user_id should reach the executor (not auth-gate)."""
    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.data = {"repo_id": "test-123", "name": "Test", "slug": "test",
                        "owner": "alice", "visibility": "public", "clone_url": "musehub://alice/test",
                        "created_at": None}

    with patch(
        "musehub.mcp.write_tools.repos.execute_create_repo",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await handle_request(
            _req("tools/call", {"name": "musehub_create_repo", "arguments": {"name": "Test"}}),
            user_id="alice",
        )
    assert resp is not None
    assert "result" in resp
    assert resp["result"].get("isError") is False


@pytest.mark.asyncio
async def test_tools_call_read_tool_with_mock_executor() -> None:
    """Read tools should delegate to the executor and return text content."""
    mock_result = MagicMock()
    mock_result.ok = True
    mock_result.data = {"repo_id": "r123", "branches": [], "recent_commits": [], "total_commits": 0, "branch_count": 0}

    with patch(
        "musehub.services.musehub_mcp_executor.execute_browse_repo",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        resp = await handle_request(
            _req("tools/call", {"name": "musehub_browse_repo", "arguments": {"repo_id": "r123"}})
        )

    assert resp is not None
    assert "result" in resp
    result = resp["result"]
    assert result.get("isError") is False
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) == 1
    assert content[0]["type"] == "text"
    # Text should be valid JSON
    data = json.loads(content[0]["text"])
    assert data["repo_id"] == "r123"


# ── Resource catalogue ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resources_list_returns_12_static() -> None:
    """resources/list should return all 12 static resources (musehub:// + muse:// docs/domains)."""
    resp = await handle_request(_req("resources/list"))
    assert resp is not None
    resources = resp["result"]["resources"]
    assert len(resources) == 12


@pytest.mark.asyncio
async def test_resources_templates_list_returns_17_templates() -> None:
    """resources/templates/list should return the 17 URI templates."""
    resp = await handle_request(_req("resources/templates/list"))
    assert resp is not None
    templates = resp["result"]["resourceTemplates"]
    assert len(templates) == 17


def test_static_resources_have_required_fields() -> None:
    """Each static resource must have uri, name, and mimeType."""
    _VALID_PREFIXES = ("musehub://", "muse://")
    for r in STATIC_RESOURCES:
        assert "uri" in r
        assert "name" in r
        assert r["uri"].startswith(_VALID_PREFIXES), f"Unexpected URI scheme: {r['uri']}"


def test_resource_templates_have_required_fields() -> None:
    """Each resource template must have uriTemplate, name, and mimeType."""
    _VALID_PREFIXES = ("musehub://", "muse://")
    for t in RESOURCE_TEMPLATES:
        assert "uriTemplate" in t
        assert "name" in t
        assert t["uriTemplate"].startswith(_VALID_PREFIXES), f"Unexpected URI scheme: {t['uriTemplate']}"


@pytest.mark.asyncio
async def test_resources_read_unknown_uri_returns_error_content() -> None:
    """resources/read with an unknown URI should return an error in the text content."""
    resp = await handle_request(
        _req("resources/read", {"uri": "musehub://nonexistent/path/that/does/not/exist"})
    )
    assert resp is not None
    assert "result" in resp
    contents = resp["result"]["contents"]
    assert isinstance(contents, list)
    assert len(contents) == 1
    data = json.loads(contents[0]["text"])
    assert "error" in data


@pytest.mark.asyncio
async def test_resources_read_missing_uri_returns_error() -> None:
    """resources/read without a uri parameter should return an InvalidParams error."""
    resp = await handle_request(_req("resources/read", {}))
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_resources_read_unsupported_scheme() -> None:
    """resources/read with a non-musehub:// URI should return an error in content."""
    result = await read_resource("https://example.com/foo")
    assert "error" in result


@pytest.mark.asyncio
async def test_resources_read_me_requires_auth() -> None:
    """musehub://me should return an error when user_id is None."""
    from musehub.mcp.resources import _read_me
    result = await _read_me(None)
    assert "error" in result


# ── Prompt catalogue ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompts_list_returns_12_prompts() -> None:
    """prompts/list should return all 12 workflow prompts."""
    resp = await handle_request(_req("prompts/list"))
    assert resp is not None
    prompts = resp["result"]["prompts"]
    assert len(prompts) == 12


def test_prompt_catalogue_completeness() -> None:
    """PROMPT_CATALOGUE must have exactly 12 entries."""
    assert len(PROMPT_CATALOGUE) == 12


def test_prompt_names_are_correct() -> None:
    """All 12 expected prompt names must be present."""
    names = {p["name"] for p in PROMPT_CATALOGUE}
    assert "musehub/orientation" in names
    assert "musehub/contribute" in names
    assert "musehub/create" in names
    assert "musehub/review_pr" in names
    assert "musehub/issue_triage" in names
    assert "musehub/release_prep" in names
    assert "musehub/onboard" in names
    assert "musehub/release_to_world" in names
    assert "musehub/domain-discovery" in names
    assert "musehub/domain-authoring" in names
    assert "musehub/agent-onboard" in names
    assert "musehub/push-workflow" in names


@pytest.mark.asyncio
async def test_prompts_get_orientation_returns_messages() -> None:
    """prompts/get for musehub/orientation should return messages."""
    resp = await handle_request(
        _req("prompts/get", {"name": "musehub/orientation", "arguments": {}})
    )
    assert resp is not None
    assert "result" in resp
    result = resp["result"]
    assert "messages" in result
    messages = result["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_prompts_get_contribute_interpolates_args() -> None:
    """prompts/get for musehub/contribute should accept repo_id, owner, slug args."""
    resp = await handle_request(
        _req("prompts/get", {
            "name": "musehub/contribute",
            "arguments": {"repo_id": "abc-123", "owner": "alice", "slug": "jazz-session"},
        })
    )
    assert resp is not None
    assert "result" in resp
    text = resp["result"]["messages"][1]["content"]["text"]
    assert "jazz-session" in text


@pytest.mark.asyncio
async def test_prompts_get_unknown_returns_method_not_found() -> None:
    """prompts/get for an unknown name should return a -32601 JSON-RPC error."""
    resp = await handle_request(
        _req("prompts/get", {"name": "musehub/nonexistent"})
    )
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_get_prompt_all_prompts_assemble() -> None:
    """All 8 prompts should assemble without raising exceptions."""
    for prompt_def in PROMPT_CATALOGUE:
        name = prompt_def["name"]
        result = get_prompt(name, {"repo_id": "test-id", "pr_id": "pr-id", "owner": "user", "slug": "repo"})
        assert result is not None, f"get_prompt({name!r}) returned None"
        assert "messages" in result
        assert len(result["messages"]) >= 2


def test_get_prompt_unknown_returns_none() -> None:
    """get_prompt for an unknown name should return None."""
    result = get_prompt("musehub/unknown")
    assert result is None


# ── Batch handling ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_handles_multiple_requests() -> None:
    """handle_batch should return responses for all non-notifications."""
    batch = [
        _req("initialize", {"protocolVersion": "2025-03-26"}, req_id=1),
        _req("tools/list", req_id=2),
        _req("prompts/list", req_id=3),
    ]
    responses = await handle_batch(batch)
    assert len(responses) == 3
    ids = {r["id"] for r in responses}
    assert ids == {1, 2, 3}


@pytest.mark.asyncio
async def test_batch_excludes_notifications() -> None:
    """handle_batch should not include responses for notifications."""
    batch = [
        _req("ping", req_id=1),
        _notification("ping"),  # no id → no response
    ]
    responses = await handle_batch(batch)
    assert len(responses) == 1
    assert responses[0]["id"] == 1

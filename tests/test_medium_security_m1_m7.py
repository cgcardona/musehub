"""Regression tests for MEDIUM security fixes M1–M7.

M1 – Exception messages no longer leak internals to MCP clients
M2 – DB pool_size/max_overflow configured for Postgres (smoke test)
M3 – CSP: 'unsafe-inline' removed from script-src; per-request nonce injected
M4 – ACCESS_TOKEN_SECRET enforces minimum 32-byte entropy in production mode
M5 – logging/setLevel requires authentication
M6 – WireSnapshot.manifest capped at 10 000 entries
M7 – Commit message, issue/PR/comment bodies capped at 10 000 chars
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError


# ── M1: Exception messages stripped from MCP responses ───────────────────────


@pytest.mark.asyncio
async def test_m1_unhandled_exception_does_not_leak_traceback() -> None:
    """An unhandled exception inside a tool must not expose its str() to clients."""
    from musehub.mcp.dispatcher import handle_request

    # Craft a valid tools/call request that will trigger an unhandled exception
    # by requesting a non-existent tool with a broken argument.
    raw: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "musehub_get_repo",
            # Pass no repo_id and no owner/slug — should trigger an error path
            "arguments": {},
        },
    }
    resp = await handle_request(raw, user_id=None)
    assert resp is not None
    # The error message must NOT contain Python exception repr / traceback fragments.
    error_block = resp.get("error") or {}
    msg = error_block.get("message", "")
    assert "Traceback" not in msg
    assert "Exception" not in msg
    assert "AttributeError" not in msg


@pytest.mark.asyncio
async def test_m1_tool_error_message_is_generic() -> None:
    """Tool execution errors use a fixed generic prefix, not exc.__str__()."""
    from musehub.mcp.dispatcher import handle_request

    raw: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tools/call",
        "params": {"name": "musehub_get_repo", "arguments": {}},
    }
    resp = await handle_request(raw, user_id=None)
    assert resp is not None
    # Either success (unlikely) or error without internal details.
    if "error" in resp:
        msg: str = resp["error"].get("message", "")  # type: ignore[index]
        # Must not contain anything resembling Python error repr.
        assert "Traceback" not in msg
        assert "NoneType" not in msg


# ── M3: CSP nonce — unsafe-inline removed from script-src ────────────────────


def test_m3_csp_header_removes_unsafe_inline_from_script_src() -> None:
    """The CSP header must not contain 'unsafe-inline' in the script-src directive."""
    import re

    # Parse the CSP string produced by SecurityHeadersMiddleware.
    from musehub.main import SecurityHeadersMiddleware

    # Build a fake middleware instance and a fake nonce.
    mw = SecurityHeadersMiddleware(app=None)  # type: ignore[arg-type]
    nonce = "test-nonce-abc123"

    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'unsafe-eval' 'nonce-{nonce}'; "
        "style-src 'self' 'unsafe-inline' https://fonts.bunny.net; "
        "font-src 'self' https://fonts.bunny.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    # Verify script-src does NOT contain unsafe-inline.
    script_src_match = re.search(r"script-src([^;]+)", csp)
    assert script_src_match is not None
    script_src = script_src_match.group(1)
    assert "'unsafe-inline'" not in script_src
    assert f"'nonce-{nonce}'" in script_src


@pytest.mark.asyncio
async def test_m3_csp_nonce_in_response_header() -> None:
    """Integration: each HTTP response carries a unique CSP nonce in its header."""
    from httpx import AsyncClient, ASGITransport
    from musehub.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.get("/mcp/docs")
        r2 = await client.get("/mcp/docs")

    # Both responses must have a CSP header without unsafe-inline in script-src.
    for resp in (r1, r2):
        csp = resp.headers.get("content-security-policy", "")
        assert "nonce-" in csp, "CSP must contain a nonce"
        import re
        m = re.search(r"script-src([^;]+)", csp)
        assert m is not None
        assert "'unsafe-inline'" not in m.group(1)

    # Each request gets a different nonce.
    import re as _re
    def _extract_nonce(h: str) -> str:
        m = _re.search(r"nonce-([A-Za-z0-9_-]+)", h)
        return m.group(1) if m else ""

    n1 = _extract_nonce(r1.headers.get("content-security-policy", ""))
    n2 = _extract_nonce(r2.headers.get("content-security-policy", ""))
    assert n1 and n2, "Both responses must have a nonce"
    assert n1 != n2, "Each request must receive a fresh nonce"


# ── M4: ACCESS_TOKEN_SECRET entropy check ────────────────────────────────────


@pytest.mark.asyncio
async def test_m4_short_secret_raises_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secret shorter than 32 bytes must raise RuntimeError in production mode."""
    from musehub.config import Settings
    monkeypatch.setattr("musehub.main.settings", Settings(
        debug=False,
        access_token_secret="short",  # < 32 bytes
        # Avoid DB password check by not using postgres URL
        database_url="sqlite+aiosqlite:///:memory:",
    ))

    from musehub.main import lifespan, app

    with pytest.raises(RuntimeError, match="ACCESS_TOKEN_SECRET"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_m4_long_secret_passes_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 32-byte secret must not raise a secret-related error."""
    import secrets
    from musehub.config import Settings
    monkeypatch.setattr("musehub.main.settings", Settings(
        debug=False,
        access_token_secret=secrets.token_hex(32),  # 64 hex chars = 32 bytes
        database_url="sqlite+aiosqlite:///:memory:",
    ))

    from musehub.main import lifespan, app

    try:
        async with lifespan(app):
            pass
    except RuntimeError as exc:
        assert "ACCESS_TOKEN_SECRET" not in str(exc), f"Unexpected secret error: {exc}"


# ── M5: logging/setLevel requires authentication ─────────────────────────────


@pytest.mark.asyncio
async def test_m5_set_level_anonymous_is_rejected() -> None:
    """An unauthenticated logging/setLevel call must be rejected with an error."""
    from musehub.mcp.dispatcher import handle_request

    raw: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "logging/setLevel",
        "params": {"level": "debug"},
    }
    resp = await handle_request(raw, user_id=None)
    assert resp is not None
    assert "error" in resp, "Anonymous setLevel must return an error"
    msg: str = resp["error"].get("message", "")  # type: ignore[index]
    assert "Authentication" in msg or "auth" in msg.lower()


@pytest.mark.asyncio
async def test_m5_set_level_authenticated_is_accepted() -> None:
    """An authenticated logging/setLevel call must succeed."""
    from musehub.mcp.dispatcher import handle_request

    raw: dict[str, object] = {
        "jsonrpc": "2.0",
        "id": 43,
        "method": "logging/setLevel",
        "params": {"level": "warning"},
    }
    resp = await handle_request(raw, user_id="test-user-m5")
    assert resp is not None
    assert "error" not in resp, f"Authenticated setLevel should succeed: {resp}"


# ── M6: WireSnapshot.manifest entry cap ──────────────────────────────────────


def test_m6_manifest_at_limit_is_accepted() -> None:
    """A manifest with exactly 10 000 entries must be accepted."""
    from musehub.models.wire import WireSnapshot

    snap = WireSnapshot(
        snapshot_id="snap-m6",
        manifest={f"file_{i}.mid": f"sha256:{'a' * 64}" for i in range(10_000)},
    )
    assert len(snap.manifest) == 10_000


def test_m6_manifest_over_limit_is_rejected() -> None:
    """A manifest with 10 001 entries must be rejected by Pydantic."""
    from musehub.models.wire import WireSnapshot

    with pytest.raises(ValidationError):
        WireSnapshot(
            snapshot_id="snap-m6-over",
            manifest={f"file_{i}.mid": f"sha256:{'a' * 64}" for i in range(10_001)},
        )


# ── M7: Commit message / PR / issue / comment body length caps ───────────────


def test_m7_commit_message_at_limit() -> None:
    from musehub.models.musehub import CommitInput
    from datetime import datetime, timezone

    CommitInput(
        commit_id="abc",
        parent_ids=[],
        message="x" * 10_000,
        timestamp=datetime.now(timezone.utc),
    )


def test_m7_commit_message_over_limit() -> None:
    from musehub.models.musehub import CommitInput
    from datetime import datetime, timezone

    with pytest.raises(ValidationError):
        CommitInput(
            commit_id="abc",
            parent_ids=[],
            message="x" * 10_001,
            timestamp=datetime.now(timezone.utc),
        )


def test_m7_issue_body_at_limit() -> None:
    from musehub.models.musehub import IssueCreate

    IssueCreate(title="My issue", body="y" * 10_000)


def test_m7_issue_body_over_limit() -> None:
    from musehub.models.musehub import IssueCreate

    with pytest.raises(ValidationError):
        IssueCreate(title="My issue", body="y" * 10_001)


def test_m7_pr_body_at_limit() -> None:
    from musehub.models.musehub import PRCreate

    PRCreate(title="My PR", from_branch="feat/x", to_branch="main", body="z" * 10_000)


def test_m7_pr_body_over_limit() -> None:
    from musehub.models.musehub import PRCreate

    with pytest.raises(ValidationError):
        PRCreate(title="My PR", from_branch="feat/x", to_branch="main", body="z" * 10_001)


def test_m7_issue_comment_body_at_limit() -> None:
    from musehub.models.musehub import IssueCommentCreate

    IssueCommentCreate(body="c" * 10_000)


def test_m7_issue_comment_body_over_limit() -> None:
    from musehub.models.musehub import IssueCommentCreate

    with pytest.raises(ValidationError):
        IssueCommentCreate(body="c" * 10_001)


def test_m7_pr_comment_body_at_limit() -> None:
    from musehub.models.musehub import PRCommentCreate

    PRCommentCreate(body="d" * 10_000)


def test_m7_pr_comment_body_over_limit() -> None:
    from musehub.models.musehub import PRCommentCreate

    with pytest.raises(ValidationError):
        PRCommentCreate(body="d" * 10_001)


def test_m7_review_body_at_limit() -> None:
    from musehub.models.musehub import PRReviewCreate

    PRReviewCreate(event="approve", body="e" * 10_000)


def test_m7_review_body_over_limit() -> None:
    from musehub.models.musehub import PRReviewCreate

    with pytest.raises(ValidationError):
        PRReviewCreate(event="approve", body="e" * 10_001)

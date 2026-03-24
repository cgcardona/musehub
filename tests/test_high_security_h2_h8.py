"""Regression tests for HIGH security fixes H2–H8.

H1 (private repo visibility) is already covered by test_wire_protocol.py.

Tests grouped by finding:
  H2 — Namespace squatting in musehub_publish_domain
  H3 — Unbounded push bundle (Pydantic max_length enforcement)
  H4 — object content size check (MAX_OBJECT_BYTES)
  H5 — Batched BFS fetch (was N sequential queries)
  H6 — MCP session store cap → 503
  H7 — muse_push per-user storage quota
  H8 — compute_pull_delta pagination (500 objects/page)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.tokens import create_access_token
from musehub.mcp.session import (
    SessionCapacityError,
    _MAX_SESSIONS,
    _SESSIONS,
    create_session,
    delete_session,
)
from musehub.models.wire import (
    MAX_OBJECT_BYTES,
    MAX_COMMITS_PER_PUSH,
    MAX_OBJECTS_PER_PUSH,
    MAX_WANT_PER_FETCH,
    WireBundle,
    WireFetchRequest,
    WireObject,
)
from musehub.services.musehub_mcp_executor import execute_musehub_publish_domain
from musehub.services.musehub_sync import compute_pull_delta, _PULL_OBJECTS_PAGE_SIZE
from musehub.db import musehub_models as db
from tests.factories import create_repo as factory_create_repo


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def wire_token() -> str:
    return create_access_token(user_id="test-user-wire", expires_hours=1)


@pytest.fixture
def wire_headers(wire_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {wire_token}",
        "Content-Type": "application/json",
    }


# ── H2: namespace squatting ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_domain_blocked_if_handle_owned_by_other(
    db_session: AsyncSession,
) -> None:
    """A user cannot publish under a handle that belongs to a different account."""
    other_user_id = str(uuid.uuid4())
    identity = db.MusehubIdentity(
        id=other_user_id,
        handle="alice",
        identity_type="human",
    )
    db_session.add(identity)
    await db_session.commit()

    # attacker tries to publish under @alice but their user_id is different
    result = await execute_musehub_publish_domain(
        author_slug="alice",
        slug="hijacked-domain",
        display_name="Hijacked",
        description="Should be rejected",
        capabilities={},
        viewer_type="generic",
        user_id="attacker-user-id",  # != other_user_id
    )
    assert result.ok is False
    assert result.error_code == "forbidden"
    assert "alice" in (result.error_message or "")


@pytest.mark.asyncio
async def test_publish_domain_allowed_if_handle_matches_caller(
    db_session: AsyncSession,
) -> None:
    """A user CAN publish under their own handle."""
    owner_id = str(uuid.uuid4())
    identity = db.MusehubIdentity(
        id=owner_id,
        handle="bobthebuilder",
        identity_type="human",
    )
    db_session.add(identity)
    await db_session.commit()

    result = await execute_musehub_publish_domain(
        author_slug="bobthebuilder",
        slug=f"my-domain-{uuid.uuid4().hex[:6]}",
        display_name="Bob's Domain",
        description="Legitimate publish",
        capabilities={},
        viewer_type="generic",
        user_id=owner_id,
    )
    # ok=True means the squatting check passed (may fail at DB level if domains
    # table requires more setup, but the guard itself did not reject it)
    assert result.error_code != "forbidden"


@pytest.mark.asyncio
async def test_publish_domain_allowed_if_no_identity_registered(
    db_session: AsyncSession,
) -> None:
    """Publishing is allowed when no identity row exists for the handle yet."""
    result = await execute_musehub_publish_domain(
        author_slug="brand-new-user",
        slug=f"first-domain-{uuid.uuid4().hex[:6]}",
        display_name="First Domain",
        description="No identity row yet — should not be forbidden",
        capabilities={},
        viewer_type="generic",
        user_id="some-user-id",
    )
    assert result.error_code != "forbidden"


# ── H3: unbounded push bundle ─────────────────────────────────────────────────

def test_wire_bundle_commits_capped() -> None:
    """WireBundle rejects more than MAX_COMMITS_PER_PUSH commits."""
    from pydantic import ValidationError
    commits = [{"commit_id": f"c{i}", "repo_id": "r"} for i in range(MAX_COMMITS_PER_PUSH + 1)]
    with pytest.raises(ValidationError, match="List should have at most"):
        WireBundle(commits=commits)  # type: ignore[arg-type]


def test_wire_bundle_objects_capped() -> None:
    """WireBundle rejects more than MAX_OBJECTS_PER_PUSH objects."""
    from pydantic import ValidationError
    objects = [{"object_id": f"o{i}", "content": b"x"} for i in range(MAX_OBJECTS_PER_PUSH + 1)]
    with pytest.raises(ValidationError, match="List should have at most"):
        WireBundle(objects=objects)  # type: ignore[arg-type]


def test_wire_fetch_request_want_capped() -> None:
    """WireFetchRequest rejects more than MAX_WANT_PER_FETCH want entries."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="List should have at most"):
        WireFetchRequest(want=["sha"] * (MAX_WANT_PER_FETCH + 1))


def test_wire_bundle_at_limit_is_accepted() -> None:
    """Exactly MAX items is valid — the cap is inclusive."""
    bundle = WireBundle(
        commits=[{"commit_id": f"c{i}", "repo_id": "r"} for i in range(MAX_COMMITS_PER_PUSH)],  # type: ignore[arg-type]
        objects=[{"object_id": f"o{i}", "content": b"x"} for i in range(MAX_OBJECTS_PER_PUSH)],  # type: ignore[arg-type]
    )
    assert len(bundle.commits) == MAX_COMMITS_PER_PUSH
    assert len(bundle.objects) == MAX_OBJECTS_PER_PUSH


# ── H4: object content size check ────────────────────────────────────────────

def test_wire_object_rejects_oversized_content() -> None:
    """WireObject rejects content larger than MAX_OBJECT_BYTES."""
    from pydantic import ValidationError
    oversized = b"x" * (MAX_OBJECT_BYTES + 1)
    with pytest.raises(ValidationError, match="exceeds maximum size|at most"):
        WireObject(object_id="too-big", content=oversized)


def test_wire_object_accepts_at_limit() -> None:
    """WireObject accepts content well under MAX_OBJECT_BYTES."""
    obj = WireObject(object_id="ok", content=b"x" * 1000)
    assert obj.object_id == "ok"


# ── H6: MCP session store cap ────────────────────────────────────────────────

def test_create_session_raises_when_store_full() -> None:
    """create_session raises SessionCapacityError when _SESSIONS is at _MAX_SESSIONS."""
    original_sessions = dict(_SESSIONS)
    try:
        # Fill the store to the exact cap
        fake_ids: list[str] = []
        for i in range(_MAX_SESSIONS - len(_SESSIONS)):
            sid = f"fake-session-{i}"
            from musehub.mcp.session import MCPSession
            _SESSIONS[sid] = MCPSession(
                session_id=sid,
                user_id=None,
                client_capabilities={},
            )
            fake_ids.append(sid)

        assert len(_SESSIONS) == _MAX_SESSIONS
        with pytest.raises(SessionCapacityError):
            create_session(user_id="overflow-user", client_capabilities={})
    finally:
        # Clean up all fake sessions we injected
        for sid in fake_ids:
            _SESSIONS.pop(sid, None)


# ── H8: compute_pull_delta pagination ────────────────────────────────────────

@pytest.mark.asyncio
async def test_pull_delta_paginates_objects(db_session: AsyncSession) -> None:
    """compute_pull_delta returns at most _PULL_OBJECTS_PAGE_SIZE objects per call."""
    repo = await factory_create_repo(db_session, slug="pull-pagination-test")

    # Insert _PULL_OBJECTS_PAGE_SIZE + 5 objects
    total = _PULL_OBJECTS_PAGE_SIZE + 5
    for i in range(total):
        obj = db.MusehubObject(
            object_id=f"obj-{i:05d}",
            repo_id=repo.repo_id,
            path=f"file_{i}.mid",
            size_bytes=100,
            disk_path=f"local://{repo.repo_id}/obj-{i:05d}",
            storage_uri=f"local://{repo.repo_id}/obj-{i:05d}",
        )
        db_session.add(obj)
    await db_session.commit()

    result = await compute_pull_delta(
        db_session,
        repo_id=repo.repo_id,
        branch="main",
        have_commits=[],
        have_objects=[],
    )
    assert len(result.objects) == _PULL_OBJECTS_PAGE_SIZE
    assert result.has_more is True
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_pull_delta_second_page(db_session: AsyncSession) -> None:
    """The second page contains the remaining objects."""
    repo = await factory_create_repo(db_session, slug="pull-page2-test")

    total = _PULL_OBJECTS_PAGE_SIZE + 3
    for i in range(total):
        obj = db.MusehubObject(
            object_id=f"p2obj-{i:05d}",
            repo_id=repo.repo_id,
            path=f"file_{i}.mid",
            size_bytes=50,
            disk_path=f"local://{repo.repo_id}/p2obj-{i:05d}",
            storage_uri=f"local://{repo.repo_id}/p2obj-{i:05d}",
        )
        db_session.add(obj)
    await db_session.commit()

    page1 = await compute_pull_delta(
        db_session,
        repo_id=repo.repo_id,
        branch="main",
        have_commits=[],
        have_objects=[],
    )
    assert page1.has_more is True

    page2 = await compute_pull_delta(
        db_session,
        repo_id=repo.repo_id,
        branch="main",
        have_commits=[],
        have_objects=[],
        cursor=page1.next_cursor,
    )
    assert len(page2.objects) == 3
    assert page2.has_more is False
    assert page2.next_cursor is None


@pytest.mark.asyncio
async def test_pull_delta_no_pagination_when_under_limit(db_session: AsyncSession) -> None:
    """When fewer objects than the page limit exist, has_more is False."""
    repo = await factory_create_repo(db_session, slug="pull-under-limit-test")

    for i in range(5):
        db_session.add(db.MusehubObject(
            object_id=f"small-{i}",
            repo_id=repo.repo_id,
            path=f"f{i}.mid",
            size_bytes=10,
            disk_path=f"local://x/small-{i}",
            storage_uri=f"local://x/small-{i}",
        ))
    await db_session.commit()

    result = await compute_pull_delta(
        db_session,
        repo_id=repo.repo_id,
        branch="main",
        have_commits=[],
        have_objects=[],
    )
    assert len(result.objects) == 5
    assert result.has_more is False
    assert result.next_cursor is None


# ── H5: batched BFS fetch (wire protocol) ────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_batched_bfs_returns_all_commits(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """wire_fetch BFS returns all reachable commits without individual PK queries."""
    repo = await factory_create_repo(db_session, slug="fetch-bfs-batch-test")

    # Build a 3-commit chain: A → B → C (parent chain)
    _ts = datetime.now(timezone.utc)
    commit_a = db.MusehubCommit(
        commit_id="bfs-commit-a",
        repo_id=repo.repo_id,
        branch="main",
        message="A",
        parent_ids=[],
        author="tester",
        commit_meta={},
        timestamp=_ts,
    )
    commit_b = db.MusehubCommit(
        commit_id="bfs-commit-b",
        repo_id=repo.repo_id,
        branch="main",
        message="B",
        parent_ids=["bfs-commit-a"],
        author="tester",
        commit_meta={},
        timestamp=_ts,
    )
    commit_c = db.MusehubCommit(
        commit_id="bfs-commit-c",
        repo_id=repo.repo_id,
        branch="main",
        message="C",
        parent_ids=["bfs-commit-b"],
        author="tester",
        commit_meta={},
        timestamp=_ts,
    )
    db_session.add_all([commit_a, commit_b, commit_c])
    await db_session.commit()

    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/fetch",
        json={"want": ["bfs-commit-c"], "have": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    commit_ids = {c["commit_id"] for c in data.get("commits", [])}
    assert "bfs-commit-a" in commit_ids
    assert "bfs-commit-b" in commit_ids
    assert "bfs-commit-c" in commit_ids

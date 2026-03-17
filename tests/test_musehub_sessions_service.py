"""Unit tests for musehub/services/musehub_sessions.py.

Tests the service layer directly (no HTTP) to validate session creation,
listing, retrieval, and ordering semantics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.models.musehub import SessionCreate
from musehub.services import musehub_sessions
from tests.factories import create_repo


def _session_create(**kwargs: object) -> SessionCreate:
    defaults = dict(
        participants=["alice"],
        intent="Recording session",
        location="Studio A",
    )
    defaults.update(kwargs)
    return SessionCreate(**defaults)


@pytest.mark.anyio
async def test_upsert_session_creates_record(db_session: AsyncSession) -> None:
    """upsert_session returns a SessionResponse with the expected fields."""
    repo = await create_repo(db_session, visibility="public")
    data = _session_create(participants=["bob", "alice"])

    result = await musehub_sessions.upsert_session(db_session, str(repo.repo_id), data)

    assert result.session_id is not None
    assert set(result.participants) == {"bob", "alice"}
    assert result.intent == "Recording session"
    assert result.location == "Studio A"
    assert result.is_active is True


@pytest.mark.anyio
async def test_upsert_session_uses_provided_started_at(db_session: AsyncSession) -> None:
    """started_at from the request is preserved in the session record."""
    repo = await create_repo(db_session)
    t = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    data = _session_create(started_at=t)

    result = await musehub_sessions.upsert_session(db_session, str(repo.repo_id), data)
    await db_session.commit()

    assert result.started_at is not None


@pytest.mark.anyio
async def test_list_sessions_empty_for_new_repo(db_session: AsyncSession) -> None:
    """A new repo with no sessions returns an empty list and total=0."""
    repo = await create_repo(db_session)
    sessions, total = await musehub_sessions.list_sessions(db_session, str(repo.repo_id))
    assert sessions == []
    assert total == 0


@pytest.mark.anyio
async def test_list_sessions_returns_all_sessions(db_session: AsyncSession) -> None:
    """list_sessions returns all sessions belonging to a repo."""
    repo = await create_repo(db_session)
    rid = str(repo.repo_id)

    for i in range(3):
        await musehub_sessions.upsert_session(
            db_session, rid, _session_create(intent=f"Session {i}")
        )
    await db_session.commit()

    sessions, total = await musehub_sessions.list_sessions(db_session, rid)
    assert total == 3
    assert len(sessions) == 3


@pytest.mark.anyio
async def test_list_sessions_ordered_newest_first(db_session: AsyncSession) -> None:
    """list_sessions returns sessions sorted by started_at descending."""
    repo = await create_repo(db_session)
    rid = str(repo.repo_id)
    now = datetime.now(tz=timezone.utc)

    for i in range(3):
        t = now - timedelta(hours=i)
        await musehub_sessions.upsert_session(
            db_session, rid, _session_create(started_at=t, intent=f"Session {i}")
        )
    await db_session.commit()

    sessions, _ = await musehub_sessions.list_sessions(db_session, rid)
    timestamps = [s.started_at for s in sessions]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.anyio
async def test_list_sessions_isolates_by_repo(db_session: AsyncSession) -> None:
    """Sessions from one repo do not appear when listing another repo's sessions."""
    repo_a = await create_repo(db_session, slug="repo-a-sess")
    repo_b = await create_repo(db_session, slug="repo-b-sess")

    await musehub_sessions.upsert_session(
        db_session, str(repo_a.repo_id), _session_create()
    )
    await db_session.commit()

    sessions, total = await musehub_sessions.list_sessions(db_session, str(repo_b.repo_id))
    assert total == 0
    assert sessions == []


@pytest.mark.anyio
async def test_get_session_by_id(db_session: AsyncSession) -> None:
    """get_session returns the correct session given its ID."""
    repo = await create_repo(db_session)
    rid = str(repo.repo_id)

    created = await musehub_sessions.upsert_session(
        db_session, rid, _session_create(intent="Find me")
    )
    await db_session.commit()

    found = await musehub_sessions.get_session(db_session, rid, created.session_id)
    assert found is not None
    assert found.session_id == created.session_id
    assert found.intent == "Find me"


@pytest.mark.anyio
async def test_get_session_nonexistent_returns_none(db_session: AsyncSession) -> None:
    """get_session returns None for an unknown session ID."""
    repo = await create_repo(db_session)
    result = await musehub_sessions.get_session(
        db_session, str(repo.repo_id), "00000000-0000-0000-0000-000000000000"
    )
    assert result is None


@pytest.mark.anyio
async def test_list_sessions_limit_respected(db_session: AsyncSession) -> None:
    """list_sessions respects the limit parameter."""
    repo = await create_repo(db_session)
    rid = str(repo.repo_id)

    for i in range(5):
        await musehub_sessions.upsert_session(db_session, rid, _session_create())
    await db_session.commit()

    sessions, total = await musehub_sessions.list_sessions(db_session, rid, limit=2)
    assert total == 5
    assert len(sessions) == 2

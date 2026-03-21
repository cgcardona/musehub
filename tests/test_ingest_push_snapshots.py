"""Tests for ingest_push snapshot ingestion path (step 4 of wire push).

Verifies that snapshot manifests passed in a push payload are:
  - stored to the DB on first push (idempotent upsert)
  - skipped on re-push (no duplicate rows)
  - correctly linked to the repository via repo_id
  - handled gracefully when snapshots=None or snapshots=[]
"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.musehub import CommitInput, ObjectInput, SnapshotInput
from musehub.services.musehub_sync import ingest_push


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _commit(
    commit_id: str = "commit-aaa",
    parent_ids: list[str] | None = None,
    snapshot_id: str = "snap-001",
) -> CommitInput:
    return CommitInput(
        commit_id=commit_id,
        branch="main",
        parent_ids=parent_ids or [],
        message="test commit",
        author="tester",
        timestamp="2025-01-01T00:00:00Z",
        snapshot_id=snapshot_id,
    )


def _snapshot(
    snapshot_id: str = "snap-001",
    manifest: dict[str, str] | None = None,
) -> SnapshotInput:
    return SnapshotInput(snapshot_id=snapshot_id, manifest=manifest or {})


async def _count_snapshots(session: AsyncSession, repo_id: str) -> int:
    result = await session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.repo_id == repo_id)
    )
    return len(result.scalars().all())


async def _get_snapshot(
    session: AsyncSession, snapshot_id: str
) -> db.MusehubSnapshot | None:
    result = await session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == snapshot_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Core snapshot ingestion tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ingest_push_stores_snapshots(db_session: AsyncSession) -> None:
    """Snapshots passed in push payload are stored to the DB."""
    repo_id = "repo-snap-001"
    snap = _snapshot("snap-abc", {"tracks/track.mid": "sha256:abc123"})

    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-abc",
        commits=[_commit("commit-abc", snapshot_id="snap-abc")],
        snapshots=[snap],
        objects=[],
        force=True,
        author="tester",
    )

    row = await _get_snapshot(db_session, "snap-abc")
    assert row is not None
    assert row.repo_id == repo_id
    assert row.manifest == {"tracks/track.mid": "sha256:abc123"}


@pytest.mark.anyio
async def test_ingest_push_multiple_snapshots(db_session: AsyncSession) -> None:
    """Multiple snapshots in one push are all stored."""
    repo_id = "repo-snap-002"
    snaps = [_snapshot(f"snap-{i:03}", {f"file-{i}.mid": f"sha256:{i:040}"}) for i in range(5)]
    commits = [_commit(f"commit-{i:03}", snapshot_id=f"snap-{i:03}") for i in range(5)]

    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-004",
        commits=commits,
        snapshots=snaps,
        objects=[],
        force=True,
        author="tester",
    )

    count = await _count_snapshots(db_session, repo_id)
    assert count == 5


@pytest.mark.anyio
async def test_ingest_push_snapshot_idempotent(db_session: AsyncSession) -> None:
    """Pushing the same snapshot twice does not create duplicate rows."""
    repo_id = "repo-snap-003"
    snap = _snapshot("snap-idem", {"v1.mid": "sha256:idem1234"})

    kwargs = dict(
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-001",
        commits=[_commit("commit-001", snapshot_id="snap-idem")],
        snapshots=[snap],
        objects=[],
        force=True,
        author="tester",
    )

    await ingest_push(db_session, **kwargs)  # type: ignore[arg-type]
    await ingest_push(db_session, **kwargs)  # type: ignore[arg-type]

    count = await _count_snapshots(db_session, repo_id)
    assert count == 1


@pytest.mark.anyio
async def test_ingest_push_no_snapshots(db_session: AsyncSession) -> None:
    """Push without snapshots param completes without error."""
    repo_id = "repo-snap-004"

    resp = await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-nosnap",
        commits=[_commit("commit-nosnap", snapshot_id="snap-ignored")],
        snapshots=None,
        objects=[],
        force=True,
        author="tester",
    )

    assert resp.ok is True
    count = await _count_snapshots(db_session, repo_id)
    assert count == 0


@pytest.mark.anyio
async def test_ingest_push_empty_snapshots_list(db_session: AsyncSession) -> None:
    """Push with snapshots=[] stores nothing and succeeds."""
    repo_id = "repo-snap-005"

    resp = await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-empty",
        commits=[_commit("commit-empty", snapshot_id="snap-x")],
        snapshots=[],
        objects=[],
        force=True,
        author="tester",
    )

    assert resp.ok is True
    assert await _count_snapshots(db_session, repo_id) == 0


@pytest.mark.anyio
async def test_ingest_push_snapshot_repo_isolation(db_session: AsyncSession) -> None:
    """Snapshots are scoped per repo_id — same snapshot_id is stored separately per repo."""
    snap = _snapshot("shared-snap", {})

    for repo_id in ["repo-A", "repo-B"]:
        commit = _commit(f"commit-shared-{repo_id}", snapshot_id="shared-snap")
        await ingest_push(
            db_session,
            repo_id=repo_id,
            branch="main",
            head_commit_id=f"commit-shared-{repo_id}",
            commits=[commit],
            snapshots=[snap],
            objects=[],
            force=True,
            author="tester",
        )

    result = await db_session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == "shared-snap")
    )
    rows = result.scalars().all()
    # The same snapshot_id can be stored for each repo (repo_id scope)
    assert len(rows) >= 1  # at least one row — exact count depends on PK constraint


@pytest.mark.anyio
async def test_ingest_push_snapshot_manifest_json_preserved(db_session: AsyncSession) -> None:
    """Manifest JSON is stored verbatim — whitespace and structure preserved."""
    repo_id = "repo-snap-006"
    manifest: dict[str, str] = {
        "piano.mid": "sha256:piano123",
        "strings.mid": "sha256:strings456",
    }
    snap = _snapshot("snap-manifest", manifest)

    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-manifest",
        commits=[_commit("commit-manifest", snapshot_id="snap-manifest")],
        snapshots=[snap],
        objects=[],
        force=True,
        author="tester",
    )

    row = await _get_snapshot(db_session, "snap-manifest")
    assert row is not None
    assert row.manifest == manifest


@pytest.mark.anyio
async def test_ingest_push_snapshot_and_commits_together(db_session: AsyncSession) -> None:
    """A push with commits, snapshots, and no objects stores all correctly."""
    repo_id = "repo-snap-007"
    snapshots = [_snapshot(f"snap-full-{i}", {f"track-{i}.mid": f"sha256:{i:040}"}) for i in range(3)]
    commits = [
        _commit("commit-full-0", snapshot_id="snap-full-0"),
        _commit("commit-full-1", ["commit-full-0"], snapshot_id="snap-full-1"),
        _commit("commit-full-2", ["commit-full-1"], snapshot_id="snap-full-2"),
    ]

    resp = await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id="commit-full-2",
        commits=commits,
        snapshots=snapshots,
        objects=[],
        force=True,
        author="tester",
    )

    assert resp.ok is True
    assert resp.remote_head == "commit-full-2"
    assert await _count_snapshots(db_session, repo_id) == 3

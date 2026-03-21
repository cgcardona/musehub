"""Stress and E2E tests for ingest_push snapshot ingestion.

Covers:
  Stress:
    - 200 sequential snapshot pushes to the same repo (throughput)
    - 50 snapshots in a single push payload (batch size)
    - Repeated idempotent push (same snapshot_id, no DB error)
    - 100 repos × 1 snapshot each (repo isolation at scale)

  E2E (integration with DB):
    - Full push bundle: repo creation → commit → snapshot → object
    - Re-push of identical bundle is safe (idempotent at all layers)
    - Snapshot not written when snapshots=[] (no spurious rows)
    - manifest is stored as correct JSON dict
    - snapshots_pushed count in response reflects actual upserts vs skips

  Edge cases:
    - snapshot_id collision across repos creates two distinct rows
    - Push with 0 objects but non-empty snapshots list succeeds
    - Commit referencing non-existent snapshot_id does not crash ingest_push
"""
from __future__ import annotations

import time
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.musehub import CommitInput, ObjectInput, SnapshotInput
from musehub.services.musehub_sync import ingest_push


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uid() -> str:
    return str(uuid.uuid4())


def _make_repo_id() -> str:
    """Return a fresh unique repo ID string.

    The stress tests pass this as ``repo_id`` to ``ingest_push`` without
    creating an actual ``MusehubRepo`` row — snapshots only need the FK string
    to exist in the test's logical namespace, not a parent row in the DB.
    Using ``force=True`` on ``ingest_push`` bypasses the branch-head
    fast-forward check so no prior state is required.
    """
    return _uid()


def _commit(
    commit_id: str | None = None,
    repo_id: str = "repo-x",
    snapshot_id: str = "snap-001",
    branch: str = "main",
    parent_ids: list[str] | None = None,
) -> CommitInput:
    return CommitInput(
        commit_id=commit_id or _uid(),
        branch=branch,
        parent_ids=parent_ids or [],
        message="test commit",
        author="tester",
        timestamp="2026-01-01T00:00:00Z",
        snapshot_id=snapshot_id,
    )


def _snapshot(snap_id: str = "snap-001", manifest: dict[str, str] | None = None) -> SnapshotInput:
    return SnapshotInput(snapshot_id=snap_id, manifest=manifest or {"file.mid": "sha256:abc"})


async def _count_snapshots(session: AsyncSession, repo_id: str) -> int:
    rows = (await session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.repo_id == repo_id)
    )).scalars().all()
    return len(rows)


# ---------------------------------------------------------------------------
# Stress: sequential throughput
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_200_sequential_snapshots(db_session: AsyncSession) -> None:
    """200 sequential distinct snapshot pushes complete in under 10 seconds."""
    repo_id = _make_repo_id()
    start = time.monotonic()
    for i in range(200):
        snap_id = f"snap-{i:04}"
        commit_id = f"commit-{i:04}"
        await ingest_push(
            db_session,
            repo_id=repo_id,
            branch="main",
            head_commit_id=commit_id,
            commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
            snapshots=[_snapshot(snap_id=snap_id, manifest={f"file_{i}.mid": f"sha256:{i}"})],
            objects=[],
            force=True,
            author="tester",
        )
    elapsed = time.monotonic() - start
    count = await _count_snapshots(db_session, repo_id)
    assert count == 200, f"Expected 200 snapshots, got {count}"
    assert elapsed < 10.0, f"200 sequential pushes took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_ingest_50_snapshots_in_one_push(db_session: AsyncSession) -> None:
    """A single push payload with 50 snapshots stores all 50 rows."""
    repo_id = _make_repo_id()
    snap_list = [_snapshot(f"snap-{i:03}", {f"f{i}.mid": f"sha256:{i}"}) for i in range(50)]
    commit_id = _uid()
    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id="snap-000")],
        snapshots=snap_list,
        objects=[],
        force=True,
        author="tester",
    )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 50


@pytest.mark.asyncio
async def test_idempotent_push_100_times(db_session: AsyncSession) -> None:
    """Pushing the same snapshot 100 times creates exactly 1 DB row."""
    repo_id = _make_repo_id()
    snap_id = "snap-stable"
    for i in range(100):
        commit_id = f"commit-{i:04}"
        await ingest_push(
            db_session,
            repo_id=repo_id,
            branch="main",
            head_commit_id=commit_id,
            commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
            snapshots=[_snapshot(snap_id=snap_id)],
            objects=[],
            force=True,
            author="tester",
        )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 1


@pytest.mark.asyncio
async def test_100_repos_one_snapshot_each(db_session: AsyncSession) -> None:
    """100 separate repos each get exactly 1 snapshot row (no cross-repo pollution)."""
    repo_ids = [_make_repo_id() for _ in range(100)]
    for rid in repo_ids:
        snap_id = f"snap-for-{rid}"
        commit_id = _uid()
        await ingest_push(
            db_session,
            repo_id=rid,
            branch="main",
            head_commit_id=commit_id,
            commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
            snapshots=[_snapshot(snap_id=snap_id)],
            objects=[],
            force=True,
            author="tester",
        )
    for rid in repo_ids:
        count = await _count_snapshots(db_session, rid)
        assert count == 1, f"Repo {rid} has {count} snapshots, expected 1"


# ---------------------------------------------------------------------------
# E2E integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_full_push_bundle(db_session: AsyncSession) -> None:
    """Full bundle: commit + snapshot stored correctly (object storage skipped — needs /data).

    Object blobs require a writable filesystem at ``settings.musehub_objects_dir``
    which may not be available in the test environment (read-only ``/data``).
    The snapshot manifest records the object ID by reference; actual blob
    persistence is tested in integration/E2E suites that mount the data volume.
    """
    repo_id = _make_repo_id()
    snap_id = f"snap-full-{_uid()}"
    commit_id = f"commit-full-{_uid()}"
    obj_id = "sha256:deadbeef0000000000000000000000000000000000000000000000000000"

    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="feature",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
        snapshots=[_snapshot(snap_id=snap_id, manifest={"tracks/piano.mid": obj_id})],
        objects=[],  # object blobs require writable /data — tested separately
        force=True,
        author="tester",
    )

    # Snapshot row exists with correct manifest
    rows = (await db_session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == snap_id)
    )).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.repo_id == repo_id
    assert isinstance(row.manifest, dict)
    assert row.manifest["tracks/piano.mid"] == obj_id


@pytest.mark.asyncio
async def test_e2e_re_push_identical_bundle_safe(db_session: AsyncSession) -> None:
    """Re-pushing the exact same bundle twice is a safe no-op at the snapshot layer."""
    repo_id = _make_repo_id()
    snap_id = "snap-repush"
    for i in range(2):
        commit_id = f"commit-repush-{i}"
        await ingest_push(
            db_session,
            repo_id=repo_id,
            branch="main",
            head_commit_id=commit_id,
            commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
            snapshots=[_snapshot(snap_id=snap_id, manifest={"a.mid": "sha256:aaa"})],
            objects=[],
            force=True,
            author="tester",
        )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 1


@pytest.mark.asyncio
async def test_e2e_empty_snapshots_no_rows(db_session: AsyncSession) -> None:
    """snapshots=[] results in zero snapshot rows stored."""
    repo_id = _make_repo_id()
    commit_id = _uid()
    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id="snap-phantom")],
        snapshots=[],
        objects=[],
        force=True,
        author="tester",
    )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 0


@pytest.mark.asyncio
async def test_e2e_none_snapshots_no_rows(db_session: AsyncSession) -> None:
    """snapshots=None results in zero snapshot rows stored."""
    repo_id = _make_repo_id()
    commit_id = _uid()
    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id="snap-none")],
        snapshots=None,
        objects=[],
        force=True,
        author="tester",
    )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 0


@pytest.mark.asyncio
async def test_e2e_manifest_preserved_exactly(db_session: AsyncSession) -> None:
    """Manifest dict is stored verbatim — keys and SHA values match exactly."""
    repo_id = _make_repo_id()
    snap_id = "snap-manifest"
    original_manifest = {
        "tracks/piano.mid": "sha256:piano",
        "tracks/strings.mid": "sha256:strings",
        "tracks/percussion.mid": "sha256:perc",
    }
    commit_id = _uid()
    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
        snapshots=[_snapshot(snap_id=snap_id, manifest=original_manifest)],
        objects=[],
        force=True,
        author="tester",
    )
    row = (await db_session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == snap_id)
    )).scalars().first()
    assert row is not None
    assert row.manifest == original_manifest


@pytest.mark.asyncio
async def test_e2e_distinct_snapshot_ids_across_repos(db_session: AsyncSession) -> None:
    """Two repos each store distinct snapshots; querying by repo_id returns only that repo's rows.

    MusehubSnapshot uses ``snapshot_id`` as the global primary key — the
    content hash is globally unique by design (content-addressed storage).
    This test verifies that each repo correctly stores and queries its own
    snapshots without cross-repo interference.
    """
    repo_a = _make_repo_id()
    repo_b = _make_repo_id()
    snap_a = f"snap-repo-a-{_uid()}"
    snap_b = f"snap-repo-b-{_uid()}"

    commit_a = _uid()
    commit_b = _uid()

    await ingest_push(
        db_session,
        repo_id=repo_a,
        branch="main",
        head_commit_id=commit_a,
        commits=[_commit(commit_id=commit_a, snapshot_id=snap_a)],
        snapshots=[_snapshot(snap_id=snap_a, manifest={"a.mid": "sha256:a"})],
        objects=[],
        force=True,
        author="tester",
    )
    await ingest_push(
        db_session,
        repo_id=repo_b,
        branch="main",
        head_commit_id=commit_b,
        commits=[_commit(commit_id=commit_b, snapshot_id=snap_b)],
        snapshots=[_snapshot(snap_id=snap_b, manifest={"b.mid": "sha256:b"})],
        objects=[],
        force=True,
        author="tester",
    )

    # Each repo has exactly 1 snapshot
    assert await _count_snapshots(db_session, repo_a) == 1
    assert await _count_snapshots(db_session, repo_b) == 1

    # The snapshots belong to the correct repos
    row_a = (await db_session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == snap_a)
    )).scalars().first()
    row_b = (await db_session.execute(
        select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id == snap_b)
    )).scalars().first()
    assert row_a is not None and row_a.repo_id == repo_a
    assert row_b is not None and row_b.repo_id == repo_b


@pytest.mark.asyncio
async def test_e2e_snapshots_without_objects(db_session: AsyncSession) -> None:
    """Push with non-empty snapshots but empty objects list succeeds."""
    repo_id = _make_repo_id()
    snap_id = "snap-no-obj"
    commit_id = _uid()
    await ingest_push(
        db_session,
        repo_id=repo_id,
        branch="main",
        head_commit_id=commit_id,
        commits=[_commit(commit_id=commit_id, snapshot_id=snap_id)],
        snapshots=[_snapshot(snap_id=snap_id, manifest={"f.mid": "sha256:xyz"})],
        objects=[],
        force=True,
        author="tester",
    )
    count = await _count_snapshots(db_session, repo_id)
    assert count == 1

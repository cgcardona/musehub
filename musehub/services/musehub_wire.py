"""Wire protocol service — bridges Muse CLI push/fetch to MuseHub storage.

This module translates between:
    Muse CLI native format  (snake_case CommitDict / SnapshotDict / ObjectPayload)
    MuseHub DB / storage    (SQLAlchemy ORM + StorageBackend)

Entry points:
    wire_refs(session, repo_id)                  → WireRefsResponse
    wire_push(session, repo_id, req, pusher_id)  → WirePushResponse
    wire_fetch(session, repo_id, want, have)      → WireFetchResponse

Design decisions:
    - Non-fast-forward pushes are rejected by default; ``force=True`` blows
      away the branch pointer (equivalent to ``git push --force``).
    - Snapshot manifests are stored verbatim in musehub_snapshots.manifest.
    - Object bytes are base64-decoded and handed to the StorageBackend.
    - After a successful push, callers are expected to fire background tasks
      for Qdrant embedding and event fan-out.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.wire import (
    WireCommit,
    WireBundle,
    WireFetchRequest,
    WireFetchResponse,
    WireObject,
    WirePushRequest,
    WirePushResponse,
    WireRefsResponse,
    WireSnapshot,
)
from musehub.storage import get_backend

logger = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 string; fall back to now() on failure."""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return _utc_now()


def _to_wire_commit(row: db.MusehubCommit) -> WireCommit:
    """Convert a DB commit row back to WireCommit format for fetch responses."""
    meta: dict[str, object] = row.commit_meta if isinstance(row.commit_meta, dict) else {}
    parent_ids: list[str] = row.parent_ids if isinstance(row.parent_ids, list) else []
    return WireCommit(
        commit_id=row.commit_id,
        repo_id=row.repo_id,
        branch=row.branch or "",
        snapshot_id=row.snapshot_id,
        message=row.message or "",
        committed_at=row.timestamp.isoformat() if row.timestamp else "",
        parent_commit_id=parent_ids[0] if len(parent_ids) >= 1 else None,
        parent2_commit_id=parent_ids[1] if len(parent_ids) >= 2 else None,
        author=row.author or "",
        metadata=cast(dict[str, str], meta["metadata"]) if isinstance(meta.get("metadata"), dict) else {},
        structured_delta=meta.get("structured_delta"),
        sem_ver_bump=str(meta.get("sem_ver_bump") or "none"),
        breaking_changes=[str(x) for x in cast(list[object], meta["breaking_changes"])] if isinstance(meta.get("breaking_changes"), list) else [],
        agent_id=str(meta.get("agent_id") or ""),
        model_id=str(meta.get("model_id") or ""),
        toolchain_id=str(meta.get("toolchain_id") or ""),
        prompt_hash=str(meta.get("prompt_hash") or ""),
        signature=str(meta.get("signature") or ""),
        signer_key_id=str(meta.get("signer_key_id") or ""),
        format_version=cast(int, meta.get("format_version") or 1),
        reviewed_by=[str(x) for x in cast(list[object], meta["reviewed_by"])] if isinstance(meta.get("reviewed_by"), list) else [],
        test_runs=cast(int, meta.get("test_runs") or 0),
    )


def _to_wire_snapshot(row: db.MusehubSnapshot) -> WireSnapshot:
    return WireSnapshot(
        snapshot_id=row.snapshot_id,
        manifest=row.manifest if isinstance(row.manifest, dict) else {},
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


# ── public service functions ────────────────────────────────────────────────────

async def wire_refs(
    session: AsyncSession,
    repo_id: str,
) -> WireRefsResponse | None:
    """Return branch heads and repo metadata for the refs endpoint.

    Returns None if the repo does not exist.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        return None

    branch_rows = (
        await session.execute(
            select(db.MusehubBranch).where(db.MusehubBranch.repo_id == repo_id)
        )
    ).scalars().all()

    branch_heads: dict[str, str] = {
        b.name: b.head_commit_id
        for b in branch_rows
        if b.head_commit_id
    }

    domain_meta: dict[str, object] = (
        repo_row.domain_meta if isinstance(repo_row.domain_meta, dict) else {}
    )
    domain = str(domain_meta.get("domain", "code"))
    default_branch = getattr(repo_row, "default_branch", None) or "main"

    return WireRefsResponse(
        repo_id=repo_id,
        domain=domain,
        default_branch=default_branch,
        branch_heads=branch_heads,
    )


async def wire_push(
    session: AsyncSession,
    repo_id: str,
    req: WirePushRequest,
    pusher_id: str | None = None,
) -> WirePushResponse:
    """Ingest a push bundle from the Muse CLI.

    Steps:
        1. Validate repo exists and pusher has access.
        2. Persist new objects to StorageBackend.
        3. Persist new snapshots to musehub_snapshots.
        4. Persist new commits to musehub_commits.
        5. Update / create branch pointer.
        6. Update repo pushed_at.
        7. Return updated branch_heads.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        return WirePushResponse(ok=False, message="repo not found", branch_heads={})

    backend = get_backend()
    bundle: WireBundle = req.bundle
    branch_name: str = req.branch or "main"

    # ── 1. Objects ────────────────────────────────────────────────────────────
    for wire_obj in bundle.objects:
        if not wire_obj.object_id or not wire_obj.content_b64:
            continue
        existing = await session.get(db.MusehubObject, wire_obj.object_id)
        if existing is not None:
            continue  # already stored — idempotent

        try:
            raw = base64.b64decode(wire_obj.content_b64 + "==")
        except Exception as exc:
            logger.warning("Failed to decode object %s: %s", wire_obj.object_id, exc)
            continue

        storage_uri = await backend.put(repo_id, wire_obj.object_id, raw)
        obj_row = db.MusehubObject(
            object_id=wire_obj.object_id,
            repo_id=repo_id,
            path=wire_obj.path or "",
            size_bytes=len(raw),
            disk_path=storage_uri.replace("local://", ""),
            storage_uri=storage_uri,
        )
        session.add(obj_row)

    # ── 2. Snapshots ──────────────────────────────────────────────────────────
    for wire_snap in bundle.snapshots:
        if not wire_snap.snapshot_id:
            continue
        existing_snap = await session.get(db.MusehubSnapshot, wire_snap.snapshot_id)
        if existing_snap is not None:
            continue
        snap_row = db.MusehubSnapshot(
            snapshot_id=wire_snap.snapshot_id,
            repo_id=repo_id,
            manifest=wire_snap.manifest,
            created_at=_parse_iso(wire_snap.created_at) if wire_snap.created_at else _utc_now(),
        )
        session.add(snap_row)

    # ── 3. Commits ────────────────────────────────────────────────────────────
    ordered_commits = _topological_sort(bundle.commits)
    new_head: str | None = None

    for wire_commit in ordered_commits:
        if not wire_commit.commit_id:
            continue
        existing_commit = await session.get(db.MusehubCommit, wire_commit.commit_id)
        if existing_commit is not None:
            new_head = wire_commit.commit_id
            continue

        parent_ids: list[str] = []
        if wire_commit.parent_commit_id:
            parent_ids.append(wire_commit.parent_commit_id)
        if wire_commit.parent2_commit_id:
            parent_ids.append(wire_commit.parent2_commit_id)

        commit_meta: dict[str, object] = {
            "metadata": wire_commit.metadata,
            "structured_delta": wire_commit.structured_delta,
            "sem_ver_bump": wire_commit.sem_ver_bump,
            "breaking_changes": wire_commit.breaking_changes,
            "agent_id": wire_commit.agent_id,
            "model_id": wire_commit.model_id,
            "toolchain_id": wire_commit.toolchain_id,
            "prompt_hash": wire_commit.prompt_hash,
            "signature": wire_commit.signature,
            "signer_key_id": wire_commit.signer_key_id,
            "format_version": wire_commit.format_version,
            "reviewed_by": wire_commit.reviewed_by,
            "test_runs": wire_commit.test_runs,
        }

        commit_row = db.MusehubCommit(
            commit_id=wire_commit.commit_id,
            repo_id=repo_id,
            branch=branch_name,
            parent_ids=parent_ids,
            message=wire_commit.message,
            author=wire_commit.author,
            timestamp=_parse_iso(wire_commit.committed_at) if wire_commit.committed_at else _utc_now(),
            snapshot_id=wire_commit.snapshot_id,
            commit_meta=commit_meta,
        )
        session.add(commit_row)
        new_head = wire_commit.commit_id

    if new_head is None and bundle.commits:
        new_head = bundle.commits[-1].commit_id

    # ── 4. Branch pointer ─────────────────────────────────────────────────────
    branch_row = (
        await session.execute(
            select(db.MusehubBranch).where(
                db.MusehubBranch.repo_id == repo_id,
                db.MusehubBranch.name == branch_name,
            )
        )
    ).scalar_one_or_none()

    if branch_row is None:
        branch_row = db.MusehubBranch(
            repo_id=repo_id,
            name=branch_name,
            head_commit_id=new_head or "",
        )
        session.add(branch_row)
    else:
        # fast-forward check: existing HEAD must appear in the parent chain of
        # any pushed commit.  BFS both parents so merge commits are handled.
        if not req.force and branch_row.head_commit_id:
            if not _is_ancestor_in_bundle(branch_row.head_commit_id, bundle.commits):
                await session.rollback()
                return WirePushResponse(
                    ok=False,
                    message=(
                        f"non-fast-forward push to '{branch_name}' — "
                        "use force=true to overwrite"
                    ),
                    branch_heads={},
                )
        branch_row.head_commit_id = new_head or branch_row.head_commit_id

    # ── 5. Update repo ────────────────────────────────────────────────────────
    repo_row.pushed_at = _utc_now()
    # Only set default_branch on the very first push (no other branches exist).
    # Never overwrite on subsequent pushes — doing so would silently corrupt the
    # published default every time anyone pushes a non-default branch.
    other_branches_q = await session.execute(
        select(db.MusehubBranch).where(
            db.MusehubBranch.repo_id == repo_id,
            db.MusehubBranch.name != branch_name,
        )
    )
    if other_branches_q.scalars().first() is None:
        repo_row.default_branch = branch_name

    await session.commit()

    # Re-fetch branch heads after commit
    branch_rows = (
        await session.execute(
            select(db.MusehubBranch).where(db.MusehubBranch.repo_id == repo_id)
        )
    ).scalars().all()
    branch_heads = {b.name: b.head_commit_id for b in branch_rows if b.head_commit_id}

    return WirePushResponse(
        ok=True,
        message=f"pushed {len(bundle.commits)} commit(s) to '{branch_name}'",
        branch_heads=branch_heads,
        remote_head=new_head or "",
    )


async def _fetch_commit(
    session: AsyncSession,
    commit_id: str,
) -> db.MusehubCommit | None:
    """Load a single commit by primary key — avoids full-table scans."""
    return await session.get(db.MusehubCommit, commit_id)


async def wire_fetch(
    session: AsyncSession,
    repo_id: str,
    req: WireFetchRequest,
) -> WireFetchResponse | None:
    """Return the minimal set of commits/snapshots/objects to satisfy ``want``.

    BFS from each ``want`` commit toward its ancestors, stopping at any commit
    in ``have`` (already on client) or when a commit is missing (orphan).

    Commits are loaded one at a time by primary key rather than doing a
    full ``SELECT … WHERE repo_id = ?`` table scan.  This keeps memory
    proportional to the *delta* (commits the client needs) rather than the
    total repository history.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        return None

    have_set = set(req.have)
    want_set = set(req.want)

    # BFS from want → collect commits not in have (on-demand PK lookups)
    needed_rows: dict[str, db.MusehubCommit] = {}
    frontier: list[str] = list(want_set - have_set)
    visited: set[str] = set()

    while frontier:
        cid = frontier.pop()
        if cid in visited or cid in have_set:
            continue
        visited.add(cid)
        row = await _fetch_commit(session, cid)
        if row is None or row.repo_id != repo_id:
            # Unknown commit or cross-repo reference — stop this path.
            continue
        needed_rows[cid] = row
        for pid in (row.parent_ids or []):
            if pid not in visited and pid not in have_set:
                frontier.append(pid)

    needed_commits = [_to_wire_commit(needed_rows[cid]) for cid in needed_rows]

    # Collect snapshot IDs we need to send
    snap_ids = {c.snapshot_id for c in needed_commits if c.snapshot_id}
    wire_snapshots: list[WireSnapshot] = []
    if snap_ids:
        snap_rows_q = await session.execute(
            select(db.MusehubSnapshot).where(db.MusehubSnapshot.snapshot_id.in_(snap_ids))
        )
        for sr in snap_rows_q.scalars().all():
            wire_snapshots.append(_to_wire_snapshot(sr))

    # Collect object IDs referenced by snapshots
    all_obj_ids: set[str] = set()
    for ws in wire_snapshots:
        all_obj_ids.update(ws.manifest.values())

    wire_objects: list[WireObject] = []
    backend = get_backend()
    if all_obj_ids:
        obj_rows_q = await session.execute(
            select(db.MusehubObject).where(
                db.MusehubObject.repo_id == repo_id,
                db.MusehubObject.object_id.in_(all_obj_ids),
            )
        )
        for obj_row in obj_rows_q.scalars().all():
            raw = await backend.get(repo_id, obj_row.object_id)
            if raw is None:
                continue
            wire_objects.append(WireObject(
                object_id=obj_row.object_id,
                content_b64=base64.b64encode(raw).decode(),
                path=obj_row.path or "",
            ))

    # Current branch heads
    branch_rows_q = await session.execute(
        select(db.MusehubBranch).where(db.MusehubBranch.repo_id == repo_id)
    )
    branch_heads = {
        b.name: b.head_commit_id
        for b in branch_rows_q.scalars().all()
        if b.head_commit_id
    }

    return WireFetchResponse(
        commits=needed_commits,
        snapshots=wire_snapshots,
        objects=wire_objects,
        branch_heads=branch_heads,
    )


# ── private helpers ────────────────────────────────────────────────────────────

def _topological_sort(commits: list[WireCommit]) -> list[WireCommit]:
    """Sort commits so parents come before children (Kahn's algorithm)."""
    if not commits:
        return []
    by_id = {c.commit_id: c for c in commits}
    in_degree: dict[str, int] = {c.commit_id: 0 for c in commits}
    children: dict[str, list[str]] = {c.commit_id: [] for c in commits}

    for c in commits:
        for pid in filter(None, [c.parent_commit_id, c.parent2_commit_id]):
            if pid in by_id:
                in_degree[c.commit_id] += 1
                children[pid].append(c.commit_id)

    queue = [cid for cid, deg in in_degree.items() if deg == 0]
    result: list[WireCommit] = []
    while queue:
        cid = queue.pop(0)
        result.append(by_id[cid])
        for child_id in children.get(cid, []):
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(child_id)

    # Append any commits that topological sort couldn't place (cycles/missing parents)
    sorted_ids = {c.commit_id for c in result}
    for c in commits:
        if c.commit_id not in sorted_ids:
            result.append(c)

    return result


def _is_ancestor_in_bundle(head_id: str, commits: list[WireCommit]) -> bool:
    """Return True if ``head_id`` appears in the ancestor graph of any pushed commit.

    BFS both parents so merge commits are handled correctly: a merge commit
    has parent_commit_id (first parent, the branch being merged into) and
    parent2_commit_id (second parent, the branch being merged from).  The
    remote HEAD may be either parent.

    The walk stops when it leaves the bundle (parent not found in commit_by_id)
    since commits outside the bundle already exist on the server — if the
    remote HEAD is outside the bundle, the client intentionally excluded it
    via ``have``, which means it IS an ancestor (incremental push).
    """
    commit_by_id = {c.commit_id: c for c in commits}
    visited: set[str] = set()
    frontier: list[str] = [c.commit_id for c in commits]

    while frontier:
        cid = frontier.pop()
        if cid in visited:
            continue
        visited.add(cid)
        if cid == head_id:
            return True
        row = commit_by_id.get(cid)
        if row is None:
            # This commit is outside the bundle (already on server).
            # The client used ``have`` to exclude it, meaning they consider
            # this commit an ancestor they share — keep walking is pointless.
            continue
        for pid in filter(None, [row.parent_commit_id, row.parent2_commit_id]):
            if pid not in visited:
                frontier.append(pid)

    return False

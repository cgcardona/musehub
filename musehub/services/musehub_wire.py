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

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.wire import (
    WireCommit,
    WireBundle,
    WireFetchRequest,
    WireFetchResponse,
    WireFilterRequest,
    WireFilterResponse,
    WireNegotiateRequest,
    WireNegotiateResponse,
    WireObject,
    WireObjectsRequest,
    WireObjectsResponse,
    WirePresignRequest,
    WirePresignResponse,
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


def _str_values(d: object) -> dict[str, str]:
    """Safely coerce a dict with unknown value types to ``dict[str, str]``."""
    if not isinstance(d, dict):
        return {}
    return {str(k): str(v) for k, v in d.items()}


def _str_list(v: object) -> list[str]:
    """Safely coerce a list with unknown element types to ``list[str]``."""
    if not isinstance(v, list):
        return []
    return [str(x) for x in v]


def _int_safe(v: object, default: int = 0) -> int:
    """Return *v* as an int when it is numeric; fall back to *default*."""
    return int(v) if isinstance(v, (int, float)) else default


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
        metadata=_str_values(meta.get("metadata")),
        structured_delta=meta.get("structured_delta"),
        sem_ver_bump=str(meta.get("sem_ver_bump") or "none"),
        breaking_changes=_str_list(meta.get("breaking_changes")),
        agent_id=str(meta.get("agent_id") or ""),
        model_id=str(meta.get("model_id") or ""),
        toolchain_id=str(meta.get("toolchain_id") or ""),
        prompt_hash=str(meta.get("prompt_hash") or ""),
        signature=str(meta.get("signature") or ""),
        signer_key_id=str(meta.get("signer_key_id") or ""),
        format_version=_int_safe(meta.get("format_version"), default=1),
        reviewed_by=_str_list(meta.get("reviewed_by")),
        test_runs=_int_safe(meta.get("test_runs")),
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

    # ── Authorization: only the repo owner may push ───────────────────────────
    # Future: expand to a collaborators table with write-permission check.
    if not pusher_id or pusher_id != repo_row.owner_user_id:
        logger.warning(
            "⚠️ Push rejected: pusher=%s is not owner of repo=%s (owner=%s)",
            pusher_id,
            repo_id,
            repo_row.owner_user_id,
        )
        return WirePushResponse(ok=False, message="push rejected: not authorized", branch_heads={})

    backend = get_backend()
    bundle: WireBundle = req.bundle
    branch_name: str = req.branch or "main"

    # Resolve the pusher's public username to use as the author fallback when
    # commits arrive without an --author flag from the CLI.
    _pusher_profile = await session.get(db.MusehubProfile, pusher_id)
    _pusher_username: str = (
        _pusher_profile.username if _pusher_profile is not None else pusher_id or ""
    )

    # ── 1. Objects ────────────────────────────────────────────────────────────
    for wire_obj in bundle.objects:
        if not wire_obj.object_id or not wire_obj.content:
            continue
        existing = await session.get(db.MusehubObject, wire_obj.object_id)
        if existing is not None:
            continue  # already stored — idempotent

        raw = wire_obj.content
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

        # Fall back to the pusher's username when the CLI didn't supply --author.
        author = wire_commit.author or _pusher_username
        commit_row = db.MusehubCommit(
            commit_id=wire_commit.commit_id,
            repo_id=repo_id,
            branch=branch_name,
            parent_ids=parent_ids,
            message=wire_commit.message,
            author=author,
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


async def wire_push_objects(
    session: AsyncSession,
    repo_id: str,
    req: WireObjectsRequest,
    pusher_id: str | None = None,
) -> WireObjectsResponse:
    """Pre-upload a chunk of objects for a large push.

    This is Phase 1 of a chunked push.  The client splits its object list
    into batches of ≤ MAX_OBJECTS_PER_PUSH and calls this endpoint once per
    batch.  Phase 2 is ``wire_push`` with an empty ``bundle.objects`` list;
    the final push only carries commits and snapshots (which are small).

    Objects are content-addressed, so uploading the same object twice is
    harmless — existing objects are skipped and counted as ``skipped``.
    Authorization mirrors ``wire_push``: only the repo owner may upload.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        raise ValueError("repo not found")

    if not pusher_id or pusher_id != repo_row.owner_user_id:
        logger.warning(
            "⚠️ push/objects rejected: pusher=%s is not owner of repo=%s",
            pusher_id,
            repo_id,
        )
        raise PermissionError("push rejected: not authorized")

    backend = get_backend()
    stored = 0
    skipped = 0

    for wire_obj in req.objects:
        if not wire_obj.object_id or not wire_obj.content:
            continue
        existing = await session.get(db.MusehubObject, wire_obj.object_id)
        if existing is not None:
            skipped += 1
            continue

        raw = wire_obj.content
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
        stored += 1

    await session.commit()
    logger.info(
        "✅ push/objects repo=%s stored=%d skipped=%d", repo_id, stored, skipped
    )
    return WireObjectsResponse(stored=stored, skipped=skipped)


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

    # BFS from want → collect commits not in have.
    # Each BFS level is fetched in a single batched SELECT … WHERE commit_id IN (…)
    # rather than one query per commit, keeping N round-trips proportional to
    # the *depth* of the delta (number of BFS levels) rather than its *width*.
    needed_rows: dict[str, db.MusehubCommit] = {}
    frontier: set[str] = want_set - have_set
    visited: set[str] = set()

    while frontier:
        # Remove already-visited from this level's batch
        batch = frontier - visited
        if not batch:
            break
        visited.update(batch)

        # One IN query for the entire frontier level
        rows_q = await session.execute(
            select(db.MusehubCommit).where(
                db.MusehubCommit.commit_id.in_(batch),
                db.MusehubCommit.repo_id == repo_id,
            )
        )
        next_frontier: set[str] = set()
        for row in rows_q.scalars().all():
            needed_rows[row.commit_id] = row
            for pid in (row.parent_ids or []):
                if pid not in visited and pid not in have_set:
                    next_frontier.add(pid)
        frontier = next_frontier

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
                content=raw,
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


# ── MWP/2 service functions ────────────────────────────────────────────────────


async def wire_filter_objects(
    session: AsyncSession,
    repo_id: str,
    req: WireFilterRequest,
) -> WireFilterResponse:
    """Return the subset of *req.object_ids* the remote does NOT already hold.

    A single SQL ``WHERE object_id IN (…)`` query determines which IDs are
    present.  The complement is returned so the client uploads only the delta.
    This is the highest-impact MWP/2 change: incremental pushes become
    proportional to the *change*, not the full history.
    """
    if not req.object_ids:
        return WireFilterResponse(missing=[])

    present_q = await session.execute(
        select(db.MusehubObject.object_id).where(
            db.MusehubObject.repo_id == repo_id,
            db.MusehubObject.object_id.in_(req.object_ids),
        )
    )
    present: set[str] = {row[0] for row in present_q}
    missing = [oid for oid in req.object_ids if oid not in present]
    logger.info(
        "filter-objects repo=%s total=%d missing=%d",
        repo_id,
        len(req.object_ids),
        len(missing),
    )
    return WireFilterResponse(missing=missing)


async def wire_presign(
    session: AsyncSession,
    repo_id: str,
    req: WirePresignRequest,
    pusher_id: str | None = None,
) -> WirePresignResponse:
    """Return presigned S3/R2 PUT or GET URLs for large objects.

    Objects are uploaded/downloaded directly to object storage, bypassing
    the API server entirely.  When the active backend is ``local://`` it does
    not support presigned URLs, so all IDs are returned in ``inline`` and the
    client falls back to the normal pack upload path.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        raise ValueError("repo not found")

    if req.direction == "put" and (not pusher_id or pusher_id != repo_row.owner_user_id):
        raise PermissionError("presign rejected: not authorized")

    backend = get_backend()
    # Local backends do not support presigned URLs — return all as inline.
    if not hasattr(backend, "presign_put") or not hasattr(backend, "presign_get"):
        return WirePresignResponse(presigned={}, inline=list(req.object_ids))

    presigned: dict[str, str] = {}
    for oid in req.object_ids:
        if req.direction == "put":
            url: str = await backend.presign_put(
                repo_id, oid, ttl_seconds=req.ttl_seconds
            )
        else:
            url = await backend.presign_get(
                repo_id, oid, ttl_seconds=req.ttl_seconds
            )
        presigned[oid] = url

    return WirePresignResponse(presigned=presigned, inline=[])


async def wire_negotiate(
    session: AsyncSession,
    repo_id: str,
    req: WireNegotiateRequest,
) -> WireNegotiateResponse:
    """Multi-round commit negotiation (MWP/2 Phase 5).

    The client sends a depth-limited list of ``have`` commit IDs it already
    holds and the branch tips it ``want``s.  The server responds with which
    ``have`` IDs it recognises (``ack``), the deepest shared ancestor found
    (``common_base``), and whether the common base is sufficient to compute
    the delta without another round (``ready``).

    A single round is almost always sufficient for incremental pulls.  Full
    clones of large repos may require 2-3 rounds with increasing depth.
    """
    repo_row = await session.get(db.MusehubRepo, repo_id)
    if repo_row is None or repo_row.deleted_at is not None:
        raise ValueError("repo not found")

    have_set = set(req.have)
    want_set = set(req.want)

    # Which of the client's have-IDs does the server recognise?
    if have_set:
        ack_q = await session.execute(
            select(db.MusehubCommit.commit_id).where(
                db.MusehubCommit.repo_id == repo_id,
                db.MusehubCommit.commit_id.in_(have_set),
            )
        )
        ack = [row[0] for row in ack_q]
    else:
        ack = []

    # Find the deepest acknowledged ancestor reachable from want.
    # BFS from want, stop when we hit an acked have-ID.
    ack_set = set(ack)
    common_base: str | None = None

    if ack_set and want_set:
        frontier: set[str] = want_set - ack_set
        visited: set[str] = set()
        found = False
        while frontier and not found:
            batch = frontier - visited
            if not batch:
                break
            visited.update(batch)
            rows_q = await session.execute(
                select(db.MusehubCommit).where(
                    db.MusehubCommit.commit_id.in_(batch),
                    db.MusehubCommit.repo_id == repo_id,
                )
            )
            next_frontier: set[str] = set()
            for row in rows_q.scalars().all():
                for pid in (row.parent_ids or []):
                    if pid in ack_set:
                        common_base = pid
                        found = True
                        break
                    if pid not in visited:
                        next_frontier.add(pid)
                if found:
                    break
            frontier = next_frontier

    # ready = True when we know the common base or the client has no have-IDs
    # (full clone — server just sends everything from want).
    ready = common_base is not None or not have_set

    return WireNegotiateResponse(ack=ack, common_base=common_base, ready=ready)


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

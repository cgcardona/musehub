"""Wire protocol endpoints — Muse CLI push/fetch transport.

URL pattern mirrors Git's Smart HTTP protocol:

    muse remote add origin https://musehub.ai/cgcardona/muse

Three sub-paths appended to the repo URL:

    GET  /{owner}/{slug}/refs    — branch heads + domain metadata (pre-flight)
    POST /{owner}/{slug}/push    — accept a pack bundle from ``muse push``
    POST /{owner}/{slug}/fetch   — send a pack bundle to ``muse pull``

Content-addressed object CDN:

    GET  /o/{object_id}          — immutable binary blob, cacheable forever

The URL scheme is deliberately identical to how Git's Smart HTTP works:
    git remote add origin https://github.com/owner/repo
    → GET /owner/repo/info/refs?service=git-upload-pack
    → POST /owner/repo/git-upload-pack
    → POST /owner/repo/git-receive-pack

For Muse:
    muse remote add origin https://musehub.ai/owner/slug
    → GET /owner/slug/refs
    → POST /owner/slug/push
    → POST /owner/slug/fetch

These routes MUST be registered before the wildcard UI router in main.py
(/{owner}/{repo_slug}/...) so FastAPI matches the concrete third-segment
paths first.
"""
from __future__ import annotations

import asyncio
import json
import logging

import msgpack  # type: ignore[import]
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import optional_token, require_valid_token, TokenClaims
from musehub.db import musehub_models as db
from musehub.db.database import get_db as get_session
from musehub.models.wire import (
    WireFilterRequest,
    WireFetchRequest,
    WireNegotiateRequest,
    WireObjectsRequest,
    WirePresignRequest,
    WirePushRequest,
)
from musehub.rate_limits import limiter, WIRE_PUSH_LIMIT, WIRE_FETCH_LIMIT
from musehub.services import musehub_qdrant as qdrant_svc
from musehub.services.musehub_repository import get_repo_row_by_owner_slug
from musehub.services.musehub_wire import (
    wire_fetch,
    wire_filter_objects,
    wire_negotiate,
    wire_presign,
    wire_push,
    wire_push_objects,
    wire_refs,
)
from musehub.storage import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Wire Protocol"])


# ── helpers ────────────────────────────────────────────────────────────────────

async def _resolve_repo(
    session: AsyncSession,
    owner: str,
    slug: str,
) -> db.MusehubRepo:
    """Resolve owner/slug → repo row or raise 404."""
    repo = await get_repo_row_by_owner_slug(session, owner, slug)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"repo '{owner}/{slug}' not found",
        )
    return repo


async def _resolve_repo_id(
    session: AsyncSession,
    owner: str,
    slug: str,
) -> str:
    """Resolve owner/slug → repo_id or raise 404 (kept for push — push does its own auth)."""
    return (await _resolve_repo(session, owner, slug)).repo_id


def _assert_readable(repo: db.MusehubRepo, claims: TokenClaims | None) -> None:
    """Raise 404 if *repo* is private and the caller is not the owner.

    Returns a 404 (not 403) to avoid leaking that the repo exists.
    Private repos are invisible to unauthenticated callers and to users
    who are not the owner.  Collaborator access can be added here once
    a collaborators table exists.
    """
    if repo.visibility == "public":
        return
    caller_id: str | None = claims.get("sub") if claims else None
    if caller_id != repo.owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"repo not found",
        )


# ── MWP/2 helpers ──────────────────────────────────────────────────────────────

def _pack_response(data: dict[str, object], request: Request) -> Response:
    """Encode *data* as msgpack based on the client's Accept header.

    MWP clients send ``Accept: application/x-msgpack`` and always receive
    binary msgpack.  The dict may contain ``bytes`` values (e.g. object
    content) which msgpack handles natively.
    """
    accept = request.headers.get("accept", "")
    if "application/x-msgpack" in accept:
        return Response(
            content=msgpack.packb(data, use_bin_type=True),
            media_type="application/x-msgpack",
        )
    return Response(content=json.dumps(data), media_type="application/json")


def _decode_request_body(raw: bytes, content_type: str) -> dict[str, object]:
    """Decode an HTTP request body from msgpack or JSON.

    MWP/2 clients send ``Content-Type: application/x-msgpack``; older clients
    send ``application/json``.  Both are accepted so the server is backward
    compatible during the client rollout.
    """
    if "application/x-msgpack" in content_type:
        result: object = msgpack.unpackb(raw, raw=False)
        if not isinstance(result, dict):
            raise ValueError("msgpack body must be a mapping")
        return result  # type: ignore[return-value]
    return json.loads(raw)


# ── wire endpoints ─────────────────────────────────────────────────────────────

@router.get(
    "/{owner}/{slug}/refs",
    summary="Get branch heads (muse pull / muse push pre-flight)",
    response_description="Repo metadata and current branch heads",
)
@limiter.limit(WIRE_FETCH_LIMIT)
async def get_refs(
    request: Request,
    owner: str,
    slug: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return branch heads and domain metadata for a repo.

    Called by ``muse push`` and ``muse pull`` as a pre-flight to determine
    what the remote already has.  Equivalent to Git's:
    ``GET /owner/repo/info/refs?service=git-upload-pack``

    Private repos are only visible to their owner — unauthenticated callers
    receive a 404 (same response as a non-existent repo, to avoid leaking
    the existence of private repos).

    Response:
    ```json
    {
      "repo_id": "...",
      "domain": "code",
      "default_branch": "main",
      "branch_heads": {"main": "sha...", "dev": "sha..."}
    }
    ```
    """
    repo = await _resolve_repo(session, owner, slug)
    _assert_readable(repo, _claims)
    result = await wire_refs(session, repo.repo_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return Response(content=result.model_dump_json(), media_type="application/json")


@router.post(
    "/{owner}/{slug}/filter-objects",
    summary="Object dedup negotiation — return missing object IDs (MWP/2 Phase 1)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_PUSH_LIMIT)
async def filter_objects(
    request: Request,
    owner: str,
    slug: str,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return the subset of the supplied object IDs the remote does NOT hold.

    Before uploading any objects, MWP/2 clients call this endpoint with their
    full list of object IDs.  The server queries its object table in a single
    ``IN`` clause and returns only the missing subset.  The client then uploads
    only those — making incremental pushes proportional to the *change* rather
    than the full history.

    Accepts ``Content-Type: application/x-msgpack`` (MWP/2) or
    ``application/json`` (legacy).  Responds in the same format as requested
    via the ``Accept`` header.
    """
    repo = await _resolve_repo(session, owner, slug)
    raw = await request.body()
    ct = request.headers.get("content-type", "")
    data = _decode_request_body(raw, ct)
    body = WireFilterRequest.model_validate(data)
    result = await wire_filter_objects(session, repo.repo_id, body)
    return _pack_response(result.model_dump(), request)


@router.post(
    "/{owner}/{slug}/presign",
    summary="Get presigned S3/R2 URLs for large-object direct upload/download (MWP/2 Phase 3)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_PUSH_LIMIT)
async def presign_objects(
    request: Request,
    owner: str,
    slug: str,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return presigned PUT or GET URLs for direct object storage access.

    For objects above the large-object threshold (64 KB), MWP/2 clients
    request presigned URLs and upload/download directly to S3/R2, bypassing
    the API server.  When the backend is ``local://``, all IDs are returned
    in ``inline`` and the client falls back to the normal pack path.

    ``direction`` — ``"put"`` for push, ``"get"`` for pull.
    """
    repo = await _resolve_repo(session, owner, slug)
    pusher_id: str | None = claims.get("sub")
    raw = await request.body()
    ct = request.headers.get("content-type", "")
    data = _decode_request_body(raw, ct)
    body = WirePresignRequest.model_validate(data)
    try:
        result = await wire_presign(session, repo.repo_id, body, pusher_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return _pack_response(result.model_dump(), request)


@router.post(
    "/{owner}/{slug}/negotiate",
    summary="Multi-round commit negotiation (MWP/2 Phase 5)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_FETCH_LIMIT)
async def negotiate(
    request: Request,
    owner: str,
    slug: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Depth-limited ACK/NAK commit negotiation for push/pull.

    Replaces the current approach of sending every local commit ID as
    ``have``.  The client sends ≤ 256 recent commits per round; the server
    responds with which it recognises and whether the common base is found.
    The client repeats with deeper ancestors until ``ready=True``.

    This caps the negotiation payload at ≤ 256 SHA-256 hashes regardless of
    repo size — O(depth) rather than O(history).
    """
    repo = await _resolve_repo(session, owner, slug)
    _assert_readable(repo, _claims)
    raw = await request.body()
    ct = request.headers.get("content-type", "")
    data = _decode_request_body(raw, ct)
    body = WireNegotiateRequest.model_validate(data)
    try:
        result = await wire_negotiate(session, repo.repo_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return _pack_response(result.model_dump(), request)


@router.post(
    "/{owner}/{slug}/push/objects",
    summary="Pre-upload an object chunk for a large push (Phase 1 of chunked push)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_PUSH_LIMIT)
async def push_objects(
    request: Request,
    owner: str,
    slug: str,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Accept a batch of content-addressed objects before the final push (MWP msgpack)."""
    raw = await request.body()
    ct = request.headers.get("Content-Type", "")
    data = _decode_request_body(raw, ct)
    body = WireObjectsRequest.model_validate(data)
    repo_id = await _resolve_repo_id(session, owner, slug)
    pusher_id: str | None = claims.get("sub")
    try:
        result = await wire_push_objects(session, repo_id, body, pusher_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return _pack_response(result.model_dump(), request)


@router.post(
    "/{owner}/{slug}/push",
    summary="Accept a pack bundle from muse push",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_PUSH_LIMIT)
async def push(
    request: Request,
    owner: str,
    slug: str,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Ingest commits, snapshots, and objects from a ``muse push`` command (MWP msgpack)."""
    raw = await request.body()
    ct = request.headers.get("Content-Type", "")
    data = _decode_request_body(raw, ct)
    body = WirePushRequest.model_validate(data)
    repo_id = await _resolve_repo_id(session, owner, slug)
    pusher_id: str | None = claims.get("sub")
    result = await wire_push(session, repo_id, body, pusher_id)

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.message,
        )

    asyncio.create_task(_embed_push_async(repo_id, result.remote_head))

    return _pack_response(result.model_dump(), request)


@router.post(
    "/{owner}/{slug}/fetch",
    summary="Fetch a pack bundle for muse pull / muse clone",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_FETCH_LIMIT)
async def fetch(
    request: Request,
    owner: str,
    slug: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return the minimal pack bundle to satisfy a ``muse pull`` or ``muse clone`` (MWP msgpack)."""
    raw = await request.body()
    ct = request.headers.get("Content-Type", "")
    data = _decode_request_body(raw, ct)
    body = WireFetchRequest.model_validate(data)
    repo = await _resolve_repo(session, owner, slug)
    _assert_readable(repo, _claims)
    result = await wire_fetch(session, repo.repo_id, body)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return _pack_response(result.model_dump(), request)


# ── content-addressed CDN ──────────────────────────────────────────────────────

@router.get(
    "/o/{object_id:path}",
    summary="Content-addressed object CDN endpoint",
    response_description="Raw binary blob",
    tags=["Objects"],
)
async def get_object(
    object_id: str,
    repo_id: str | None = None,
    _claims: TokenClaims | None = Depends(optional_token),
) -> Response:
    """Serve a content-addressed binary object.

    Objects are immutable (ID is derived from content hash), so the response
    carries ``Cache-Control: max-age=31536000, immutable`` — safe to place
    behind CloudFront forever.
    """
    backend = get_backend()
    effective_repo_id = repo_id or "shared"
    try:
        raw = await backend.get(effective_repo_id, object_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid object path")
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="object not found")

    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{object_id}"',
        },
    )


# ── background tasks ───────────────────────────────────────────────────────────

async def _embed_push_async(repo_id: str, head_commit_id: str) -> None:
    """Fire-and-forget: embed the pushed commits in Qdrant after a push."""
    qdrant = qdrant_svc.get_qdrant()
    if qdrant is None:
        return
    try:
        logger.debug("Qdrant embed task started for repo=%s head=%s", repo_id, head_commit_id)
    except Exception as exc:
        logger.warning("Qdrant embed background task failed: %s", exc)

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
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import optional_token, require_valid_token, TokenClaims
from musehub.db import musehub_models as db
from musehub.db.database import get_db as get_session
from musehub.models.wire import WireFetchRequest, WireObjectsRequest, WirePushRequest
from musehub.rate_limits import limiter, WIRE_PUSH_LIMIT, WIRE_FETCH_LIMIT
from musehub.services import musehub_qdrant as qdrant_svc
from musehub.services.musehub_repository import get_repo_row_by_owner_slug
from musehub.services.musehub_wire import wire_fetch, wire_push, wire_push_objects, wire_refs
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
    "/{owner}/{slug}/push/objects",
    summary="Pre-upload an object chunk for a large push (Phase 1 of chunked push)",
    status_code=status.HTTP_200_OK,
)
@limiter.limit(WIRE_PUSH_LIMIT)
async def push_objects(
    request: Request,
    owner: str,
    slug: str,
    body: WireObjectsRequest,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Accept a batch of content-addressed objects before the final push.

    Large pushes are split into two phases:

    **Phase 1 — upload objects** (this endpoint, called N times):
        Client batches objects into chunks of ≤ 1 000 and POSTs each chunk
        here.  Objects are idempotent — the server skips any it already holds.

    **Phase 2 — push commits** (``POST /{owner}/{slug}/push``):
        Client sends commits + snapshots with an empty ``bundle.objects``
        list.  Because objects were already uploaded in Phase 1, the final
        push is small and fast.

    Response:
    ```json
    {"stored": 42, "skipped": 8}
    ```
    """
    repo_id = await _resolve_repo_id(session, owner, slug)
    pusher_id: str | None = claims.get("sub")
    try:
        result = await wire_push_objects(session, repo_id, body, pusher_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return Response(content=result.model_dump_json(), media_type="application/json")


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
    body: WirePushRequest,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Ingest commits, snapshots, and objects from a ``muse push`` command.

    Requires a valid Bearer token.  Equivalent to Git's:
    ``POST /owner/repo/git-receive-pack``

    Request body:
    ```json
    {
      "bundle": {"commits": [...], "snapshots": [...], "objects": [...]},
      "branch": "main",
      "force": false
    }
    ```

    Response:
    ```json
    {"ok": true, "message": "pushed 3 commit(s) to 'main'",
     "branch_heads": {...}, "remote_head": "sha..."}
    ```
    """
    repo_id = await _resolve_repo_id(session, owner, slug)
    pusher_id: str | None = claims.get("sub")
    result = await wire_push(session, repo_id, body, pusher_id)

    if not result.ok:
        # 409 Conflict for non-fast-forward (diverged history, use --force).
        # 422 would imply a malformed request body; this is a semantic conflict.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.message,
        )

    asyncio.create_task(_embed_push_async(repo_id, result.remote_head))

    return Response(content=result.model_dump_json(), media_type="application/json")


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
    body: WireFetchRequest,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return the minimal pack bundle to satisfy a ``muse pull`` or ``muse clone``.

    Equivalent to Git's:
    ``POST /owner/repo/git-upload-pack``

    Private repos require a valid Bearer token belonging to the repo owner.
    Unauthenticated callers receive a 404 (not 403) to avoid confirming the
    repo's existence.

    ``want`` — commit SHAs the client wants.
    ``have`` — commit SHAs the client already has (exclusion list).
    """
    repo = await _resolve_repo(session, owner, slug)
    _assert_readable(repo, _claims)
    result = await wire_fetch(session, repo.repo_id, body)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return Response(content=result.model_dump_json(), media_type="application/json")


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

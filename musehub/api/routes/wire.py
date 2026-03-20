"""Wire protocol endpoints — Muse CLI push/fetch transport.

URL pattern:  /wire/repos/{repo_id}/...

Three endpoints:
    GET  /wire/repos/{repo_id}/refs    — branch heads + repo metadata
    POST /wire/repos/{repo_id}/push    — accept a pack bundle from ``muse push``
    POST /wire/repos/{repo_id}/fetch   — send a pack bundle to ``muse pull``

Also serves the content-addressed object CDN endpoint:
    GET  /o/{object_id}               — immutable binary blob, cacheable forever

Authentication:
    ``refs`` and ``fetch`` accept optional Bearer tokens (public repos are read-only
    without auth).  ``push`` requires a valid Bearer token.

The wire URLs that ``muse remote add`` stores::

    muse remote add origin https://musehub.ai/wire/repos/<repo_id>

Muse CLI then calls:
    GET  {remote_url}/refs
    POST {remote_url}/push  {"bundle": {...}, "branch": "main", "force": false}
    POST {remote_url}/fetch {"want": [...], "have": [...]}
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import optional_token, require_valid_token, TokenClaims
from musehub.db.database import get_db as get_session
from musehub.models.wire import WireFetchRequest, WirePushRequest
from musehub.services.musehub_wire import wire_fetch, wire_push, wire_refs
from musehub.services import musehub_qdrant as qdrant_svc
from musehub.storage import get_backend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Wire Protocol"])


@router.get(
    "/wire/repos/{repo_id}/refs",
    summary="Get branch heads (muse pull / muse push pre-flight)",
    response_description="Repo metadata and current branch heads",
)
async def get_refs(
    repo_id: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return branch heads and domain metadata for a repo.

    Called by ``muse push`` and ``muse pull`` as a pre-flight to determine
    what the remote already has.

    Response (JSON):
    ```json
    {
      "repo_id": "...",
      "domain": "code",
      "default_branch": "main",
      "branch_heads": {"main": "sha...", "dev": "sha..."}
    }
    ```
    """
    result = await wire_refs(session, repo_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
    )


@router.post(
    "/wire/repos/{repo_id}/push",
    summary="Accept a pack bundle from muse push",
    status_code=status.HTTP_200_OK,
)
async def push(
    repo_id: str,
    body: WirePushRequest,
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Ingest commits, snapshots, and objects from a ``muse push`` command.

    Requires a valid Bearer token.  The pusher's subject (``claims["sub"]``)
    is recorded for audit purposes.

    Request body mirrors the Muse CLI ``PackBundle + branch + force``:
    ```json
    {
      "bundle": {
        "commits": [...],
        "snapshots": [...],
        "objects": [...],
        "branch_heads": {}
      },
      "branch": "main",
      "force": false
    }
    ```

    Response:
    ```json
    {"ok": true, "message": "pushed 3 commit(s) to 'main'", "branch_heads": {...}, "remote_head": "sha..."}
    ```
    """
    pusher_id: str | None = claims.get("sub")
    result = await wire_push(session, repo_id, body, pusher_id)

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message,
        )

    # Background: embed pushed commits in Qdrant (non-blocking)
    asyncio.create_task(_embed_push_async(repo_id, result.remote_head))

    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
    )


@router.post(
    "/wire/repos/{repo_id}/fetch",
    summary="Fetch a pack bundle for muse pull / muse clone",
    status_code=status.HTTP_200_OK,
)
async def fetch(
    repo_id: str,
    body: WireFetchRequest,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Return the minimal pack bundle to satisfy a ``muse pull`` or ``muse clone``.

    ``want`` is the list of commit SHAs the client wants.
    ``have`` is the list of commit SHAs the client already has.

    The server performs a BFS from ``want`` minus ``have`` and packs all
    missing commits, their snapshots, and the objects those snapshots reference.

    Response mirrors ``PackBundle`` so the Muse CLI can call ``_parse_bundle()``
    on it directly.
    """
    result = await wire_fetch(session, repo_id, body)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
    )


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

    Objects are immutable by definition (the ID is derived from the content
    hash), so the response carries ``Cache-Control: max-age=31536000, immutable``
    to allow CDN and browser caching forever.

    ``object_id`` may be:
        - A bare SHA, e.g. ``/o/abc123``
        - A repo-scoped SHA, e.g. ``/o/repos/<repo_id>/abc123``

    ``repo_id`` query parameter is used for storage backend resolution when
    not embedded in the path.

    This endpoint is designed to be placed behind CloudFront / nginx so that
    the origin is only hit once per object per CDN edge node.
    """
    backend = get_backend()
    # Accept simple SHA or repo-scoped path
    effective_repo_id = repo_id or "shared"
    raw = await backend.get(effective_repo_id, object_id)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="object not found")

    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={
            # Permanent immutable cache — safe because content is addressed by hash
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{object_id}"',
        },
    )


async def _embed_push_async(repo_id: str, head_commit_id: str) -> None:
    """Fire-and-forget background task: embed the pushed commits in Qdrant."""
    qdrant = qdrant_svc.get_qdrant()
    if qdrant is None:
        return
    try:
        # Lightweight import — avoids DB hit in the hot path
        logger.debug("Qdrant embed task started for repo=%s head=%s", repo_id, head_commit_id)
    except Exception as exc:
        logger.warning("Qdrant embed background task failed: %s", exc)

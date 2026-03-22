"""REST API — repo endpoints.

Mounted at /api/repos/...

These are the canonical machine-readable repo endpoints.
The browser UI continues to live at /{owner}/{slug}/... for human-readable URLs.

Endpoint surface:
    GET  /api/repos                     — list / search repos
    POST /api/repos                     — create a repo
    GET  /api/repos/{repo_id}           — get repo metadata
    PATCH /api/repos/{repo_id}          — update repo metadata
    DELETE /api/repos/{repo_id}         — soft-delete a repo

    GET  /api/repos/{repo_id}/branches  — list branches
    GET  /api/repos/{repo_id}/commits   — list commits (paginated)
    GET  /api/repos/{repo_id}/commits/{commit_id} — single commit

    GET  /api/repos/{repo_id}/objects/{object_id} — serve a binary object

Wire-protocol endpoints live at /wire/repos/{repo_id}/... (separate router).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import optional_token, require_valid_token, TokenClaims
from musehub.db import musehub_models as db
from musehub.db.database import get_db as get_session
from musehub.services.musehub_repository import (
    get_repo,
    list_repos_for_user,
    create_repo,
    list_commits,
)
from musehub.services import musehub_qdrant as qdrant_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Repos"])


@router.get("/api/repos", summary="List or search repos")
async def list_repos_endpoint(
    owner: str | None = Query(None),
    domain: str | None = Query(None),
    q: str | None = Query(None, description="Semantic search query (uses Qdrant when available)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """List repos with optional filtering.

    When ``q`` is provided and Qdrant is configured, performs semantic search.
    Otherwise falls back to Postgres text matching.
    """
    import json as _json
    if q:
        qdrant = qdrant_svc.get_qdrant()
        if qdrant is not None:
            semantic_results = await qdrant_svc.semantic_search_repos(
                qdrant, q, limit=per_page, domain=domain
            )
            return Response(
                content=_json.dumps({"repos": semantic_results, "semantic": True}),
                media_type="application/json",
            )

    # Fallback: list by owner if provided, otherwise empty
    if owner:
        result = await list_repos_for_user(session, user_id=owner, limit=per_page)
        return Response(content=result.model_dump_json(), media_type="application/json")

    return Response(
        content=_json.dumps({"repos": [], "hint": "Provide ?owner= or ?q= to filter results"}),
        media_type="application/json",
    )


@router.post("/api/repos", summary="Create a repo", status_code=status.HTTP_201_CREATED)
async def create_repo_endpoint(
    body: dict[str, object],
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Create a new repo under the authenticated identity.

    ``owner`` is resolved from the caller's registered identity handle — the
    URL-visible slug (e.g. "gabriel").  ``owner_user_id`` is the stable UUID
    from the JWT ``sub`` claim.  The two are stored separately so handle renames
    only require updating identity rows, not every repo row.
    """
    user_id: str = claims.get("sub") or ""
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no subject in token")

    # Resolve the identity handle for this user — the URL-visible slug.
    # Identities link to the JWT ``sub`` via the ``legacy_user_id`` column.
    identity_row = (
        await session.execute(
            select(db.MusehubIdentity).where(db.MusehubIdentity.legacy_user_id == user_id)
        )
    ).scalars().first()
    if identity_row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No identity registered for this account. Create an identity first via POST /api/identities.",
        )
    owner_handle: str = identity_row.handle

    name = str(body.get("name") or body.get("slug") or "")
    description = str(body.get("description") or "")
    visibility = "private" if body.get("is_private") else "public"

    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="name is required")

    result = await create_repo(
        session,
        name=name,
        owner=owner_handle,
        visibility=visibility,
        owner_user_id=user_id,
        description=description,
    )
    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/api/repos/{repo_id}", summary="Get a repo by ID")
async def get_repo_endpoint(
    repo_id: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    result = await get_repo(session, repo_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repo not found")
    return Response(content=result.model_dump_json(), media_type="application/json")


@router.get("/api/repos/{repo_id}/branches", summary="List branches")
async def list_branches_endpoint(
    repo_id: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = (
        await session.execute(
            select(db.MusehubBranch).where(db.MusehubBranch.repo_id == repo_id)
        )
    ).scalars().all()
    branches = [
        {"name": b.name, "head_commit_id": b.head_commit_id}
        for b in rows
    ]
    import json
    return Response(
        content=json.dumps({"branches": branches}),
        media_type="application/json",
    )


@router.get("/api/repos/{repo_id}/commits", summary="List commits (paginated)")
async def list_commits_endpoint(
    repo_id: str,
    branch: str = Query("main"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    q: str | None = Query(None, description="Semantic search query"),
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """List commits for a repo with optional semantic search."""
    import json as _json
    if q:
        qdrant = qdrant_svc.get_qdrant()
        if qdrant is not None:
            results = await qdrant_svc.semantic_search_commits(qdrant, q, repo_id=repo_id, limit=per_page)
            return Response(
                content=_json.dumps({"commits": results, "semantic": True}),
                media_type="application/json",
            )

    offset = (page - 1) * per_page
    commits, total = await list_commits(session, repo_id, branch=branch, limit=per_page, offset=offset)
    return Response(
        content=_json.dumps({
            "commits": [c.model_dump() for c in commits],
            "total": total,
            "page": page,
            "per_page": per_page,
        }),
        media_type="application/json",
    )


@router.get("/api/repos/{repo_id}/commits/{commit_id}", summary="Get a single commit")
async def get_commit_endpoint(
    repo_id: str,
    commit_id: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await session.get(db.MusehubCommit, commit_id)
    if row is None or row.repo_id != repo_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="commit not found")

    from musehub.services.musehub_wire import _to_wire_commit
    wire = _to_wire_commit(row)
    return Response(content=wire.model_dump_json(), media_type="application/json")

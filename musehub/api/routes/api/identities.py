"""REST API — identity endpoints.

Mounted at /api/identities/...

An identity is any actor in MuseHub: human, agent, or org.
This is the v2 replacement for /api/v1/users/... which was human-only.

Endpoint surface:
    GET  /api/identities                — list identities (filterable by type)
    GET  /api/identities/{handle}       — get identity by handle
    POST /api/identities                — register a new identity
    PATCH /api/identities/{handle}      — update own identity
    DELETE /api/identities/{handle}     — soft-delete identity

    GET  /api/identities/{handle}/repos — repos belonging to this identity
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import optional_token, require_valid_token, TokenClaims
from musehub.db import musehub_models as db
from musehub.db.database import get_db as get_session
from musehub.rate_limits import limiter, AUTH_LIMIT

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Identities"])


@router.get("/api/identities", summary="List identities")
async def list_identities(
    identity_type: str | None = Query(None, description="Filter by type: human | agent | org"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    stmt = select(db.MusehubIdentity).where(db.MusehubIdentity.deleted_at.is_(None))
    if identity_type:
        stmt = stmt.where(db.MusehubIdentity.identity_type == identity_type)
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = (await session.execute(stmt)).scalars().all()
    import json
    return Response(
        content=json.dumps({"identities": [_row_to_dict(r) for r in rows]}),
        media_type="application/json",
    )


@router.post("/api/identities", summary="Register a new identity", status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_LIMIT)
async def create_identity(
    request: Request,
    body: dict[str, object],
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Register a new human, agent, or org identity.

    The ``handle`` must be unique across all identity types.
    Agents must supply ``agent_model``; humans may supply ``email``.
    """
    handle = str(body.get("handle") or "").strip()
    if not handle:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="handle is required")

    identity_type = body.get("identity_type", "human")
    if identity_type not in ("human", "agent", "org"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="identity_type must be human | agent | org",
        )

    # Check handle uniqueness
    existing = (
        await session.execute(
            select(db.MusehubIdentity).where(db.MusehubIdentity.handle == handle)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="handle already taken")

    row = db.MusehubIdentity(
        id=str(uuid.uuid4()),
        handle=handle,
        identity_type=identity_type,
        display_name=body.get("display_name"),
        bio=body.get("bio"),
        avatar_url=body.get("avatar_url"),
        website_url=body.get("website_url"),
        email=body.get("email"),
        agent_model=body.get("agent_model"),
        agent_capabilities=body.get("agent_capabilities", []),
        legacy_user_id=claims.get("sub"),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    import json
    return Response(
        content=json.dumps(_row_to_dict(row)),
        media_type="application/json",
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/api/identities/{handle}", summary="Get identity by handle")
async def get_identity(
    handle: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _get_or_404(session, handle)
    import json
    return Response(content=json.dumps(_row_to_dict(row)), media_type="application/json")


@router.patch("/api/identities/{handle}", summary="Update own identity")
async def update_identity(
    handle: str,
    body: dict[str, object],
    claims: TokenClaims = Depends(require_valid_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    row = await _get_or_404(session, handle)
    sub = claims.get("sub") or ""
    if row.legacy_user_id != sub and claims.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your identity")

    for field in ("display_name", "bio", "avatar_url", "website_url", "email", "agent_model"):
        if field in body:
            setattr(row, field, body[field])
    if "agent_capabilities" in body:
        caps = body["agent_capabilities"]
        row.agent_capabilities = list(caps) if isinstance(caps, list) else []

    await session.commit()
    await session.refresh(row)
    import json
    return Response(content=json.dumps(_row_to_dict(row)), media_type="application/json")


@router.get("/api/identities/{handle}/repos", summary="List repos owned by this identity")
async def list_identity_repos(
    handle: str,
    _claims: TokenClaims | None = Depends(optional_token),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Repos are stored with owner = handle (or user_id in legacy)
    from sqlalchemy import or_
    stmt = (
        select(db.MusehubRepo)
        .where(
            or_(db.MusehubRepo.owner == handle),
            db.MusehubRepo.deleted_at.is_(None),
        )
        .order_by(db.MusehubRepo.created_at.desc())
        .limit(100)
    )
    rows = (await session.execute(stmt)).scalars().all()
    import json
    repos = [
        {
            "repo_id": r.repo_id,
            "owner": r.owner,
            "slug": r.slug,
            "description": r.description,
            "visibility": r.visibility,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return Response(content=json.dumps({"repos": repos}), media_type="application/json")


# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_or_404(session: AsyncSession, handle: str) -> db.MusehubIdentity:
    row = (
        await session.execute(
            select(db.MusehubIdentity).where(
                db.MusehubIdentity.handle == handle,
                db.MusehubIdentity.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="identity not found")
    return row


def _row_to_dict(row: db.MusehubIdentity) -> dict[str, object]:
    return {
        "id": row.id,
        "handle": row.handle,
        "identity_type": row.identity_type,
        "display_name": row.display_name,
        "bio": row.bio,
        "avatar_url": row.avatar_url,
        "website_url": row.website_url,
        "email": row.email,
        "agent_model": row.agent_model,
        "agent_capabilities": row.agent_capabilities or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }

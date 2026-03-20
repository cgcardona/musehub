"""Domain plugin registry API endpoints.

Routes:
  GET  /api/v1/domains                              list + search registered domains
  POST /api/v1/domains                              register a new domain (auth required)
  GET  /api/v1/domains/@{author_slug}/{slug}        domain detail + capabilities
  GET  /api/v1/domains/@{author_slug}/{slug}/repos  public repos using this domain

The ``@`` prefix in URL paths is handled by encoding it in the route path
directly: ``/domains/@{author_slug}/{slug}``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import TokenClaims, require_valid_token
from musehub.db import get_db
from musehub.services import musehub_domains

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/domains", tags=["Domains"])


# ── Request models ────────────────────────────────────────────────────────────


class RegisterDomainRequest(BaseModel):
    """Body for registering a new domain plugin."""

    author_slug: str
    """URL-safe author handle — forms the @author_slug part of the scoped ID."""

    slug: str
    """URL-safe domain name — forms the /slug part of the scoped ID."""

    display_name: str
    """Human-readable domain name, e.g. "Genomics"."""

    description: str = ""
    """Short description of what state space this domain versions."""

    capabilities: dict
    """Domain capabilities manifest — dimensions, viewer_type, artifact_types, etc."""

    viewer_type: str = "generic"
    """Primary viewer type: 'piano_roll' | 'symbol_graph' | 'sequence_viewer' | 'generic'."""

    version: str = "1.0.0"
    """Semver version string for this domain manifest."""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List registered Muse domain plugins",
    operation_id="listDomains",
)
async def list_domains(
    q: str | None = Query(None, description="Search by name, slug, or description"),
    verified: bool = Query(False, description="Only return MuseHub-verified domains"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return a paginated list of registered Muse domain plugins.

    Domains are the foundation of the Muse paradigm — each one defines a unique
    state space and the six plugin interfaces Muse uses to version it. Agents
    should call this endpoint to discover available domains before creating
    repositories or understanding what insight dimensions are available.
    """
    result = await musehub_domains.list_domains(
        db,
        query=q,
        verified_only=verified,
        page=page,
        page_size=page_size,
    )
    return JSONResponse({
        "domains": [
            {
                "domain_id": d.domain_id,
                "scoped_id": d.scoped_id,
                "author_slug": d.author_slug,
                "slug": d.slug,
                "display_name": d.display_name,
                "description": d.description,
                "version": d.version,
                "manifest_hash": d.manifest_hash,
                "viewer_type": d.viewer_type,
                "install_count": d.install_count,
                "is_verified": d.is_verified,
                "is_deprecated": d.is_deprecated,
                "dimension_count": len(d.capabilities.get("dimensions", [])),
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in result.domains
        ],
        "total": result.total,
        "page": page,
        "page_size": page_size,
    })


@router.post(
    "",
    summary="Register a new Muse domain plugin",
    operation_id="registerDomain",
    status_code=http_status.HTTP_201_CREATED,
)
async def register_domain(
    body: RegisterDomainRequest,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims = Depends(require_valid_token),
) -> JSONResponse:
    """Register a new Muse domain plugin in the MuseHub registry.

    The domain becomes discoverable by all agents and humans via
    ``musehub_list_domains`` and the ``/domains`` browse page. The scoped
    identifier ``@{author_slug}/{slug}`` must be unique.

    The ``capabilities`` object should follow the Muse domain schema:
    - ``dimensions``: list of ``{name, description}`` objects
    - ``viewer_type``: primary viewer identifier
    - ``artifact_types``: list of MIME types the domain produces
    - ``merge_semantics``: ``"ot"`` | ``"crdt"`` | ``"three_way"``
    - ``supported_commands``: list of ``muse`` CLI commands
    """
    author_user_id: str = claims.get("sub") or ""

    try:
        domain = await musehub_domains.create_domain(
            db,
            author_user_id=author_user_id,
            author_slug=body.author_slug,
            slug=body.slug,
            display_name=body.display_name,
            description=body.description,
            capabilities=body.capabilities,
            viewer_type=body.viewer_type,
            version=body.version,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=f"Domain '@{body.author_slug}/{body.slug}' is already registered.",
        )

    logger.info(
        "Domain registered: @%s/%s (id=%s)",
        domain.author_slug,
        domain.slug,
        domain.domain_id,
    )
    return JSONResponse(
        {
            "domain_id": domain.domain_id,
            "scoped_id": domain.scoped_id,
            "manifest_hash": domain.manifest_hash,
        },
        status_code=http_status.HTTP_201_CREATED,
    )


@router.get(
    "/@{author_slug}/{slug}",
    summary="Get a domain plugin by scoped ID",
    operation_id="getDomain",
)
async def get_domain(
    author_slug: str,
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return full manifest and capabilities for a domain plugin.

    Agents should call this to understand what insight dimensions a domain
    supports, what viewer type to expect, and what CLI commands are available.
    The ``manifest_hash`` can be used to pin to a specific version.
    """
    domain = await musehub_domains.get_domain_by_scoped_id(db, author_slug, slug)
    if domain is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Domain '@{author_slug}/{slug}' not found.",
        )
    return JSONResponse({
        "domain_id": domain.domain_id,
        "scoped_id": domain.scoped_id,
        "author_slug": domain.author_slug,
        "slug": domain.slug,
        "display_name": domain.display_name,
        "description": domain.description,
        "version": domain.version,
        "manifest_hash": domain.manifest_hash,
        "capabilities": domain.capabilities,
        "viewer_type": domain.viewer_type,
        "install_count": domain.install_count,
        "is_verified": domain.is_verified,
        "is_deprecated": domain.is_deprecated,
        "created_at": domain.created_at.isoformat() if domain.created_at else None,
        "updated_at": domain.updated_at.isoformat() if domain.updated_at else None,
    })


@router.get(
    "/@{author_slug}/{slug}/repos",
    summary="List public repos using a domain plugin",
    operation_id="listDomainRepos",
)
async def list_domain_repos(
    author_slug: str,
    slug: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return public repositories that use the specified domain plugin.

    Useful for agents discovering real-world examples of a domain in use,
    or for the domain detail page to show community adoption.
    """
    domain = await musehub_domains.get_domain_by_scoped_id(db, author_slug, slug)
    if domain is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Domain '@{author_slug}/{slug}' not found.",
        )

    result = await musehub_domains.list_repos_for_domain(
        db, domain.domain_id, page=page, page_size=page_size
    )
    return JSONResponse({
        "domain_id": result.domain_id,
        "scoped_id": result.scoped_id,
        "repos": result.repos,
        "total": result.total,
        "page": page,
        "page_size": page_size,
    })

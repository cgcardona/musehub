"""Domain registry browser UI routes.

Serves:
  GET /domains                    — browse/search all registered domain plugins
  GET /domains/@{author}/{slug}   — domain detail, capabilities, repos using it

Both routes support content negotiation:
  - Browsers receive the full HTML page.
  - Agents send ``Accept: application/json`` or ``?format=json`` and receive
    structured JSON — the same data, same URL, no separate endpoint needed.
  - The canonical machine-readable API is at ``/api/v1/domains/…`` (REST) and
    via the ``musehub_get_domain`` / ``musehub_list_domains`` MCP tools.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from musehub.api.routes.musehub._templates import templates as _templates
from musehub.api.routes.musehub.json_alternate import add_json_available_header
from musehub.api.routes.musehub.ui_new_repo import licenses_for_viewer_type
from musehub.db import get_db
from musehub.services import musehub_domains

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["musehub-ui-domains"])

# Canonical REST API base — used in Link headers and JSON meta.api fields.
_API_BASE = "/api/v1"


def _wants_json(request: Request, format_param: str | None) -> bool:
    if format_param == "json":
        return True
    return "application/json" in request.headers.get("accept", "")


@router.get(
    "/domains",
    response_class=HTMLResponse,
    summary="Browse registered Muse domain plugins",
    operation_id="domainsPage",
)
async def domains_page(
    request: Request,
    q: str | None = Query(None, description="Search query"),
    verified: bool = Query(False, description="Only show verified domains"),
    format: str | None = Query(None, description="Response format: json | html"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Browse and discover registered Muse domain plugins.

    Supports content negotiation — agents send ``Accept: application/json`` or
    ``?format=json`` to receive the domain list as structured JSON without HTML.
    The canonical JSON endpoint is ``GET /api/v1/domains``.
    """
    result = await musehub_domains.list_domains(
        db,
        query=q,
        verified_only=verified,
        page=1,
        page_size=50,
    )
    domain_list = [
        {
            "domain_id": d.domain_id,
            "scoped_id": d.scoped_id,
            "author_slug": d.author_slug,
            "slug": d.slug,
            "display_name": d.display_name,
            "description": d.description,
            "viewer_type": d.viewer_type,
            "install_count": d.install_count,
            "is_verified": d.is_verified,
            "dimension_count": len(d.capabilities.get("dimensions", [])),
            "artifact_types": d.capabilities.get("artifact_types", []),
            "merge_semantics": d.capabilities.get("merge_semantics", ""),
        }
        for d in result.domains
    ]

    if _wants_json(request, format):
        return JSONResponse(
            content={
                "domains": domain_list,
                "total": result.total,
                "meta": {
                    "url": str(request.url),
                    "api": f"{_API_BASE}/domains",
                    "mcp_tool": "musehub_list_domains",
                    "mcp_resource": "muse://domains",
                },
            }
        )

    ctx: dict[str, object] = {
        "title": "Domains",
        "current_page": "domains",
        "domains": domain_list,
        "total": result.total,
        "search_query": q or "",
        "verified_only": verified,
    }
    resp = _templates.TemplateResponse(request, "musehub/pages/domains.html", ctx)
    resp.headers["Link"] = f'<{_API_BASE}/domains>; rel="alternate"; type="application/json"'
    return add_json_available_header(resp, request)


@router.get(
    "/domains/@{author_slug}/{slug}",
    response_class=HTMLResponse,
    summary="Domain plugin detail page",
    operation_id="domainDetailPage",
)
async def domain_detail_page(
    request: Request,
    author_slug: str,
    slug: str,
    format: str | None = Query(None, description="Response format: json | html"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Display full manifest, capabilities, and repos for a domain plugin.

    Supports content negotiation — agents send ``Accept: application/json`` or
    ``?format=json`` to receive the full domain manifest as structured JSON.
    The canonical JSON endpoint is ``GET /api/v1/domains/@{author}/{slug}``.
    """
    domain = await musehub_domains.get_domain_by_scoped_id(db, author_slug, slug)
    if domain is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Domain @{author_slug}/{slug} not found.")

    repos_result = await musehub_domains.list_repos_for_domain(
        db, domain.domain_id, page=1, page_size=12
    )

    api_url = f"{_API_BASE}/domains/{domain.scoped_id}"

    domain_data: dict[str, object] = {
        "domain_id": domain.domain_id,
        "scoped_id": domain.scoped_id,
        "author_slug": domain.author_slug,
        "slug": domain.slug,
        "display_name": domain.display_name,
        "description": domain.description,
        "version": domain.version,
        "manifest_hash": domain.manifest_hash,
        "viewer_type": domain.viewer_type,
        "install_count": domain.install_count,
        "is_verified": domain.is_verified,
        "is_deprecated": domain.is_deprecated,
        "dimensions": domain.capabilities.get("dimensions", []),
        "artifact_types": domain.capabilities.get("artifact_types", []),
        "merge_semantics": domain.capabilities.get("merge_semantics", ""),
        "supported_commands": domain.capabilities.get("supported_commands", []),
        "created_at": domain.created_at.isoformat() if domain.created_at else None,
    }

    if _wants_json(request, format):
        return JSONResponse(
            content={
                "domain": domain_data,
                "repos": repos_result.repos,
                "repos_total": repos_result.total,
                "meta": {
                    "url": str(request.url),
                    "api": api_url,
                    "mcp_tool": "musehub_get_domain",
                    "mcp_resource": f"muse://domains/{author_slug}/{slug}",
                },
            }
        )

    ctx: dict[str, object] = {
        "title": f"{domain.display_name} domain",
        "current_page": "domains",
        "domain": domain_data,
        "repos": repos_result.repos,
        "repos_total": repos_result.total,
    }
    resp = _templates.TemplateResponse(request, "musehub/pages/domain_detail.html", ctx)
    resp.headers["Link"] = f'<{api_url}>; rel="alternate"; type="application/json"'
    return add_json_available_header(resp, request)


@router.get(
    "/domains/@{author_slug}/{slug}/new",
    response_class=HTMLResponse,
    summary="Create a new repository within a domain context",
    operation_id="newRepoDomainPage",
)
async def new_repo_domain_page(
    request: Request,
    author_slug: str,
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the domain-scoped repository creation wizard.

    The domain is always known here, so the form locks the domain display,
    pre-selects the appropriate license set (code vs. music vs. generic),
    and removes the domain selector dropdown.
    """
    from fastapi import HTTPException

    domain = await musehub_domains.get_domain_by_scoped_id(db, author_slug, slug)
    if domain is None:
        raise HTTPException(status_code=404, detail=f"Domain @{author_slug}/{slug} not found.")

    domain_data: dict[str, object] = {
        "scoped_id": domain.scoped_id,
        "author_slug": domain.author_slug,
        "slug": domain.slug,
        "display_name": domain.display_name,
        "viewer_type": domain.viewer_type,
        "dimension_count": len(domain.capabilities.get("dimensions", [])),
    }

    ctx: dict[str, object] = {
        "title": f"New {domain.display_name} repository",
        "current_page": "domains",
        "domain": domain_data,
        "licenses": licenses_for_viewer_type(domain.viewer_type),
    }
    return _templates.TemplateResponse(request, "musehub/pages/new_repo.html", ctx)

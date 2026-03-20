"""MuseHub new repo creation wizard — SSR migration (#562).

Serves the repository creation wizard at /new.

Routes:
  GET  /new        — SSR creation wizard form (Jinja2 template)
  POST /new        — create repo (JSON body, auth required), returns
                                redirect URL for JS navigation
  GET  /new/check  — name availability check; returns HTML fragment
                                when requested by HTMX, JSON otherwise

Auth contract:
- GET renders the SSR form without requiring a JWT. The form fields are
  rendered server-side; client JS (Alpine.js) handles the visibility toggle
  and topics tag input only.
- POST requires a valid JWT in the Authorization header. Returns
  ``{"redirect": "/{owner}/{slug}?welcome=1"}`` on success so the
  JS can navigate; returns 409 on slug collision.
- GET /new/check is unauthenticated — slug availability is not secret.
  When called by HTMX (``HX-Request: true``), returns an HTML fragment
  (``<span>`` with availability text). Otherwise returns JSON for scripts/agents.

The POST handler delegates all persistence to
``musehub.services.musehub_repository.create_repo``, keeping this handler
thin per the routes-as-thin-adapters architecture rule.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 (used in route dependency)
from starlette.responses import RedirectResponse, Response

from musehub.api.routes.musehub._templates import templates as _templates
from musehub.api.routes.musehub.htmx_helpers import is_htmx
from musehub.auth.dependencies import TokenClaims, require_valid_token
from musehub.db import get_db
from musehub.models.musehub import CreateRepoRequest
from musehub.services import musehub_repository, musehub_domains

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["musehub-ui-new-repo"])

# License sets by domain type — code domains use OSS licenses, music/MIDI use
# Creative Commons. The generic set is a union used as a fallback.
_LICENSES_CODE: list[tuple[str, str]] = [
    ("", "No license"),
    ("MIT", "MIT License"),
    ("Apache-2.0", "Apache 2.0"),
    ("GPL-3.0", "GNU GPL v3"),
    ("AGPL-3.0", "AGPL v3"),
    ("BSD-2-Clause", "BSD 2-Clause"),
]

_LICENSES_MUSIC: list[tuple[str, str]] = [
    ("", "No license"),
    ("CC0", "CC0 — Public Domain"),
    ("CC BY", "CC BY — Attribution"),
    ("CC BY-SA", "CC BY-SA — ShareAlike"),
    ("CC BY-NC", "CC BY-NC — NonCommercial"),
    ("ARR", "All Rights Reserved"),
]

_LICENSES_GENERIC: list[tuple[str, str]] = [
    ("", "No license"),
    ("MIT", "MIT License"),
    ("Apache-2.0", "Apache 2.0"),
    ("GPL-3.0", "GNU GPL v3"),
    ("CC0", "CC0 — Public Domain"),
    ("CC BY", "CC BY — Attribution"),
    ("CC BY-SA", "CC BY-SA — ShareAlike"),
    ("ARR", "All Rights Reserved"),
]


def licenses_for_viewer_type(viewer_type: str) -> list[tuple[str, str]]:
    """Return the appropriate license list for a given domain viewer type."""
    if viewer_type == "symbol_graph":
        return _LICENSES_CODE
    if viewer_type == "piano_roll":
        return _LICENSES_MUSIC
    return _LICENSES_GENERIC


@router.get(
    "/new",
    summary="Redirect to domain browser — repos require a domain context",
    operation_id="newRepoRedirect",
)
async def new_repo_redirect() -> Response:
    """Every repository must belong to a domain.

    Navigate to a domain's detail page and use the 'Create repository' button
    to start the scoped creation wizard at /domains/@{author}/{slug}/new.
    """
    return RedirectResponse(url="/domains", status_code=302)


@router.post(
    "/new",
    summary="Create a new repository via the wizard",
    operation_id="createRepoWizard",
    status_code=http_status.HTTP_201_CREATED,
)
async def create_repo_wizard(
    body: CreateRepoRequest,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims = Depends(require_valid_token),
) -> JSONResponse:
    """Create a new repo from the wizard form submission and return the redirect URL.

    Why POST + JSON instead of a browser form POST: all MuseHub UI pages use
    JavaScript to call authenticated API endpoints. The JWT lives in
    localStorage, not in a cookie or form field, so keeping the submission
    client-side avoids requiring a hidden token field or session cookie.

    On success, returns 201 + ``{"redirect": "/{owner}/{slug}?welcome=1"}``
    so the client-side JS can navigate to the new repo. On slug collision,
    returns 409 so the wizard can surface a friendly error without a full reload.
    """
    owner_user_id: str = claims.get("sub") or ""
    try:
        repo = await musehub_repository.create_repo(
            db,
            name=body.name,
            owner=body.owner,
            visibility=body.visibility,
            owner_user_id=owner_user_id,
            description=body.description,
            tags=body.tags,
            key_signature=body.key_signature,
            tempo_bpm=body.tempo_bpm,
            license=body.license,
            topics=body.topics,
            initialize=body.initialize,
            default_branch=body.default_branch,
            template_repo_id=body.template_repo_id,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="A repository with this owner and name already exists.",
        )
    redirect_url = f"/{repo.owner}/{repo.slug}?welcome=1"
    logger.info(
        "✅ New repo created via wizard: %s/%s (id=%s)",
        repo.owner,
        repo.slug,
        repo.repo_id,
    )
    return JSONResponse(
        {
            "redirect": redirect_url,
            "repoId": repo.repo_id,
            "slug": repo.slug,
            "owner": repo.owner,
        },
        status_code=http_status.HTTP_201_CREATED,
    )


@router.get(
    "/new/check",
    summary="Check repo name availability",
    operation_id="checkRepoNameAvailable",
)
async def check_repo_name(
    request: Request,
    owner: str = Query(..., description="Owner username to check under"),
    slug: str = Query(..., description="URL-safe slug derived from the repo name"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return whether a given owner+slug pair is available.

    When called by HTMX (``HX-Request: true``), returns a bare HTML
    ``<span>`` fragment that HTMX swaps into the ``#name-check`` target
    element — no JavaScript needed for the availability indicator.

    When called without the HTMX header (scripts, agents, legacy JS),
    returns JSON: ``{"available": true}`` or ``{"available": false}``.

    No auth required — slug availability is not secret information.
    """
    existing = await musehub_repository.get_repo_by_owner_slug(db, owner, slug)
    available = existing is None
    if is_htmx(request):
        return _templates.TemplateResponse(
            request,
            "musehub/fragments/slug_check.html",
            {"available": available},
        )
    return JSONResponse({"available": available})

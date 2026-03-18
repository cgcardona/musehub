"""MuseHub web UI route handlers.

Serves browser-readable HTML pages for navigating a MuseHub repo --
analogous to GitHub's repository browser but for music projects.

All pages are rendered via Jinja2 templates stored in
``musehub/templates/musehub/``.  Route handlers resolve server-side data
(repo_id, owner, slug) and pass a minimal context dict to the template
engine; all HTML, CSS, and JavaScript lives in the template files, not here.

Endpoint summary (fixed-path):
  GET /search                                  -- global cross-repo search page
  GET /explore                                 -- public repo discovery grid
  GET /trending                                -- repos sorted by stars
  GET /{username}                              -- public user profile

Endpoint summary (repo-scoped):
  GET /{owner}/{repo_slug}                           -- repo landing page
  GET /{owner}/{repo_slug}/commits                   -- paginated commit list with branch filter
  GET /{owner}/{repo_slug}/commits/{commit_id}       -- commit detail + artifacts
  GET /{owner}/{repo_slug}/commits/{commit_id}/diff  -- musical diff view
  GET /{owner}/{repo_slug}/graph                     -- interactive DAG commit graph
  GET /{owner}/{repo_slug}/pulls                     -- pull request list
  GET /{owner}/{repo_slug}/pulls/{pr_id}             -- PR detail with musical diff (radar, piano roll, audio A/B)
  GET /{owner}/{repo_slug}/issues                    -- issue list
  GET /{owner}/{repo_slug}/issues/{number}           -- issue detail + close button
  GET /{owner}/{repo_slug}/context/{ref}             -- AI context viewer
  GET /{owner}/{repo_slug}/credits                   -- dynamic credits (liner notes)
  GET /{owner}/{repo_slug}/embed/{ref}               -- iframe-safe audio player
  GET /{owner}/{repo_slug}/search                    -- in-repo search (4 modes)
  GET /{owner}/{repo_slug}/compare/{base}...{head}   -- multi-dimensional musical diff between two refs
  GET /{owner}/{repo_slug}/divergence                -- branch divergence radar chart
  GET /{owner}/{repo_slug}/timeline                  -- chronological SVG timeline
  GET /{owner}/{repo_slug}/releases                  -- release list
  GET /{owner}/{repo_slug}/releases/{tag}            -- release detail + downloads
  GET /{owner}/{repo_slug}/sessions                  -- recording session log
  GET /{owner}/{repo_slug}/sessions/{id}             -- session detail
  GET /{owner}/{repo_slug}/insights                  -- repo insights dashboard
  GET /{owner}/{repo_slug}/tree/{ref}                -- file tree browser (repo root)
  GET /{owner}/{repo_slug}/tree/{ref}/{path}         -- file tree browser (subdirectory)
  GET /{owner}/{repo_slug}/analysis/{ref}            -- analysis dashboard (all 10 dimensions at a glance)
  GET /{owner}/{repo_slug}/analysis/{ref}/contour    -- melodic contour analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/tempo      -- tempo analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/dynamics   -- dynamics analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/key        -- key detection analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/meter      -- metric analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/chord-map  -- chord map analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/groove     -- rhythmic groove analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/emotion    -- emotion analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/form       -- formal structure analysis
  GET /{owner}/{repo_slug}/analysis/{ref}/motifs     -- motif browser (recurring patterns, transformations)
  GET /{owner}/{repo_slug}/listen/{ref}              -- full-mix and per-track audio playback with track listing
  GET /{owner}/{repo_slug}/listen/{ref}/{path}       -- single-stem playback page
  GET /{owner}/{repo_slug}/listen/{ref}             -- Wavesurfer.js audio player (full mix)
  GET /{owner}/{repo_slug}/listen/{ref}/{path}      -- Wavesurfer.js audio player (single track)
  GET /{owner}/{repo_slug}/arrange/{ref}             -- arrangement matrix (instrument × section density grid)
  GET /{owner}/{repo_slug}/piano-roll/{ref}          -- interactive piano roll (all tracks)
  GET /{owner}/{repo_slug}/piano-roll/{ref}/{path}   -- interactive piano roll (single MIDI file)
  GET /{owner}/{repo_slug}/activity                  -- repo-level event stream (commits, PRs, issues, branches, tags, sessions)

These routes require NO JWT auth -- they return HTML shells whose embedded
JavaScript fetches data from the authed JSON API (``/api/v1/musehub/...``)
using a token stored in ``localStorage``.

The embed route sets ``X-Frame-Options: ALLOWALL`` for cross-origin iframe use.
"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, select as sa_select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response as StarletteResponse

from musehub.api.routes.musehub.htmx_helpers import htmx_fragment_or_full, htmx_trigger, is_htmx
from musehub.api.routes.musehub.json_alternate import json_or_html
from musehub.api.routes.musehub.negotiate import negotiate_response
from musehub.api.routes.musehub.ui_jsonld import jsonld_release, jsonld_repo, render_jsonld_script
from musehub.db import get_db
from musehub.models.musehub import CommitListResponse, CommitResponse, RepoResponse, TrackListingResponse
from musehub.models.musehub_analysis import DimensionData
from musehub.models.musehub import (
    BranchDetailListResponse,
    CommitListResponse,
    CommitResponse,
    PRDiffResponse,
    RepoResponse,
    TagListResponse,
    TagResponse,
)
from musehub.db import musehub_models as musehub_db
from musehub.muse_cli.models import MuseCliTag
from musehub.db import musehub_label_models as label_db
from musehub.services import musehub_analysis, musehub_credits, musehub_divergence, musehub_events, musehub_issues, musehub_listen, musehub_pull_requests, musehub_releases
from musehub.services import musehub_discover, musehub_repository, musehub_search
from musehub.api.routes.musehub._templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["musehub-ui"])

# Fixed-path routes registered BEFORE the /{owner}/{repo_slug} wildcard to
# prevent /explore, /trending, and /users/* from being shadowed.
fixed_router = APIRouter(prefix="", tags=["musehub-ui"])



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_url(owner: str, repo_slug: str) -> str:
    """Return the canonical UI base URL for a repo."""
    return f"/{owner}/{repo_slug}"


# Maps file extensions to display-friendly language names for the blob viewer.
# Used by _detect_language() to annotate server-rendered file content.
_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".txt": "text",
    ".xml": "xml",
    ".html": "html",
    ".css": "css",
    ".sh": "bash",
    ".mid": "midi",
    ".midi": "midi",
}

# File types (from extension) that should not be rendered as text lines.
_BLOB_BINARY_TYPES: frozenset[str] = frozenset(
    [".mid", ".midi", ".mp3", ".wav", ".flac", ".ogg", ".webp", ".png", ".jpg", ".jpeg"]
)


def _detect_language(path: str) -> str:
    """Return a display-friendly language name for a file path based on its extension.

    Used by blob_page() to annotate server-rendered file content and choose
    the correct syntax-highlighting hint for the client-side enhancer.
    Returns an empty string for unrecognised extensions.
    """
    ext = os.path.splitext(path)[1].lower()
    return _LANG_MAP.get(ext, "")


def _breadcrumbs(*segments: tuple[str, str]) -> list[dict[str, str]]:
    """Build breadcrumb_data list from (label, url) pairs.

    Each dict has ``label`` (display text) and ``url`` (link target).
    Pass an empty string for ``url`` to render the segment as plain text
    (used for the leaf/current-page segment).
    """
    return [{"label": label, "url": url} for label, url in segments]


async def _resolve_repo(
    owner: str, repo_slug: str, db: AsyncSession
) -> tuple[str, str]:
    """Resolve owner+slug to repo_id; raise 404 if not found.

    Returns (repo_id, base_url) as a convenience so callers can unpack
    both in one line.
    """
    row = await musehub_repository.get_repo_orm_by_owner_slug(db, owner, repo_slug)
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Repo '{owner}/{repo_slug}' not found",
        )
    return str(row.repo_id), _base_url(owner, repo_slug)


async def _resolve_repo_full(
    owner: str, repo_slug: str, db: AsyncSession
) -> tuple[RepoResponse, str]:
    """Resolve owner+slug to a full RepoResponse; raise 404 if not found.

    Returns (repo_response, base_url).  Use this when the handler needs
    structured repo data (e.g. to return JSON via negotiate_response).
    """
    repo = await musehub_repository.get_repo_by_owner_slug(db, owner, repo_slug)
    if repo is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Repo '{owner}/{repo_slug}' not found",
        )
    return repo, _base_url(owner, repo_slug)


def _og_tags(
    *,
    title: str,
    description: str = "",
    image: str = "",
    og_type: str = "website",
    twitter_card: str = "summary",
) -> dict[str, str]:
    """Build Open Graph and Twitter Card meta tag dict for a page template.

    Returns a flat mapping of meta property name → content string.  Template
    authors receive this as ``og_meta`` in the template context and iterate
    over it to emit ``<meta property="..." content="...">`` tags in the
    document ``<head>``.

    Why a helper: OG tags are structurally repetitive (title, description, and
    image appear once for OG and once for Twitter).  Centralising the mapping
    ensures both protocol families stay in sync and reduces copy-paste errors
    in handlers.

    Call this for any page that should expose rich-preview metadata to social
    crawlers and link-unfurling bots.  Omit ``image`` when no canonical preview
    image exists — crawlers fall back to the site default.
    """
    tags: dict[str, str] = {
        "og:title": title,
        "og:type": og_type,
        "twitter:card": twitter_card,
        "twitter:title": title,
    }
    if description:
        tags["og:description"] = description
        tags["twitter:description"] = description
    if image:
        tags["og:image"] = image
        tags["twitter:image"] = image
    return tags


# ---------------------------------------------------------------------------
# Fixed-path routes (registered before wildcard routes in main.py)
# ---------------------------------------------------------------------------


@fixed_router.get("/feed", summary="MuseHub activity feed")
async def feed_page(request: Request) -> Response:
    """Render the activity feed page — events from followed users and watched repos."""
    ctx: dict[str, object] = {"title": "Feed"}
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/feed.html", ctx),
        ctx,
    )


@fixed_router.get("/search", summary="MuseHub global search page")
async def global_search_page(
    request: Request,
    q: str = "",
    mode: str = "keyword",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the global cross-repo search page with SSR results.

    Results are fetched server-side and rendered into Jinja2 templates so the
    page is fully readable without JavaScript.  HTMX live-search (debounced
    input trigger) swaps only the ``#search-results`` fragment on subsequent
    queries, avoiding a full-page reload.
    """
    safe_mode = mode if mode in ("keyword", "pattern") else "keyword"
    result = None
    if q and len(q.strip()) >= 2:
        result = await musehub_repository.global_search(
            db,
            query=q,
            mode=safe_mode,
            page=page,
            page_size=page_size,
        )
        logger.info(
            "✅ Global search SSR q=%r mode=%s page=%d → %d groups",
            q,
            safe_mode,
            page,
            len(result.groups) if result else 0,
        )
    ctx: dict[str, object] = {
        "query": q,
        "mode": safe_mode,
        "page": page,
        "page_size": page_size,
        "result": result,
        "modes": ["keyword", "pattern"],
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/global_search.html",
        fragment_template="musehub/fragments/global_search_results.html",
    )


@fixed_router.get("/explore", summary="MuseHub explore page")
async def explore_page(
    request: Request,
    lang: list[str] = Query(default=[], alias="lang", description="Language/instrument filter chips (multi-select)"),
    license_filter: str = Query(default="", alias="license", description="License filter (e.g. CC0, CC BY)"),
    sort: str = Query(default="stars", description="Sort order: stars | updated | forks | trending"),
    topic: list[str] = Query(default=[], alias="topic", description="Topic filter chips (multi-select)"),
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(default=24, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the explore/discover page — an SSR filterable grid of all public repos.

    No JWT required.  Filter sidebar uses GET params so all filter states are
    bookmarkable and shareable.  Sidebar data (muse_tag chips, topic chips) is
    pre-loaded server-side to avoid an extra round-trip on first paint.

    HTMX fragment requests (HX-Request: true) return only the repo grid fragment
    so filter changes can swap the grid without a full page reload.

    Filter sources:
    - ``lang`` chips: top 30 distinct values from the ``muse_tags`` table.
    - ``topic`` chips: top 40 distinct tags from ``musehub_repos.tags`` JSON.
    - ``license``: fixed enum (CC0, CC BY, CC BY-SA, CC BY-NC, All Rights Reserved).
    - ``sort``: stars | updated | forks | trending.
    """
    # Build Language/Instrument chip cloud from musehub_repos.tags JSON.
    # Tags may be prefixed (emotion:melancholic, genre:baroque, stage:released) or bare.
    # We strip the prefix and count distinct values so chips cover all 39 public repos,
    # not just the ~10 repos that happen to have muse_cli commit data.
    lang_tag_rows = await db.execute(
        sa_select(musehub_db.MusehubRepo.tags).where(
            musehub_db.MusehubRepo.visibility == "public"
        )
    )
    _lang_counts: dict[str, int] = {}
    for (tags,) in lang_tag_rows:
        for t in tags or []:
            raw = str(t)
            # Strip known prefixes so "emotion:melancholic" → "melancholic"
            value = raw.split(":", 1)[-1].lower() if ":" in raw else raw.lower()
            # Skip very short values (keys like "c", "f") and tempo strings
            if len(value) >= 3 and not value.replace(".", "").isdigit():
                _lang_counts[value] = _lang_counts.get(value, 0) + 1
    muse_tag_chips: list[str] = [
        name
        for name, _ in sorted(_lang_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    ]

    # Fetch top topics from public repo tag JSON arrays (same logic as topics API).
    topic_rows = await db.execute(
        sa_select(musehub_db.MusehubRepo.tags).where(
            musehub_db.MusehubRepo.visibility == "public"
        )
    )
    topic_counts: dict[str, int] = {}
    for (tags,) in topic_rows:
        for t in tags or []:
            key = str(t).lower()
            topic_counts[key] = topic_counts.get(key, 0) + 1
    topic_chips: list[str] = [
        name
        for name, _ in sorted(topic_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:40]
    ]

    # Map UI sort labels to discover service sort fields.
    _sort_map: dict[str, musehub_discover.SortField] = {
        "stars": "stars",
        "updated": "activity",
        "forks": "commits",
        "trending": "trending",
    }
    effective_sort: musehub_discover.SortField = _sort_map.get(sort, "stars")

    # Fetch repos server-side for SSR grid, passing all active filters.
    explore = await musehub_discover.list_public_repos(
        db,
        sort=effective_sort,
        page=page,
        page_size=per_page,
        langs=lang or None,
        topics=topic or None,
        license=license_filter or None,
    )
    total_pages = max(1, (explore.total + per_page - 1) // per_page)

    ctx: dict[str, object] = {
        "title": "Explore",
        "breadcrumb": "Explore",
        "repos": explore.repos,
        "total": explore.total,
        "page": page,
        "total_pages": total_pages,
        "sort": sort,
        "muse_tag_chips": muse_tag_chips,
        "topic_chips": topic_chips,
        "selected_langs": lang,
        "selected_license": license_filter,
        "selected_topics": topic,
        "license_options": ["", "CC0", "CC BY", "CC BY-SA", "CC BY-NC", "All Rights Reserved"],
        "sort_options": [
            ("stars", "Most starred"),
            ("updated", "Recently updated"),
            ("forks", "Most forked"),
            ("trending", "Trending"),
        ],
        "base_explore_url": "/explore",
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/explore.html",
        fragment_template="musehub/fragments/repo_grid.html",
    )


@fixed_router.get("/trending", summary="MuseHub trending page")
async def trending_page(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(default=24, ge=1, le=100, description="Results per page"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the trending page — public repos sorted by star count, SSR.

    HTMX fragment requests (HX-Request: true) return only the repo grid
    fragment for seamless pagination without a full page reload.
    """
    explore = await musehub_discover.list_public_repos(
        db,
        sort="stars",
        page=page,
        page_size=per_page,
    )
    total_pages = max(1, (explore.total + per_page - 1) // per_page)

    ctx: dict[str, object] = {
        "title": "Trending",
        "breadcrumb": "Trending",
        "repos": explore.repos,
        "total": explore.total,
        "page": page,
        "total_pages": total_pages,
        "sort": "stars",
        "base_explore_url": "/trending",
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/trending.html",
        fragment_template="musehub/fragments/repo_grid.html",
    )


# ---------------------------------------------------------------------------
# Repo-scoped pages
# ---------------------------------------------------------------------------


@router.get(
    "/{owner}/{repo_slug}",
    summary="MuseHub repo home page",
)
async def repo_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str = Query("HEAD", description="Branch name or commit SHA to view"),
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the repo home page with SSR file tree, recent commits, and branch picker.

    All data is fetched server-side and rendered via Jinja2.  HTMX handles
    branch-switching: selecting a branch submits the form via ``hx-get`` and
    swaps only the ``#file-tree`` container with the file_tree fragment.

    Content negotiation:
    - ``?format=json`` or ``Accept: application/json`` → full ``RepoResponse`` with camelCase keys.
    - ``HX-Request: true`` → bare ``file_tree.html`` fragment (branch-switch target).
    - Default → full SSR page via ``repo_home.html``.

    Clone URL variants passed to the template:
    - ``clone_url_musehub``: native DAW protocol (``musehub://{owner}/{slug}``)
    - ``clone_url_ssh``: SSH git remote (``ssh://git@musehub.app/{owner}/{slug}.git``)
    - ``clone_url_https``: HTTPS git remote (``https://musehub.app/{owner}/{slug}.git``)
    """
    repo, base_url = await _resolve_repo_full(owner, repo_slug, db)
    repo_id = repo.repo_id

    # JSON shortcut for API consumers — return structured data without SSR overhead.
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        return JSONResponse(repo.model_dump(by_alias=True, mode="json"))

    # Resolve "HEAD" → real branch name so tree links use a stable, routable ref.
    if ref == "HEAD":
        ref = await musehub_repository.resolve_head_ref(db, repo_id)

    # Fetch all SSR data in parallel.
    tree_response = await musehub_repository.list_tree(db, repo_id, owner, repo_slug, ref, "")
    (commits, _) = await musehub_repository.list_commits(db, repo_id, limit=5)
    branches = await musehub_repository.list_branches(db, repo_id)
    releases = await musehub_releases.list_releases(db, repo_id)
    tags_count = len(releases)

    # Fetch settings from ORM (not on RepoResponse wire model) for license display.
    orm_repo = await db.get(musehub_db.MusehubRepo, repo_id)
    repo_license: str = ""
    if orm_repo and orm_repo.settings and isinstance(orm_repo.settings, dict):
        repo_license = orm_repo.settings.get("license", "") or ""

    page_url = str(request.url)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "home",
        "repo": repo,
        "repo_license": repo_license,
        "ref": ref,
        "tree": tree_response.entries,
        # commit_row macro expects camelCase keys (commitId, etc.)
        "commits": [c.model_dump(by_alias=True) for c in commits],
        "branches": branches,
        "tags_count": tags_count,
        "jsonld_script": render_jsonld_script(jsonld_repo(repo, page_url)),
        "og_meta": _og_tags(
            title=f"{owner}/{repo_slug} — MuseHub",
            description=repo.description or f"Music composition repository by {owner}",
            og_type="website",
        ),
        "clone_url_musehub": f"musehub://{owner}/{repo_slug}",
        "clone_url_ssh": f"ssh://git@musehub.app/{owner}/{repo_slug}.git",
        "clone_url_https": f"https://musehub.app/{owner}/{repo_slug}.git",
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/repo_home.html",
        fragment_template="musehub/fragments/file_tree.html",
    )


@router.get(
    "/{owner}/{repo_slug}/commits",
    summary="MuseHub commits list page",
)
async def commits_list_page(
    request: Request,
    owner: str,
    repo_slug: str,
    branch: str | None = Query(None, description="Filter commits by branch name"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(30, ge=1, le=200, description="Commits per page"),
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    author: str | None = Query(None, description="Filter by commit author"),
    q: str | None = Query(None, description="Full-text search over commit messages"),
    date_from: str | None = Query(None, alias="dateFrom", description="ISO date lower bound (inclusive), e.g. 2026-01-01"),
    date_to: str | None = Query(None, alias="dateTo", description="ISO date upper bound (inclusive), e.g. 2026-12-31"),
    tag_filter: str | None = Query(None, alias="tag", description="Filter by muse_tag prefix, e.g. 'emotion:happy', 'stage:chorus'"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the paginated commits list page or return structured commit data as JSON.

    HTML (default): renders ``commits.html`` with:
    - Rich filter bar: author dropdown, date range pickers, message search, tag filter.
    - Per-commit metadata badges: tempo (♩ BPM), key, emotion, stage, instruments.
    - Compare mode: checkbox per row; selecting exactly 2 activates a compare link.
    - Visual mini-lane: DAG dots with merge-commit indicators.
    - Paginated history, branch selector.

    JSON (``Accept: application/json`` or ``?format=json``): returns
    ``CommitListResponse`` with the newest commits first for the requested page.

    Filter params (``author``, ``q``, ``dateFrom``, ``dateTo``, ``tag``) are
    applied server-side so pagination counts stay accurate.  They are forwarded
    through pagination links so the filter state persists across pages.
    """
    from datetime import date as _date, timedelta as _td

    import sqlalchemy as _sa

    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    # ── Build the filtered SQLAlchemy query ──────────────────────────────────
    base_stmt = sa_select(musehub_db.MusehubCommit).where(
        musehub_db.MusehubCommit.repo_id == repo_id
    )
    if branch:
        base_stmt = base_stmt.where(musehub_db.MusehubCommit.branch == branch)
    if author:
        base_stmt = base_stmt.where(musehub_db.MusehubCommit.author == author)
    if q:
        base_stmt = base_stmt.where(
            musehub_db.MusehubCommit.message.ilike(f"%{q}%")
        )
    if date_from:
        try:
            df = _date.fromisoformat(date_from)
            base_stmt = base_stmt.where(musehub_db.MusehubCommit.timestamp >= df.isoformat())
        except ValueError:
            pass  # ignore malformed date — show all results
    if date_to:
        try:
            dt = _date.fromisoformat(date_to)
            dt_end = (dt + _td(days=1)).isoformat()  # inclusive upper bound
            base_stmt = base_stmt.where(musehub_db.MusehubCommit.timestamp < dt_end)
        except ValueError:
            pass

    # tag_filter matches muse_tag namespace prefixes embedded in commit messages
    # (e.g. "emotion:happy", "stage:chorus") since musehub_commits has no
    # separate tags column — tags live in commit messages by convention.
    if tag_filter:
        base_stmt = base_stmt.where(
            musehub_db.MusehubCommit.message.ilike(f"%{tag_filter}%")
        )

    total_stmt = sa_select(func.count()).select_from(base_stmt.subquery())
    total: int = (await db.execute(total_stmt)).scalar_one()

    offset = (page - 1) * per_page
    rows_stmt = (
        base_stmt.order_by(_sa.desc(musehub_db.MusehubCommit.timestamp))
        .offset(offset)
        .limit(per_page)
    )
    rows = (await db.execute(rows_stmt)).scalars().all()

    # Build CommitResponse objects inline — same mapping as the service layer.
    commits = [
        CommitResponse(
            commit_id=r.commit_id,
            branch=r.branch,
            parent_ids=list(r.parent_ids or []),
            message=r.message,
            author=r.author,
            timestamp=r.timestamp,
            snapshot_id=r.snapshot_id,
        )
        for r in rows
    ]

    # ── Distinct authors for the filter dropdown ──────────────────────────────
    author_stmt = (
        sa_select(musehub_db.MusehubCommit.author)
        .where(musehub_db.MusehubCommit.repo_id == repo_id)
        .distinct()
        .order_by(musehub_db.MusehubCommit.author)
    )
    all_authors: list[str] = list((await db.execute(author_stmt)).scalars().all())

    branches = await musehub_repository.list_branches(db, repo_id)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # ── Active filter set (forwarded to pagination links) ────────────────────
    active_filters: dict[str, str] = {}
    if branch:
        active_filters["branch"] = branch
    if author:
        active_filters["author"] = author
    if q:
        active_filters["q"] = q
    if date_from:
        active_filters["dateFrom"] = date_from
    if date_to:
        active_filters["dateTo"] = date_to
    if tag_filter:
        active_filters["tag"] = tag_filter

    return await negotiate_response(
        request=request,
        template_name="musehub/pages/commits.html",
        context={
            "owner": owner,
            "repo_slug": repo_slug,
            "repo_id": repo_id,
            "base_url": base_url,
            "current_page": "commits",
            "commits": commits,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "branch": branch,
            "branches": branches,
            "all_authors": all_authors,
            "filter_author": author or "",
            "filter_q": q or "",
            "filter_date_from": date_from or "",
            "filter_date_to": date_to or "",
            "filter_tag": tag_filter or "",
            "active_filters": active_filters,
            "breadcrumb_data": _breadcrumbs(
                (owner, f"/{owner}"),
                (repo_slug, base_url),
                ("commits", ""),
            ),
        },
        templates=templates,
        json_data=CommitListResponse(commits=commits, total=total),
        format_param=format,
        fragment_template="musehub/fragments/commit_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/commits/{commit_id}",
    summary="MuseHub commit detail page",
)
async def commit_page(
    request: Request,
    owner: str,
    repo_slug: str,
    commit_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the commit detail page — SSR metadata + comments, JS audio/score cores.

    Partial SSR strategy (HTMX phase 4):
    - Commit header (message, author, timestamp, SHA, parent SHAs) → server-rendered.
    - Comment thread → server-rendered; HTMX refreshes it after new comment POST.
    - WaveSurfer.js audio player → JS-initialized from ``data-url`` attribute when
      ``audio_url`` is resolved server-side (``commit.snapshot_id`` present).
    - abcjs score renderer → JS-initialized from ``data-abc-url`` attribute when
      ``has_score`` is True.

    HTMX requests (``HX-Request: true``) receive only the comment fragment so the
    comment form can re-render the thread without a full page reload.

    Returns 404 when ``commit_id`` is not found in this repo.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    commit = await musehub_repository.get_commit(db, repo_id, commit_id)
    if commit is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Commit not found")

    short_id = commit_id[:8]

    # Fetch commit comments server-side (target_type="commit" in musehub_comments).
    comment_rows = (
        await db.execute(
            sa_select(musehub_db.MusehubComment)
            .where(
                musehub_db.MusehubComment.repo_id == repo_id,
                musehub_db.MusehubComment.target_type == "commit",
                musehub_db.MusehubComment.target_id == commit_id,
                musehub_db.MusehubComment.is_deleted.is_(False),
            )
            .order_by(musehub_db.MusehubComment.created_at)
        )
    ).scalars().all()
    comments = [
        {
            "comment_id": r.comment_id,
            "author": r.author,
            "body": r.body,
            "parent_id": r.parent_id,
            "created_at": r.created_at,
        }
        for r in comment_rows
    ]

    # Derive audio URL from snapshot_id when available.  WaveSurfer picks this
    # up from the data-url attribute; no JS API call needed when present.
    api_base = f"/api/v1/repos/{repo_id}"
    audio_url: str | None = (
        f"{api_base}/objects/{commit.snapshot_id}/content"
        if commit.snapshot_id is not None
        else None
    )
    # Score (abcjs) support is reserved for future data-model enrichment.
    has_score = False
    abc_url: str | None = None

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "commit_id": commit_id,
        "short_id": short_id,
        "base_url": base_url,
        "listen_url": f"{base_url}/listen/{commit_id}",
        "embed_url": f"{base_url}/embed/{commit_id}",
        "current_page": "commits",
        "commit": commit.model_dump(),
        "comments": comments,
        "audio_url": audio_url,
        "has_score": has_score,
        "abc_url": abc_url,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("commits", f"{base_url}/commits"),
            (short_id, ""),
        ),
        "og_meta": _og_tags(
            title=f"Commit {short_id} · {owner}/{repo_slug} — MuseHub",
            description=commit.message,
            og_type="music.song",
        ),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/commit_detail.html",
        fragment_template="musehub/fragments/commit_comments.html",
    )


@router.get(
    "/{owner}/{repo_slug}/commits/{commit_id}/diff",
    summary="MuseHub musical diff view",
)
async def diff_page(
    request: Request,
    owner: str,
    repo_slug: str,
    commit_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the musical diff between a commit and its parent.

    Shows key/tempo/time-signature deltas, tracks added/removed/modified,
    and side-by-side artifact comparison. Fetches commit and parent metadata
    from the API client-side.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "commit_id": commit_id,
        "base_url": base_url,
        "current_page": "commits",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/diff.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/graph",
    summary="MuseHub interactive DAG commit graph",
)
async def graph_page(
    request: Request,
    owner: str,
    repo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the interactive DAG commit graph with SSR metadata scaffolding.

    Fetches commit and branch counts server-side and injects them into the
    template so the page header renders without JS.  Commit graph data is
    also pre-serialised into ``window.__graphData`` so the client-side DAG
    renderer can skip the initial API round-trip and render immediately.

    The complex SVG layout computation (force-directed positioning, zoom/pan,
    popover hover) remains client-side — this is inherently visual and cannot
    be SSR'd in a meaningful way.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    commits, _total = await musehub_repository.list_commits(db, repo_id, limit=100)
    branches = await musehub_repository.list_branches(db, repo_id)

    graph_data = [
        {
            "sha": c.commit_id,
            "shortSha": c.commit_id[:8],
            "message": c.message,
            "author": c.author,
            "timestamp": c.timestamp.isoformat(),
            "parents": c.parent_ids,
        }
        for c in commits
    ]

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "graph",
        "graph_data_json": graph_data,
        "commit_count": len(commits),
        "branch_count": len(branches),
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/graph.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/pulls",
    summary="MuseHub pull request list page",
)
async def pr_list_page(
    request: Request,
    owner: str,
    repo_slug: str,
    state: str = Query("open", pattern="^(open|merged|closed|all)$"),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the PR list page with SSR data and HTMX fragment support.

    Fetches open, merged, and closed PR counts server-side and renders the
    active tab's rows. Returns a bare fragment when ``HX-Request: true`` so
    HTMX tab switches only swap the ``#pr-rows`` container.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    open_prs = await musehub_pull_requests.list_prs(db, repo_id, state="open")
    merged_prs = await musehub_pull_requests.list_prs(db, repo_id, state="merged")
    closed_prs = await musehub_pull_requests.list_prs(db, repo_id, state="closed")

    if state == "merged":
        active_prs = merged_prs
    elif state == "closed":
        active_prs = closed_prs
    elif state == "all":
        active_prs = open_prs + merged_prs + closed_prs
    else:
        active_prs = open_prs

    if sort == "oldest":
        active_prs = sorted(active_prs, key=lambda p: p.created_at)
    else:
        active_prs = sorted(active_prs, key=lambda p: p.created_at, reverse=True)

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "pulls",
        "prs": [p.model_dump() for p in active_prs],
        "open_count": len(open_prs),
        "merged_count": len(merged_prs),
        "closed_count": len(closed_prs),
        "state": state,
        "active_sort": sort,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Pull Requests", f"{base_url}/pulls"),
        ),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/pr_list.html",
        fragment_template="musehub/fragments/pr_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/pulls/{pr_id}",
    response_class=HTMLResponse,
    summary="MuseHub PR detail page — SSR with HTMX review/merge actions",
)
async def pr_detail_page(
    request: Request,
    owner: str,
    repo_slug: str,
    pr_id: str,
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the PR detail page with full SSR data and HTMX fragment support.

    Fetches the PR record, reviews, and comment thread server-side so the
    initial HTML render is complete without any client-side API calls.
    Returns a bare comment fragment when ``HX-Request: true`` so HTMX can
    swap only ``#pr-comments`` on partial refreshes.

    Raises HTTP 404 when the PR does not exist in the given repository.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    pr = await musehub_pull_requests.get_pr(db, repo_id, pr_id)
    if pr is None:
        raise HTTPException(status_code=404, detail=f"Pull request {pr_id} not found")

    # JSON content negotiation — return PRDiffResponse for agent/API consumers.
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        try:
            divergence_result = await musehub_divergence.compute_hub_divergence(
                db,
                repo_id=repo_id,
                branch_a=pr.from_branch,
                branch_b=pr.to_branch,
            )
            diff_response = musehub_divergence.build_pr_diff_response(
                pr_id=pr_id,
                from_branch=pr.from_branch,
                to_branch=pr.to_branch,
                result=divergence_result,
            )
        except ValueError:
            diff_response = musehub_divergence.build_zero_diff_response(
                pr_id=pr_id,
                repo_id=repo_id,
                from_branch=pr.from_branch,
                to_branch=pr.to_branch,
            )
        return JSONResponse(diff_response.model_dump(by_alias=True, mode="json"))

    reviews_resp = await musehub_pull_requests.list_reviews(
        db, repo_id=repo_id, pr_id=pr_id
    )
    comments_resp = await musehub_pull_requests.list_pr_comments(
        db, pr_id=pr_id, repo_id=repo_id
    )

    approved_count = sum(1 for r in reviews_resp.reviews if r.state == "approved")
    changes_count = sum(
        1 for r in reviews_resp.reviews if r.state == "changes_requested"
    )

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "pr_id": pr_id,
        "base_url": base_url,
        "current_page": "pulls",
        "pr": pr.model_dump(),
        "reviews": [r.model_dump() for r in reviews_resp.reviews],
        "comments": [c.model_dump() for c in comments_resp.comments],
        "comment_count": comments_resp.total,
        "approved_count": approved_count,
        "changes_count": changes_count,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Pull Requests", f"{base_url}/pulls"),
            (pr_id[:8], f"{base_url}/pulls/{pr_id}"),
        ),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/pr_detail.html",
        fragment_template="musehub/fragments/pr_comments.html",
    )


@router.get(
    "/{owner}/{repo_slug}/issues",
    summary="MuseHub issue list page",
)
async def issue_list_page(
    request: Request,
    owner: str,
    repo_slug: str,
    state: str = Query("open", pattern="^(open|closed)$"),
    label: str | None = Query(None),
    milestone_id: str | None = Query(None),
    assignee: str | None = Query(None),
    author: str | None = Query(None),
    sort: str = Query("newest", pattern="^(newest|oldest|most-commented)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the issue list page with full server-side data and HTMX fragment support.

    Fetches open/closed counts, applies label/milestone/assignee/author filters
    server-side, paginates the result, and renders either a full page or a bare
    HTMX fragment depending on the ``HX-Request`` header.

    No JWT required — issue data is publicly readable.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    # Fetch all open and closed issues for counts and assignee collection.
    all_open = await musehub_issues.list_issues(db, repo_id, state="open")
    all_closed = await musehub_issues.list_issues(db, repo_id, state="closed")
    open_count = len(all_open)
    closed_count = len(all_closed)

    # Fetch filtered issues for the active state (label + milestone applied in service).
    filtered = await musehub_issues.list_issues(
        db, repo_id, state=state, label=label, milestone_id=milestone_id
    )

    # Apply remaining Python-side filters (assignee, author).
    if assignee:
        filtered = [i for i in filtered if i.assignee == assignee]
    if author:
        q = author.lower()
        filtered = [i for i in filtered if q in (i.author or "").lower()]

    # Server-side sort.
    if sort == "oldest":
        filtered.sort(key=lambda i: i.created_at)
    elif sort == "most-commented":
        filtered.sort(key=lambda i: i.comment_count, reverse=True)
    else:
        filtered.sort(key=lambda i: i.created_at, reverse=True)

    # Pagination.
    total = len(filtered)
    offset = (page - 1) * per_page
    page_issues = filtered[offset : offset + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Labels for the filter sidebar (all labels in the repo).
    label_rows = (
        await db.execute(
            sa_select(label_db.MusehubLabel)
            .where(label_db.MusehubLabel.repo_id == repo_id)
            .order_by(label_db.MusehubLabel.name)
        )
    ).scalars().all()
    labels_data = [{"name": r.name, "color": r.color} for r in label_rows]

    # Open milestones for the filter sidebar and right sidebar.
    milestone_data = await musehub_issues.list_milestones(db, repo_id, state="open")
    milestones_data = milestone_data.milestones

    # Collect unique assignees from all issues (both states) for the filter dropdown.
    all_issues_combined = all_open + all_closed
    assignees = sorted({i.assignee for i in all_issues_combined if i.assignee})

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "issues",
        "issues": [i.model_dump() for i in page_issues],
        "open_count": open_count,
        "closed_count": closed_count,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "state": state,
        "active_label": label or "",
        "active_milestone_id": milestone_id or "",
        "active_assignee": assignee or "",
        "active_author": author or "",
        "active_sort": sort,
        "labels_data": labels_data,
        "milestones_data": milestones_data,
        "assignees": assignees,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Issues", f"{base_url}/issues"),
        ),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/issue_list.html",
        fragment_template="musehub/fragments/issue_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/context/{ref}",
    summary="MuseHub AI context viewer",
)
async def context_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the AI context viewer for a given commit ref — fully SSR.

    Calls :func:`musehub_analysis.get_context` to fetch musical summary,
    missing elements, and Muse suggestions server-side so the template
    receives a populated ``context_data`` object with no client fetch required.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    context_data = await musehub_analysis.get_context(db, repo_id, ref=ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "context_data": context_data,
    }
    return templates.TemplateResponse(request, "musehub/pages/analysis/context.html", ctx)


@router.get(
    "/{owner}/{repo_slug}/issues/{number}",
    summary="MuseHub issue detail page",
)
async def issue_detail_page(
    request: Request,
    owner: str,
    repo_slug: str,
    number: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the issue detail page with SSR body and HTMX comment threading.

    Fetches the issue, comments, labels, milestones, and linked PRs server-side.
    HTMX requests receive only the comment fragment; direct navigation receives
    the full page that extends base.html.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)

    issue = await musehub_issues.get_issue(db, repo_id, number)
    if not issue:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Issue #{number} not found",
        )

    comment_list = await musehub_issues.list_comments(db, issue.issue_id)
    comments = [c.model_dump() for c in comment_list.comments]

    milestone_list = await musehub_issues.list_milestones(db, repo_id, state="open")
    milestones_data = [m.model_dump() for m in milestone_list.milestones]

    label_rows = (
        await db.execute(
            sa_select(label_db.MusehubLabel)
            .where(label_db.MusehubLabel.repo_id == repo_id)
            .order_by(label_db.MusehubLabel.name)
        )
    ).scalars().all()
    labels_data = [{"name": r.name, "color": r.color} for r in label_rows]

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "issues",
        "issue": issue.model_dump(),
        "comments": comments,
        "labels_data": labels_data,
        "milestones_data": milestones_data,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Issues", f"{base_url}/issues"),
            (f"#{number}", ""),
        ),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/issue_detail.html",
        fragment_template="musehub/fragments/issue_comments.html",
    )


@router.get(
    "/{owner}/{repo_slug}/embed/{ref}",
    summary="Embeddable MuseHub audio player widget",
)
async def embed_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render a compact, iframe-safe audio player for a MuseHub repo commit.

    Why this route exists: external sites embed MuseHub compositions via
    ``<iframe src="/{owner}/{repo_slug}/embed/{ref}">``.

    Contract:
    - No JWT required -- public repos can be embedded without auth.
    - Returns ``X-Frame-Options: ALLOWALL`` so browsers permit cross-origin framing.
    - Audio fetched from ``/api/v1/repos/{repo_id}/objects`` at runtime.
    """
    repo_id, _ = await _resolve_repo(owner, repo_slug, db)
    short_ref = ref[:8] if len(ref) >= 8 else ref
    listen_url = _base_url(owner, repo_slug)

    # Resolve first audio track for SSR — no auth check needed (public embed)
    listing = await musehub_listen.build_track_listing(db, repo_id, ref)
    first_track = listing.tracks[0] if listing.tracks else None

    content = templates.TemplateResponse(
        request,
        "musehub/pages/embed.html",
        {
            "title": f"Player {short_ref}",
            "repo_id": repo_id,
            "ref": ref,
            "listen_url": listen_url,
            "owner": owner,
            "repo_slug": repo_slug,
            "track_url": first_track.audio_url if first_track else None,
            "track_name": first_track.name if first_track else short_ref,
        },
    )
    return Response(
        content=content.body,
        media_type="text/html",
        headers={"X-Frame-Options": "ALLOWALL"},
    )


@router.get(
    "/{owner}/{repo_slug}/listen/{ref}",
    summary="MuseHub listen page — full-mix and per-track audio playback",
)
async def listen_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the listen page with a full-mix player and per-track listing.

    Why this route exists: musicians need a dedicated listening experience to
    evaluate each stem's contribution to the mix without exporting files to a
    DAW.  The page surfaces the full-mix audio at the top, then lists each
    audio artifact with its own player, mute/solo controls, a mini waveform
    visualisation, a download button, and a link to the piano-roll view.

    Content negotiation:
    - HTML (default): interactive listen page via Jinja2.
    - JSON (``Accept: application/json`` or ``?format=json``):
      returns ``TrackListingResponse`` with all audio URLs.

    Graceful fallback: when no audio renders exist the page shows a call-to-
    action rather than an empty list, so musicians know what to do next.
    No JWT required — the HTML shell's JS handles auth for private repos.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    json_data = await musehub_listen.build_track_listing(db, repo_id, ref)

    # Build playlist payload for WaveSurfer — passed as window.__playlist
    playlist_data = [
        {
            "name": t.name,
            "url": t.audio_url,
            "size": t.size_bytes,
        }
        for t in json_data.tracks
    ]
    first_track = json_data.tracks[0] if json_data.tracks else None

    return await negotiate_response(
        request=request,
        template_name="musehub/pages/listen.html",
        context={
            "owner": owner,
            "repo_slug": repo_slug,
            "repo_id": repo_id,
            "ref": ref,
            "base_url": base_url,
            "current_page": "listen",
            "tracks": json_data.tracks,
            "playlist_json": playlist_data,
            "first_track_url": first_track.audio_url if first_track else None,
            "first_track_name": first_track.name if first_track else None,
        },
        templates=templates,
        json_data=json_data,
        format_param=format,
    )


@router.get(
    "/{owner}/{repo_slug}/listen/{ref}/{path:path}",
    summary="MuseHub listen page — individual stem playback",
)
async def listen_track_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the per-track listen page for a single stem artifact.

    Why this route exists: ``path`` identifies a specific stem (e.g.
    ``tracks/bass.mp3``).  This page focuses the player on that one file
    and provides a "Back to full mix" link, a download button, and the
    piano-roll viewer if a matching image artifact exists.

    Content negotiation mirrors ``listen_page``: JSON returns a single-track
    ``TrackListingResponse`` with ``has_renders=True`` when the file exists.

    No JWT required — HTML shell; JS handles auth for private repos.
    """
    import os

    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    objects = await musehub_repository.list_objects(db, repo_id)

    object_map: dict[str, str] = {obj.path: obj.object_id for obj in objects}
    image_exts: frozenset[str] = frozenset({".webp", ".png", ".jpg", ".jpeg"})
    api_base = f"/api/v1/repos/{repo_id}"

    target_obj = next((obj for obj in objects if obj.path == path), None)
    has_renders = target_obj is not None

    from musehub.models.musehub import AudioTrackEntry

    tracks: list[AudioTrackEntry] = []
    full_mix_url: str | None = None

    if target_obj:
        stem = os.path.splitext(os.path.basename(target_obj.path))[0]
        piano_roll_url: str | None = None
        for p, oid in object_map.items():
            if os.path.splitext(p)[1].lower() in image_exts and os.path.splitext(os.path.basename(p))[0] == stem:
                piano_roll_url = f"{api_base}/objects/{oid}/content"
                break
        tracks = [
            AudioTrackEntry(
                name=stem,
                path=target_obj.path,
                object_id=target_obj.object_id,
                audio_url=f"{api_base}/objects/{target_obj.object_id}/content",
                piano_roll_url=piano_roll_url,
                size_bytes=target_obj.size_bytes,
            )
        ]
        full_mix_url = f"{api_base}/objects/{target_obj.object_id}/content"

    json_data = TrackListingResponse(
        repo_id=repo_id,
        ref=ref,
        full_mix_url=full_mix_url,
        tracks=tracks,
        has_renders=has_renders,
    )

    return await negotiate_response(
        request=request,
        template_name="musehub/pages/listen.html",
        context={
            "owner": owner,
            "repo_slug": repo_slug,
            "repo_id": repo_id,
            "ref": ref,
            "track_path": path,
            "base_url": base_url,
            "current_page": "listen",
        },
        templates=templates,
        json_data=json_data,
        format_param=format,
    )


@router.get(
    "/{owner}/{repo_slug}/credits",
    summary="MuseHub dynamic credits page",
)
async def credits_page(
    request: Request,
    owner: str,
    repo_slug: str,
    sort: str = Query("count", pattern="^(count|recency|alpha)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the dynamic credits page — album liner notes for the repo.

    Fetches contributor credits server-side and renders them directly into the
    template, eliminating the client-side JS fetch.  All formatting (dates,
    roles, contribution window) is handled in the Jinja2 template using the
    ``fmtdate`` and ``fmtrelative`` filters.

    No JWT required — credits data is publicly readable.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    credits_data = await musehub_credits.aggregate_credits(db, repo_id, sort=sort)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "credits",
        "contributors": credits_data.contributors,
        "total_contributors": credits_data.total_contributors,
        "sort": sort,
    }
    return templates.TemplateResponse(request, "musehub/pages/credits.html", ctx)

@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}",
    summary="MuseHub analysis dashboard -- all musical dimensions at a glance",
)
async def analysis_dashboard_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the analysis dashboard: summary cards for all musical dimensions.

    All dimension data is computed server-side so agents and browsers receive
    a fully-rendered page without issuing additional API calls.  The aggregate
    response covers key, tempo, meter, dynamics, groove, emotion, form, motifs,
    chord map, and contour.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    aggregate = musehub_analysis.compute_aggregate_analysis(repo_id=repo_id, ref=ref)
    dim_map: dict[str, object] = {d.dimension: d.data for d in aggregate.dimensions}
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "dashboard",
        "dim_map": dim_map,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/dashboard.html",
        fragment_template="musehub/fragments/analysis/dashboard_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/search",
    summary="MuseHub in-repo search page",
)
async def search_page(
    request: Request,
    owner: str,
    repo_slug: str,
    q: str = Query("", description="Search query"),
    mode: str = Query("keyword", description="Search mode: keyword | pattern | ask"),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the in-repo search page with SSR results.

    Simple keyword / pattern / ask modes are run server-side when ``q`` is
    provided and at least 2 characters long.  The Musical Properties mode
    (``mode=property``) keeps its JS-driven form because its multi-field
    filter UI is not expressible as a single query param — that panel degrades
    gracefully to a submit-button form when JS is unavailable.

    HTMX live-search swaps only the ``#repo-search-results`` fragment on
    debounced input, avoiding a full-page reload for subsequent queries.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    safe_mode = mode if mode in ("keyword", "pattern", "ask") else "keyword"
    search_result = None
    if q and len(q.strip()) >= 2 and safe_mode != "property":
        if safe_mode == "keyword":
            search_result = await musehub_search.search_by_keyword(
                db, repo_id=repo_id, keyword=q, limit=limit
            )
        elif safe_mode == "ask":
            search_result = await musehub_search.search_by_ask(
                db, repo_id=repo_id, question=q, limit=limit
            )
        elif safe_mode == "pattern":
            search_result = await musehub_search.search_by_pattern(
                db, repo_id=repo_id, pattern=q, limit=limit
            )
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "search",
        "query": q,
        "mode": safe_mode,
        "limit": limit,
        "search_result": search_result,
        "modes": ["keyword", "pattern", "ask"],
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/search.html",
        fragment_template="musehub/fragments/search_results.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/motifs",
    summary="MuseHub motif browser page",
)
async def motifs_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the motif browser for a given commit ref — SSR.

    Fetches motif data server-side via :func:`~musehub.services.musehub_analysis.compute_dimension`
    and passes it directly to the Jinja2 template so all motif patterns,
    occurrences, and recurrence grids are rendered server-side without
    a client-side fetch.

    Auth is handled client-side via localStorage JWT, matching all other UI
    pages.  No JWT is required to render the HTML shell.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    motifs_data = musehub_analysis.compute_dimension("motifs", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "motifs",
        "motifs_data": motifs_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/motifs.html",
        fragment_template="musehub/fragments/analysis/motifs_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/arrange/{ref}",
    summary="MuseHub arrangement matrix page",
)
async def arrange_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the arrangement matrix page for a given commit ref.

    Fetches ``GET /api/v1/repos/{repo_id}/arrange/{ref}`` and renders
    an interactive instrument × section grid where:

    - Y-axis: instruments (bass, keys, guitar, drums, lead, pads)
    - X-axis: sections (intro, verse_1, chorus, bridge, outro)
    - Cell colour intensity encodes note density (0 = silent, max = densest)
    - Cell click navigates to the piano roll for that instrument + section
    - Hover tooltip shows note count, beat range, and pitch range
    - Row summaries show per-instrument note totals and section activity counts
    - Column summaries show per-section note totals and active instrument counts

    Auth is handled client-side via localStorage JWT, matching all other UI
    pages.  No JWT is required to render the HTML shell.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "arrange",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/arrange.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/compare/{refs}",
    response_class=HTMLResponse,
    summary="MuseHub compare view — multi-dimensional musical diff between two refs",
)
async def compare_page(
    request: Request,
    owner: str,
    repo_slug: str,
    refs: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the compare view for two refs — fully SSR.

    The ``refs`` path segment encodes both refs separated by ``...``:
    ``main...feature-branch`` compares ``main`` (base) against
    ``feature-branch`` (head).

    Calls :func:`musehub_analysis.compare_refs` server-side so the template
    receives a populated ``compare_data`` object with no client fetch required.

    Returns 404 when:
    - The repo owner/slug is unknown.
    - The ``refs`` value does not contain the ``...`` separator.
    - Either ref has no commits in this repo (delegated to API response).
    """
    if "..." not in refs:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Invalid compare spec '{refs}' — expected format: base...head",
        )
    base_ref, head_ref = refs.split("...", 1)
    if not base_ref or not head_ref:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Both base and head refs must be non-empty",
        )
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    compare_data = await musehub_analysis.compare_refs(db, repo_id, base=base_ref, head=head_ref)

    context: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_ref": base_ref,
        "head_ref": head_ref,
        "refs": refs,
        "base_url": base_url,
        "current_page": "compare",
        "compare_data": compare_data,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("compare", ""),
            (f"{base_ref}...{head_ref}", ""),
        ),
    }
    return templates.TemplateResponse(request, "musehub/pages/analysis/compare.html", context)


@router.get(
    "/{owner}/{repo_slug}/divergence",
    summary="MuseHub divergence visualization page",
)
async def divergence_page(
    request: Request,
    owner: str,
    repo_slug: str,
    fork_repo_id: str | None = Query(None, description="Fork repo UUID to compare against; omit for self-comparison"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the divergence visualization — fully SSR.

    Calls :func:`musehub_analysis.compute_divergence` server-side so the
    template receives a populated ``divergence_data`` object containing the
    overall score and per-dimension breakdown with no client fetch required.

    Optional ``?fork_repo_id=<uuid>`` compares against a specific fork.
    When omitted the comparison is relative to the repo itself (score=0).
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    divergence_data = await musehub_analysis.compute_divergence(db, repo_id, fork_repo_id=fork_repo_id)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "analysis",
        "fork_repo_id": fork_repo_id or "",
        "divergence_data": divergence_data,
    }
    return templates.TemplateResponse(request, "musehub/pages/analysis/divergence.html", ctx)


@router.get(
    "/{owner}/{repo_slug}/timeline",
    summary="MuseHub timeline page",
)
async def timeline_page(
    request: Request,
    owner: str,
    repo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the layered chronological timeline visualisation.

    Four independently toggleable layers: commits, emotion line chart,
    section markers, and track add/remove markers.  Includes a time
    scrubber and zoom controls (day/week/month/all-time).
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "timeline",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/timeline.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/releases",
    summary="MuseHub release list page",
)
async def release_list_page(
    request: Request,
    owner: str,
    repo_slug: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the release list page: all published versions newest first.

    Data is resolved server-side and passed to the Jinja2 template so the page
    is immediately readable without JavaScript execution.  HTMX partial requests
    (HX-Request: true) receive only the ``release_rows.html`` fragment so HTMX
    can swap just the row container without re-rendering the full shell.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    all_releases = await musehub_releases.list_releases(db, repo_id)
    total = len(all_releases)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    releases = all_releases[start : start + per_page]
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "releases",
        "releases": releases,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/releases.html",
        fragment_template="musehub/fragments/release_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/releases/{tag}",
    summary="MuseHub release detail page",
)
async def release_detail_page(
    request: Request,
    owner: str,
    repo_slug: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the release detail page: title, release notes, download packages.

    Release metadata, changelog (body), download package cards, and asset list
    are all resolved server-side and injected into the Jinja2 template.  The
    audio player div is rendered as an SSR container that WaveSurfer JS (issue
    #583) initialises client-side once the page loads.

    Returns 404 when the tag does not exist in the repository.
    """
    repo, base_url = await _resolve_repo_full(owner, repo_slug, db)
    repo_id = str(repo.repo_id)
    release = await musehub_releases.get_release_by_tag(db, repo_id, tag)
    if release is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Release '{tag}' not found in '{owner}/{repo_slug}'",
        )
    assets_resp = await musehub_releases.list_release_assets(db, release.release_id, tag)
    page_url = str(request.url)
    jsonld_script = render_jsonld_script(jsonld_release(release, repo, page_url))
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "tag": tag,
        "base_url": base_url,
        "current_page": "releases",
        "release": release,
        "assets": assets_resp.assets,
        "jsonld_script": jsonld_script,
    }
    return templates.TemplateResponse(request, "musehub/pages/release_detail.html", ctx)


@router.get(
    "/{owner}/{repo_slug}/sessions",
    summary="MuseHub session log page",
)
async def sessions_page(
    request: Request,
    owner: str,
    repo_slug: str,
    page: int = Query(1, ge=1, description="1-based page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the session log page -- all recording sessions newest first.

    Fetches session data server-side and renders via Jinja2.  Active sessions
    appear at the top of the list.  Supports HTMX partial swap via
    ``htmx_fragment_or_full()``: a full HTML page is returned on initial load
    and only the ``#session-rows`` fragment is returned when ``HX-Request``
    is present.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    offset = (page - 1) * per_page
    sessions, total = await musehub_repository.list_sessions(
        db, repo_id, limit=per_page, offset=offset
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "sessions",
        "sessions": [s.model_dump(by_alias=True, mode="json") for s in sessions],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/sessions.html",
        fragment_template="musehub/fragments/session_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/sessions/{session_id}",
    summary="MuseHub session detail page",
)
async def session_detail_page(
    request: Request,
    owner: str,
    repo_slug: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the full session detail page with server-side data.

    Fetches the session and its participant list from the database and renders
    via Jinja2.  Returns HTTP 404 when the session does not exist so callers
    receive a proper status code rather than an empty JS shell.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    session = await musehub_repository.get_session(db, repo_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "session_id": session_id,
        "base_url": base_url,
        "current_page": "sessions",
        "session": session.model_dump(by_alias=True, mode="json"),
        "participants": session.participants,
    }
    return templates.TemplateResponse(request, "musehub/pages/session_detail.html", ctx)


@router.get(
    "/{owner}/{repo_slug}/insights",
    summary="MuseHub repo insights dashboard",
)
async def insights_page(
    request: Request,
    owner: str,
    repo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the repo insights dashboard.

    Shows commit frequency heatmap, contributor breakdown, musical evolution
    timeline (key/BPM/energy across commits), branch activity, and download
    statistics.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "insights",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/insights.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/contour",
    summary="MuseHub melodic contour analysis page",
)
async def contour_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the melodic contour analysis page for a Muse commit ref — SSR.

    Fetches contour data server-side via :func:`~musehub.services.musehub_analysis.compute_dimension`
    and passes the pitch curve directly to the Jinja2 template so the SVG
    polyline is rendered server-side without a client-side fetch.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    contour_data = musehub_analysis.compute_dimension("contour", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "contour",
        "contour_data": contour_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/contour.html",
        fragment_template="musehub/fragments/analysis/contour_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/tempo",
    summary="MuseHub tempo analysis page",
)
async def tempo_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the tempo analysis page for a Muse commit ref.

    BPM, time feel, stability bar, and tempo-change timeline are all computed
    server-side and passed to the Jinja2 template — no client-side API fetch required.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    tempo_data: DimensionData = musehub_analysis.compute_dimension("tempo", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "tempo",
        "tempo_data": tempo_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/tempo.html",
        fragment_template="musehub/fragments/analysis/tempo_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/dynamics",
    summary="MuseHub dynamics analysis page",
)
async def dynamics_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the dynamics analysis page for a Muse commit ref — SSR.

    Fetches per-track dynamics data server-side via
    :func:`~musehub.services.musehub_analysis.compute_dynamics_page_data`
    and passes it directly to the Jinja2 template so velocity bars and arc
    badges are rendered server-side without a client-side fetch.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    dynamics_data = musehub_analysis.compute_dynamics_page_data(repo_id=repo_id, ref=ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "dynamics",
        "dynamics_data": dynamics_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/dynamics.html",
        fragment_template="musehub/fragments/analysis/dynamics_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/key",
    summary="MuseHub key detection analysis page",
)
async def key_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the key detection analysis page for a Muse commit ref.

    Tonic, mode, confidence bar, relative key, and alternate key candidates are
    all computed server-side and injected into the Jinja2 template.  Agents use
    this to confirm the tonal centre before generating harmonically compatible
    material without needing an authenticated client-side API call.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    key_data: DimensionData = musehub_analysis.compute_dimension("key", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "key",
        "key_data": key_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/key.html",
        fragment_template="musehub/fragments/analysis/key_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/meter",
    summary="MuseHub meter analysis page",
)
async def meter_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the metric analysis page for a Muse commit ref.

    Time signature, compound/simple classification, beat-strength profile, and
    irregular-meter sections are all computed server-side.  Agents use this to
    generate rhythmically coherent material without an authenticated client call.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    meter_data: DimensionData = musehub_analysis.compute_dimension("meter", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "meter",
        "meter_data": meter_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/meter.html",
        fragment_template="musehub/fragments/analysis/meter_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/chord-map",
    summary="MuseHub chord map analysis page",
)
async def chord_map_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the chord map analysis page for a Muse commit ref — SSR.

    Fetches chord progression data server-side via
    :func:`~musehub.services.musehub_analysis.compute_dimension` and passes it
    directly to the Jinja2 template so the chord timeline bars are rendered
    server-side without a client-side fetch.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    chord_map_data = musehub_analysis.compute_dimension("chord-map", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "chord-map",
        "chord_map_data": chord_map_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/chord_map.html",
        fragment_template="musehub/fragments/analysis/chord_map_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/groove",
    summary="MuseHub groove analysis page",
)
async def groove_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the rhythmic groove analysis page for a Muse commit ref.

    Style, BPM, grid resolution, onset deviation, groove score, and swing
    factor are all computed server-side.  Agents use this to match rhythmic
    feel when generating continuation material.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    groove_data: DimensionData = musehub_analysis.compute_dimension("groove", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "groove",
        "groove_data": groove_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/groove.html",
        fragment_template="musehub/fragments/analysis/groove_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/emotion",
    summary="MuseHub emotion analysis page",
)
async def emotion_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the emotion analysis page for a Muse commit ref — SSR.

    Fetches emotion map data server-side via
    :func:`~musehub.services.musehub_analysis.compute_emotion_map` and passes it
    directly to the Jinja2 template so the valence/arousal scatter plot and
    trajectory are rendered server-side without a client-side fetch.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    emotion_data = musehub_analysis.compute_emotion_map(repo_id=repo_id, ref=ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "emotion",
        "emotion_data": emotion_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/emotion.html",
        fragment_template="musehub/fragments/analysis/emotion_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/form",
    summary="MuseHub form analysis page",
)
async def form_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the formal structure analysis page for a Muse commit ref.

    Macro form label, colour-coded section timeline, and per-section beat/function
    table are all computed server-side.  Agents use this to understand where they
    are in the compositional arc without needing an authenticated client API call.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    form_data: DimensionData = musehub_analysis.compute_dimension("form", ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "form",
        "form_data": form_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/form.html",
        fragment_template="musehub/fragments/analysis/form_content.html",
    )


@router.get(
    "/{owner}/{repo_slug}/tree/{ref}",
    summary="MuseHub file tree browser — repo root",
)
async def tree_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the file tree browser for the repo root at a given ref.

    Displays all top-level files and directories with music-aware file-type
    icons (MIDI=piano, MP3/WAV=waveform, JSON=braces, images=photo).
    The branch/tag selector dropdown allows switching ref without a page reload.
    Breadcrumbs show: {owner} / {repo} / tree / {ref}.

    Content negotiation: the embedded JavaScript also uses this URL to fetch
    a JSON listing from GET /api/v1/repos/{repo_id}/tree/{ref} when
    the Accept header is application/json.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "dir_path": "",
        "base_url": base_url,
        "current_page": "tree",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/tree.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/tree/{ref}/{path:path}",
    summary="MuseHub file tree browser — subdirectory",
)
async def tree_subdir_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the file tree browser for a subdirectory at a given ref.

    Behaves identically to ``tree_page`` but scoped to the subdirectory
    identified by ``path`` (e.g. "tracks", "tracks/stems").  The breadcrumb
    expands to show each path segment as a clickable link.

    Files are clickable and navigate to the blob viewer:
    /{owner}/{repo_slug}/blob/{ref}/{path}
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "dir_path": path,
        "base_url": base_url,
        "current_page": "tree",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/tree.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/groove-check",
    summary="MuseHub groove check page",
)
async def groove_check_page(
    request: Request,
    owner: str,
    repo_slug: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the rhythmic consistency dashboard for a repo.

    Displays a summary of groove metrics, an SVG bar chart of groove scores
    over the commit window, and a per-commit table with status badges.

    The chart encodes status as bar colour: green = OK, orange = WARN,
    red = FAIL.  Threshold and limit can be adjusted via controls that
    re-fetch the underlying ``GET /api/v1/repos/{repo_id}/groove-check``
    endpoint client-side.

    Auth is handled client-side via localStorage JWT, consistent with all other
    MuseHub UI pages.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "groove-check",
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/groove_check.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/branches",
    summary="MuseHub branch list page",
)
async def branches_page(
    request: Request,
    owner: str,
    repo_slug: str,
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the branch list page (SSR).

    Lists all branches with HEAD commit info, ahead/behind counts,
    musical divergence scores (placeholder), and compare links rendered
    server-side.  HTMX partial requests (``HX-Request: true``) return only
    the ``fragments/branch_rows.html`` fragment for in-place swap.

    JSON (``Accept: application/json`` or ``?format=json``): returns
    ``BranchDetailListResponse`` with camelCase keys.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    branch_data: BranchDetailListResponse = (
        await musehub_repository.list_branches_with_detail(db, repo_id)
    )
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        return JSONResponse(branch_data.model_dump(by_alias=True, mode="json"))
    default_branch = next((b for b in branch_data.branches if b.is_default), None)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "code",
        "branches": branch_data.branches,
        "default_branch": default_branch,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/branches.html",
        fragment_template="musehub/fragments/branch_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/tags",
    summary="MuseHub tag browser page",
)
async def tags_page(
    request: Request,
    owner: str,
    repo_slug: str,
    namespace: str | None = Query(None, description="Filter tags by namespace prefix"),
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the tag browser page (SSR).

    Tags are sourced from repo releases.  The tag browser groups tags by their
    namespace prefix (the text before ``:``, e.g. ``emotion``, ``genre``,
    ``instrument``) — tags without a colon fall into the ``version`` namespace.

    All tag data is rendered server-side; no client-side API fetch is required.
    The optional ``?namespace`` query parameter filters to a single namespace.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    releases = await musehub_releases.list_releases(db, repo_id)

    all_tags: list[TagResponse] = []
    for release in releases:
        tag_str = release.tag
        if ":" in tag_str:
            ns, _ = tag_str.split(":", 1)
        else:
            ns = "version"
        all_tags.append(
            TagResponse(
                tag=tag_str,
                namespace=ns,
                commit_id=release.commit_id,
                message=release.title,
                created_at=release.created_at,
            )
        )

    if namespace:
        filtered_tags = [t for t in all_tags if t.namespace == namespace]
    else:
        filtered_tags = all_tags

    namespaces: list[str] = sorted({t.namespace for t in all_tags})
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        tag_list = TagListResponse(tags=filtered_tags, namespaces=namespaces)
        return JSONResponse(tag_list.model_dump(by_alias=True, mode="json"))
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "releases",
        "tags": filtered_tags,
        "all_tags": all_tags,
        "namespaces": namespaces,
        "active_namespace": namespace or "",
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/tags.html",
    )


@router.get(
    "/{repo_id}/form-structure/{ref}",
    summary="MuseHub form and structure page",
)
async def form_structure_page(
    request: Request,
    repo_id: str,
    ref: str,
) -> Response:
    """Render the form and structure analysis page for a commit ref.

    Fetches ``GET /api/v1/repos/{repo_id}/form-structure/{ref}`` and
    renders three structural analysis panels:

    - **Section map**: SVG timeline of intro/verse/chorus/bridge/outro bars,
      colour-coded by section type, with bar numbers and length labels.
    - **Repetition structure**: which sections repeat, how many times, and
      their mean pairwise similarity score.
    - **Section comparison**: similarity heatmap rendered as an SVG grid
      where cell colour intensity encodes the 0–1 cosine similarity between
      every pair of formal sections.

    Auth is handled client-side via localStorage JWT, matching all other UI
    pages.  No JWT is required to load the HTML shell.
    """
    short_ref = ref[:8] if len(ref) >= 8 else ref
    ctx: dict[str, object] = {"repo_id": repo_id, "ref": ref, "short_ref": short_ref}
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/form_structure.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/harmony",
    summary="MuseHub harmony analysis page",
)
async def harmony_analysis_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the harmony analysis page for a Muse commit ref — SSR.

    Fetches Roman-numeral harmonic analysis server-side via
    :func:`~musehub.services.musehub_analysis.compute_harmony_analysis`
    and passes it directly to the Jinja2 template so cadences, modulations,
    and the harmonic rhythm are rendered without a client-side API fetch.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    harmony_data = musehub_analysis.compute_harmony_analysis(repo_id=repo_id, ref=ref)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "analysis",
        "analysis_dimension": "harmony",
        "harmony_data": harmony_data,
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/analysis/harmony.html",
        fragment_template="musehub/fragments/analysis/harmony_content.html",
    )



@router.get(
    "/{owner}/{repo_slug}/piano-roll/{ref}",
    summary="MuseHub piano roll — all MIDI tracks",
)
async def piano_roll_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the Canvas-based interactive piano roll for all MIDI tracks at ``ref``.

    Fetches instrument lane metadata server-side so the sidebar is rendered in
    SSR without requiring a client round-trip.  The Canvas itself and
    ``piano-roll.js`` remain client-side — MIDI rendering to a canvas is
    inherently a browser operation.

    No JWT required — HTML shell; JS fetches authed data via localStorage token.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    short_ref = ref[:8] if len(ref) >= 8 else ref
    instruments = await musehub_repository.get_instruments_for_repo(db, repo_id)
    piano_roll_data_url = f"/api/v1/repos/{repo_id}/midi?ref={ref}"
    instruments_data = [i.model_dump(by_alias=True, mode="json") for i in instruments]
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "short_ref": short_ref,
        "path": None,
        "base_url": base_url,
        "current_page": "piano-roll",
        "track": None,
        "instruments": instruments_data,
        "track_path": None,
        "piano_roll_data_url": piano_roll_data_url,
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/piano_roll.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/piano-roll/{ref}/{path:path}",
    summary="MuseHub piano roll — single MIDI track",
)
async def piano_roll_track_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the Canvas-based piano roll scoped to a single MIDI file ``path``.

    Fetches track metadata and instrument lane descriptors server-side so the
    header and sidebar render without a client round-trip.  The Canvas and
    ``piano-roll.js`` remain client-side.

    Useful for per-track deep-dive links from the tree browser or commit
    detail page.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    short_ref = ref[:8] if len(ref) >= 8 else ref
    track = await musehub_repository.get_track_info(db, repo_id, path)
    instruments = await musehub_repository.get_instruments_for_repo(db, repo_id)
    piano_roll_data_url = (
        f"/api/v1/repos/{repo_id}/midi?ref={ref}&path={path}"
    )
    track_data = track.model_dump(by_alias=True, mode="json") if track else None
    instruments_data = [i.model_dump(by_alias=True, mode="json") for i in instruments]
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "short_ref": short_ref,
        "path": path,
        "base_url": base_url,
        "current_page": "piano-roll",
        "track": track_data,
        "instruments": instruments_data,
        "track_path": path,
        "piano_roll_data_url": piano_roll_data_url,
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/piano_roll.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/blob/{ref}/{path:path}",
    summary="MuseHub file blob viewer — music-aware file rendering",
)
async def blob_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the music-aware blob viewer with SSR scaffolding.

    Fetches the file object from the database server-side and populates the
    template with enough context to render the page header, file metadata,
    and (for text files) the full line-numbered content without JavaScript.

    Rendering modes by extension:
    - .mid/.midi → MIDI player shell with data-midi-url attribute
    - .mp3/.wav/.flac → client-side audio player (JS required for <audio>)
    - Text/code files → server-rendered line-numbered table; JS enhances with
      syntax highlighting progressively
    - Binary / oversized (>1 MB) → download link only

    If no object exists at ``path`` in the repo a 404 is raised immediately,
    avoiding the JS "File not found" flash that the previous implementation
    produced.

    Auth: no JWT required for public repos.  Private-repo auth is
    handled client-side via localStorage JWT (consistent with other
    MuseHub UI pages).
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    filename = path.split("/")[-1] if path else ""

    obj = await musehub_repository.get_object_by_path(db, repo_id, path)

    lang = _detect_language(path)
    ext = os.path.splitext(path)[1].lower()
    is_binary = ext in _BLOB_BINARY_TYPES
    is_midi = ext in (".mid", ".midi")
    size_bytes: int = obj.size_bytes if obj is not None else 0

    # Treat files over 1 MB as binary regardless of extension.
    if size_bytes > 1_000_000:
        is_binary = True

    # Read text content for small non-binary files so we can SSR line numbers.
    # Use asyncio.to_thread so the blocking file read does not stall the event loop.
    content: str | None = None
    if obj is not None and not is_binary and os.path.exists(obj.disk_path):
        _disk_path = obj.disk_path

        def _read_file() -> str:
            with open(_disk_path, encoding="utf-8", errors="replace") as fh:
                return fh.read()

        try:
            content = await asyncio.to_thread(_read_file)
        except OSError:
            logger.warning("⚠️ blob_page: could not read %s", obj.disk_path)

    lines: list[str] = content.splitlines() if content is not None else []
    line_count = len(lines)

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "file_path": path,
        "filename": filename,
        "base_url": base_url,
        "current_page": "tree",
        "lang": lang,
        "is_binary": is_binary,
        "is_midi": is_midi,
        "size_bytes": size_bytes,
        "lines": lines,
        "line_count": line_count,
        "blob_found": obj is not None,
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/blob.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/score/{ref}",
    summary="MuseHub score renderer — full score, all tracks",
)
async def score_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the sheet music score page for a given commit ref (all tracks).

    Fetches score metadata server-side so the header (title, key, meter,
    instrument count) renders without a client round-trip.  The SVG notation
    renderer remains client-side — music layout requires DOM measurement.

    No JWT is required to render the HTML shell.  Auth is handled client-side
    via localStorage JWT, matching all other UI pages.

    For a single-part view use the ``score/{ref}/{path}`` variant which filters
    to one instrument track.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    score_meta = await musehub_repository.get_score_meta_for_repo(db, repo_id, "")
    abc_url = f"/api/v1/repos/{repo_id}/abc?ref={ref}"
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "path": "",
        "current_page": "score",
        "score_meta": score_meta.model_dump(by_alias=True, mode="json"),
        "abc_url": abc_url,
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/score.html", ctx),
        ctx,
    )


@router.get(
    "/{owner}/{repo_slug}/activity",
    summary="MuseHub activity feed — repo-level event stream",
)
async def activity_page(
    request: Request,
    owner: str,
    repo_slug: str,
    event_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the repo-level activity feed page with full SSR and HTMX fragment support.

    Fetches events server-side and renders them directly, eliminating the
    client-side JS fetch loop.  HTMX filter and pagination requests receive
    only the ``activity_rows.html`` fragment; direct browser navigation receives
    the full page extending ``base.html``.

    No JWT required — activity data is publicly readable.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    feed = await musehub_events.list_events(
        db,
        repo_id,
        event_type=event_type or None,
        page=page,
        page_size=per_page,
    )
    total_pages = max(1, (feed.total + per_page - 1) // per_page)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "activity",
        "events": feed.events,
        "total": feed.total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "event_type": event_type or "",
        "event_types": sorted(musehub_events.KNOWN_EVENT_TYPES),
    }
    return await htmx_fragment_or_full(
        request,
        templates,
        ctx,
        full_template="musehub/pages/activity.html",
        fragment_template="musehub/fragments/activity_rows.html",
    )


@router.get(
    "/{owner}/{repo_slug}/score/{ref}/{path:path}",
    summary="MuseHub score renderer — single-track part view",
)
async def score_part_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the sheet music score page filtered to a single instrument part.

    Fetches score metadata server-side using the ``path`` segment as the
    track title source.  The client-side renderer pre-selects that track
    in the part selector on load.

    No JWT is required to render the HTML shell.
    """
    repo_id, base_url = await _resolve_repo(owner, repo_slug, db)
    score_meta = await musehub_repository.get_score_meta_for_repo(db, repo_id, path)
    abc_url = f"/api/v1/repos/{repo_id}/abc?ref={ref}&path={path}"
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "path": path,
        "current_page": "score",
        "score_meta": score_meta.model_dump(by_alias=True, mode="json"),
        "abc_url": abc_url,
    }
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/score.html", ctx),
        ctx,
    )

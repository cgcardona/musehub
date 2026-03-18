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
from typing import Any

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
) -> tuple[str, str, dict[str, Any]]:
    """Resolve owner+slug to repo_id; raise 404 if not found.

    Returns (repo_id, base_url, nav_ctx) where nav_ctx contains all
    SSR-ready nav-header fields — repo metadata chips AND open PR/issue
    counts for the tab strip — so every page renders fully on the server
    with no client-side API round-trips that would cause FOUC.
    """
    row = await musehub_repository.get_repo_orm_by_owner_slug(db, owner, repo_slug)
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Repo '{owner}/{repo_slug}' not found",
        )
    repo_id = str(row.repo_id)

    # Two fast indexed COUNT queries run concurrently — no full table scans.
    pr_count_result, issue_count_result = await asyncio.gather(
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubPullRequest).where(
                musehub_db.MusehubPullRequest.repo_id == repo_id,
                musehub_db.MusehubPullRequest.state == "open",
            )
        ),
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubIssue).where(
                musehub_db.MusehubIssue.repo_id == repo_id,
                musehub_db.MusehubIssue.state == "open",
            )
        ),
    )
    open_pr_count: int = pr_count_result.scalar_one_or_none() or 0
    open_issue_count: int = issue_count_result.scalar_one_or_none() or 0

    nav_ctx: dict[str, Any] = {
        "repo_key": row.key_signature or "",
        "repo_bpm": row.tempo_bpm,
        "repo_tags": row.tags or [],
        "repo_visibility": row.visibility or "private",
        "nav_open_pr_count": open_pr_count,
        "nav_open_issue_count": open_issue_count,
    }
    return repo_id, _base_url(owner, repo_slug), nav_ctx


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

    # Fetch all SSR data in parallel (including tab counts for nav).
    (
        tree_response,
        (commits, _),
        branches,
        releases,
        pr_count_result,
        issue_count_result,
    ) = await asyncio.gather(
        musehub_repository.list_tree(db, repo_id, owner, repo_slug, ref, ""),
        musehub_repository.list_commits(db, repo_id, limit=5),
        musehub_repository.list_branches(db, repo_id),
        musehub_releases.list_releases(db, repo_id),
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubPullRequest).where(
                musehub_db.MusehubPullRequest.repo_id == repo_id,
                musehub_db.MusehubPullRequest.state == "open",
            )
        ),
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubIssue).where(
                musehub_db.MusehubIssue.repo_id == repo_id,
                musehub_db.MusehubIssue.state == "open",
            )
        ),
    )
    tags_count = len(releases)
    nav_ctx: dict[str, Any] = {
        "repo_key": repo.key_signature or "",
        "repo_bpm": repo.tempo_bpm,
        "repo_tags": repo.tags or [],
        "repo_visibility": repo.visibility or "private",
        "nav_open_pr_count": pr_count_result.scalar_one_or_none() or 0,
        "nav_open_issue_count": issue_count_result.scalar_one_or_none() or 0,
    }

    # Fetch settings from ORM (not on RepoResponse wire model) for license display.
    orm_repo = await db.get(musehub_db.MusehubRepo, repo_id)
    repo_license: str = ""
    if orm_repo and orm_repo.settings and isinstance(orm_repo.settings, dict):
        repo_license = str(orm_repo.settings.get("license", "") or "")

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
    ctx.update(nav_ctx)
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

    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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

    ctx: dict[str, Any] = {
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
    }
    ctx.update(nav_ctx)
    return await negotiate_response(
        request=request,
        template_name="musehub/pages/commits.html",
        context=ctx,
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    commit = await musehub_repository.get_commit(db, repo_id, commit_id)
    if commit is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Commit not found")

    short_id = commit_id[:8]
    api_base = f"/api/v1/repos/{repo_id}"

    # ── Parallel: comments + sibling commits on same branch ──────────────
    async def _q_comments() -> list[dict[str, Any]]:
        rows = (await db.execute(
            sa_select(musehub_db.MusehubComment)
            .where(
                musehub_db.MusehubComment.repo_id == repo_id,
                musehub_db.MusehubComment.target_type == "commit",
                musehub_db.MusehubComment.target_id == commit_id,
                musehub_db.MusehubComment.is_deleted.is_(False),
            )
            .order_by(musehub_db.MusehubComment.created_at)
        )).scalars().all()
        return [
            {
                "comment_id": r.comment_id,
                "author": r.author,
                "body": r.body,
                "parent_id": r.parent_id,
                "created_at": r.created_at,
            }
            for r in rows
        ]

    async def _q_branch_commits() -> list[Any]:
        commits, _ = await musehub_repository.list_commits(
            db, repo_id, branch=commit.branch, limit=100
        )
        return commits

    comments, branch_commits = await asyncio.gather(_q_comments(), _q_branch_commits())

    # ── Find prev (older) / next (newer) siblings on branch ──────────────
    # list_commits returns newest-first; pos+1 = older, pos-1 = newer
    cur_pos = next((i for i, c in enumerate(branch_commits) if c.commit_id == commit_id), None)
    older_commit: Any = branch_commits[cur_pos + 1] if (cur_pos is not None and cur_pos + 1 < len(branch_commits)) else None
    newer_commit: Any = branch_commits[cur_pos - 1] if (cur_pos is not None and cur_pos > 0) else None

    # ── Compute musical dimension change scores from commit message ───────
    _DIM_KWS: list[tuple[str, frozenset[str]]] = [
        ("melodic",    frozenset(["melody", "melodic", "lead", "motif", "phrase", "contour", "scale", "mode"])),
        ("harmonic",   frozenset(["key", "chord", "harmony", "harmonic", "tonal", "modulation", "progression", "pitch"])),
        ("rhythmic",   frozenset(["bpm", "tempo", "beat", "rhythm", "rhythmic", "groove", "swing", "meter", "time"])),
        ("structural", frozenset(["section", "structural", "intro", "verse", "chorus", "bridge", "outro", "form", "arrangement", "structure"])),
        ("dynamic",    frozenset(["dynamic", "volume", "velocity", "loud", "soft", "crescendo", "decrescendo", "fade", "mute", "swell"])),
    ]

    def _dim_score(msg: str, kws: frozenset[str], is_root: bool) -> dict[str, Any]:
        score = 1.0 if is_root else (0.0 if not any(kw in msg for kw in kws) else min(0.35 + (sum(1 for kw in kws if kw in msg) - 1) * 0.15, 0.95))
        label = "none" if score < 0.15 else ("low" if score < 0.40 else ("medium" if score < 0.70 else "high"))
        return {"dimension": name, "score": round(score, 3), "label": label}

    is_root = not commit.parent_ids
    msg_lower = commit.message.lower()
    dimensions: list[dict[str, Any]] = []
    for name, kws in _DIM_KWS:
        score = 1.0 if is_root else (0.0 if not any(kw in msg_lower for kw in kws) else min(0.35 + (sum(1 for kw in kws if kw in msg_lower) - 1) * 0.15, 0.95))
        label = "none" if score < 0.15 else ("low" if score < 0.40 else ("medium" if score < 0.70 else "high"))
        dimensions.append({"dimension": name, "score": round(score, 3), "label": label})

    overall_change = round(sum(d["score"] for d in dimensions) / len(dimensions), 3) if dimensions else 0.0

    # ── Audio / render status ─────────────────────────────────────────────
    audio_url: str | None = (
        f"{api_base}/objects/{commit.snapshot_id}/content"
        if commit.snapshot_id is not None
        else None
    )
    render_status = "ready" if audio_url else "none"

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "commit_id": commit_id,
        "short_id": short_id,
        "base_url": base_url,
        "listen_url": f"{base_url}/listen/{commit_id}",
        "embed_url": f"{base_url}/embed/{commit_id}",
        "current_page": "commits",
        "commit": commit.model_dump(mode="json"),
        "comments": comments,
        "audio_url": audio_url,
        "render_status": render_status,
        "dimensions": dimensions,
        "overall_change": overall_change,
        "older_commit": older_commit.model_dump(mode="json") if older_commit else None,
        "newer_commit": newer_commit.model_dump(mode="json") if newer_commit else None,
        "branch_commit_count": len(branch_commits),
        "branch_position": (cur_pos + 1) if cur_pos is not None else None,
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "commit_id": commit_id,
        "base_url": base_url,
        "current_page": "commits",
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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

    # ── Parallel queries ─────────────────────────────────────────────────
    async def _q_reviews() -> Any:
        return await musehub_pull_requests.list_reviews(db, repo_id=repo_id, pr_id=pr_id)

    async def _q_comments() -> Any:
        return await musehub_pull_requests.list_pr_comments(db, pr_id=pr_id, repo_id=repo_id)

    async def _q_diff() -> Any:
        try:
            result = await musehub_divergence.compute_hub_divergence(
                db, repo_id=repo_id, branch_a=pr.from_branch, branch_b=pr.to_branch,
            )
            return musehub_divergence.build_pr_diff_response(
                pr_id=pr_id, from_branch=pr.from_branch,
                to_branch=pr.to_branch, result=result,
            )
        except Exception:
            return musehub_divergence.build_zero_diff_response(
                pr_id=pr_id, repo_id=repo_id,
                from_branch=pr.from_branch, to_branch=pr.to_branch,
            )

    reviews_resp, comments_resp, diff_resp = await asyncio.gather(
        _q_reviews(), _q_comments(), _q_diff(),
    )

    # ── Fetch commits on the from_branch ────────────────────────────────
    commit_rows = (await db.execute(
        sa_select(musehub_db.MusehubCommit)
        .where(
            musehub_db.MusehubCommit.repo_id == repo_id,
            musehub_db.MusehubCommit.branch == pr.from_branch,
        )
        .order_by(musehub_db.MusehubCommit.created_at.desc())
        .limit(25)
    )).scalars().all()
    pr_commits: list[dict[str, Any]] = [
        {
            "commit_id": c.commit_id,
            "message": c.message,
            "author_name": c.author,
            "created_at": c.timestamp,
        }
        for c in commit_rows
    ]

    approved_count = sum(1 for r in reviews_resp.reviews if r.state == "approved")
    changes_count = sum(
        1 for r in reviews_resp.reviews if r.state == "changes_requested"
    )
    pending_count = sum(1 for r in reviews_resp.reviews if r.state == "pending")

    # Diff summary data for template
    diff_dict = diff_resp.model_dump(mode="json")

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "pr_id": pr_id,
        "base_url": base_url,
        "current_page": "pulls",
        "pr": pr.model_dump(mode="json"),
        "reviews": [r.model_dump(mode="json") for r in reviews_resp.reviews],
        "comments": [c.model_dump(mode="json") for c in comments_resp.comments],
        "comment_count": comments_resp.total,
        "approved_count": approved_count,
        "changes_count": changes_count,
        "pending_count": pending_count,
        "diff": diff_dict,
        "pr_commits": pr_commits,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Pull Requests", f"{base_url}/pulls"),
            (pr_id[:8], f"{base_url}/pulls/{pr_id}"),
        ),
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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

    # Derived stats for the stats bar (no extra DB queries).
    unassigned_open_count = len([i for i in all_open if not i.assignee])
    total_comment_count = sum(i.comment_count for i in all_open + all_closed)
    unique_author_count = len({i.author for i in all_open + all_closed if i.author})

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
        # Stats bar metrics
        "unassigned_open_count": unassigned_open_count,
        "total_comment_count": total_comment_count,
        "unique_author_count": unique_author_count,
        "breadcrumb_data": _breadcrumbs(
            (owner, f"/{owner}"),
            (repo_slug, base_url),
            ("Issues", f"{base_url}/issues"),
        ),
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

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
    ctx.update(nav_ctx)
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
    repo_id, _base, _nav = await _resolve_repo(owner, repo_slug, db)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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

    listen_ctx: dict[str, Any] = {
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
    }
    listen_ctx.update(nav_ctx)
    return await negotiate_response(
        request=request,
        template_name="musehub/pages/listen.html",
        context=listen_ctx,
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

    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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

    listen_track_ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "track_path": path,
        "base_url": base_url,
        "current_page": "listen",
    }
    listen_track_ctx.update(nav_ctx)
    return await negotiate_response(
        request=request,
        template_name="musehub/pages/listen.html",
        context=listen_track_ctx,
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    credits_data = await musehub_credits.aggregate_credits(db, repo_id, sort=sort)
    contributors = credits_data.contributors

    # --- Aggregate stats from credits data (no extra DB query) ----------
    total_all_commits: int = sum(c.session_count for c in contributors) if contributors else 0
    max_commits: int       = max((c.session_count for c in contributors), default=1)

    from datetime import datetime as _dt, timezone as _tz
    _epoch = _dt(1970, 1, 1, tzinfo=_tz.utc)
    project_start = min((c.first_active for c in contributors), default=_epoch)
    project_end   = max((c.last_active  for c in contributors), default=_epoch)
    project_span_days: int = max(0, (project_end - project_start).days)

    most_prolific = max(contributors, key=lambda c: c.session_count,                            default=None)
    most_recent   = max(contributors, key=lambda c: c.last_active,                              default=None)
    longest_active = max(contributors, key=lambda c: (c.last_active - c.first_active).days,    default=None)

    # --- Per-author dimension + branch breakdown (one extra query) ------
    commit_rows_r = await db.execute(
        sa_select(
            musehub_db.MusehubCommit.author,
            musehub_db.MusehubCommit.message,
            musehub_db.MusehubCommit.branch,
        ).where(musehub_db.MusehubCommit.repo_id == repo_id)
    )
    author_dim_counts: dict[str, dict[str, int]] = {}
    author_branches:   dict[str, set[str]]       = {}
    for author, message, branch in commit_rows_r:
        if author not in author_dim_counts:
            author_dim_counts[author] = {}
            author_branches[author]   = set()
        author_branches[author].add(branch)
        for dim in musehub_divergence.classify_message(message):
            author_dim_counts[author][dim] = author_dim_counts[author].get(dim, 0) + 1

    author_top_dims: dict[str, list[tuple[str, int]]] = {
        author: sorted(dims.items(), key=lambda x: -x[1])[:3]
        for author, dims in author_dim_counts.items()
    }
    author_branch_counts: dict[str, int] = {
        a: len(brs) for a, brs in author_branches.items()
    }

    # --- Unique roles across the whole project --------------------------
    all_roles: set[str] = set()
    for c in contributors:
        all_roles.update(c.contribution_types)

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "credits",
        "sort": sort,
        # Core credits data
        "contributors": contributors,
        "total_contributors": credits_data.total_contributors,
        # Aggregate stats
        "total_all_commits": total_all_commits,
        "max_commits": max_commits,
        "project_start": project_start,
        "project_end": project_end,
        "project_span_days": project_span_days,
        "all_roles": sorted(all_roles),
        # Spotlights
        "most_prolific": most_prolific,
        "most_recent": most_recent,
        "longest_active": longest_active,
        # Per-author enrichment
        "author_top_dims": author_top_dims,
        "author_branch_counts": author_branch_counts,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    search_type: str = Query("all", description="Result type filter: all | commits | issues | prs | releases | sessions"),
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the in-repo multi-type search page with SSR results.

    Searches commits, issues, pull requests, releases, and sessions in
    parallel.  The ``type`` param filters which category is shown; the
    ``mode`` param (keyword/pattern/ask) applies only to commit search.

    HTMX live-search swaps only the ``#sr-results`` fragment on debounced
    input, avoiding a full-page reload for subsequent queries.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    safe_mode = mode if mode in ("keyword", "pattern", "ask") else "keyword"
    safe_type = search_type if search_type in ("all", "commits", "issues", "prs", "releases", "sessions") else "all"

    commit_result = None
    issue_hits: list[Any] = []
    pr_hits: list[Any] = []
    release_hits: list[Any] = []
    session_hits: list[Any] = []

    if q and len(q.strip()) >= 2:
        q_lower = q.strip().lower()

        async def _search_commits() -> Any:
            if safe_mode == "keyword":
                return await musehub_search.search_by_keyword(
                    db, repo_id=repo_id, keyword=q, limit=limit
                )
            if safe_mode == "ask":
                return await musehub_search.search_by_ask(
                    db, repo_id=repo_id, question=q, limit=limit
                )
            return await musehub_search.search_by_pattern(
                db, repo_id=repo_id, pattern=q, limit=limit
            )

        async def _search_issues() -> list[Any]:
            rows = (await db.execute(
                sa_select(
                    musehub_db.MusehubIssue.issue_id,
                    musehub_db.MusehubIssue.number,
                    musehub_db.MusehubIssue.title,
                    musehub_db.MusehubIssue.state,
                    musehub_db.MusehubIssue.author,
                    musehub_db.MusehubIssue.labels,
                    musehub_db.MusehubIssue.created_at,
                ).where(
                    musehub_db.MusehubIssue.repo_id == repo_id,
                    func.lower(musehub_db.MusehubIssue.title).contains(q_lower),
                ).order_by(musehub_db.MusehubIssue.created_at.desc())
                .limit(limit)
            )).all()
            return list(rows)

        async def _search_prs() -> list[Any]:
            rows = (await db.execute(
                sa_select(
                    musehub_db.MusehubPullRequest.pr_id,
                    musehub_db.MusehubPullRequest.title,
                    musehub_db.MusehubPullRequest.state,
                    musehub_db.MusehubPullRequest.author,
                    musehub_db.MusehubPullRequest.from_branch,
                    musehub_db.MusehubPullRequest.to_branch,
                    musehub_db.MusehubPullRequest.created_at,
                ).where(
                    musehub_db.MusehubPullRequest.repo_id == repo_id,
                    func.lower(musehub_db.MusehubPullRequest.title).contains(q_lower),
                ).order_by(musehub_db.MusehubPullRequest.created_at.desc())
                .limit(limit)
            )).all()
            return list(rows)

        async def _search_releases() -> list[Any]:
            rows = (await db.execute(
                sa_select(
                    musehub_db.MusehubRelease.release_id,
                    musehub_db.MusehubRelease.tag,
                    musehub_db.MusehubRelease.title,
                    musehub_db.MusehubRelease.is_prerelease,
                    musehub_db.MusehubRelease.is_draft,
                    musehub_db.MusehubRelease.created_at,
                ).where(
                    musehub_db.MusehubRelease.repo_id == repo_id,
                    func.lower(musehub_db.MusehubRelease.title).contains(q_lower)
                    | func.lower(musehub_db.MusehubRelease.tag).contains(q_lower),
                ).order_by(musehub_db.MusehubRelease.created_at.desc())
                .limit(limit)
            )).all()
            return list(rows)

        async def _search_sessions() -> list[Any]:
            rows = (await db.execute(
                sa_select(
                    musehub_db.MusehubSession.session_id,
                    musehub_db.MusehubSession.intent,
                    musehub_db.MusehubSession.location,
                    musehub_db.MusehubSession.participants,
                    musehub_db.MusehubSession.is_active,
                    musehub_db.MusehubSession.started_at,
                ).where(
                    musehub_db.MusehubSession.repo_id == repo_id,
                    func.lower(musehub_db.MusehubSession.intent).contains(q_lower)
                    | func.lower(musehub_db.MusehubSession.location).contains(q_lower),
                ).order_by(musehub_db.MusehubSession.started_at.desc())
                .limit(limit)
            )).all()
            return list(rows)

        (
            commit_result,
            issue_hits,
            pr_hits,
            release_hits,
            session_hits,
        ) = await asyncio.gather(
            _search_commits(),
            _search_issues(),
            _search_prs(),
            _search_releases(),
            _search_sessions(),
        )

    commit_count  = len(commit_result.matches) if commit_result else 0
    issue_count   = len(issue_hits)
    pr_count      = len(pr_hits)
    release_count = len(release_hits)
    session_count = len(session_hits)
    total_count   = commit_count + issue_count + pr_count + release_count + session_count

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "search",
        "query": q,
        "mode": safe_mode,
        "search_type": safe_type,
        "limit": limit,
        # Commit search result
        "search_result": commit_result,
        # Multi-type hits
        "issue_hits": issue_hits,
        "pr_hits": pr_hits,
        "release_hits": release_hits,
        "session_hits": session_hits,
        # Counts (for type tabs)
        "commit_count": commit_count,
        "issue_count": issue_count,
        "pr_count": pr_count,
        "release_count": release_count,
        "session_count": session_count,
        "total_count": total_count,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    """Render the fully server-side-rendered arrangement matrix page.

    Pre-computes the instrument × section matrix, fetches commit metadata,
    render-job status, and recent branch commits for navigation — all passed
    to the Jinja2 template.  No client-side API calls needed for initial render.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # ── Resolve commit for this ref ─────────────────────────────────────────
    commit_row: Any = None
    render_job_row: Any = None
    branch_commits: list[Any] = []

    if ref == "HEAD":
        result = await db.execute(
            sa_select(
                musehub_db.MusehubCommit.commit_id,
                musehub_db.MusehubCommit.message,
                musehub_db.MusehubCommit.author,
                musehub_db.MusehubCommit.timestamp,
                musehub_db.MusehubCommit.branch,
            ).where(musehub_db.MusehubCommit.repo_id == repo_id)
            .order_by(musehub_db.MusehubCommit.timestamp.desc())
            .limit(1)
        )
        commit_row = result.first()
    else:
        result = await db.execute(
            sa_select(
                musehub_db.MusehubCommit.commit_id,
                musehub_db.MusehubCommit.message,
                musehub_db.MusehubCommit.author,
                musehub_db.MusehubCommit.timestamp,
                musehub_db.MusehubCommit.branch,
            ).where(
                musehub_db.MusehubCommit.repo_id == repo_id,
                musehub_db.MusehubCommit.commit_id == ref,
            ).limit(1)
        )
        commit_row = result.first()

    actual_commit_id = commit_row.commit_id if commit_row else ref
    commit_branch    = commit_row.branch if commit_row else "main"

    # ── Render job status ───────────────────────────────────────────────────
    rj_result = await db.execute(
        sa_select(
            musehub_db.MusehubRenderJob.status,
            musehub_db.MusehubRenderJob.midi_count,
            musehub_db.MusehubRenderJob.mp3_object_ids,
            musehub_db.MusehubRenderJob.image_object_ids,
        ).where(
            musehub_db.MusehubRenderJob.repo_id == repo_id,
            musehub_db.MusehubRenderJob.commit_id == actual_commit_id,
        ).limit(1)
    )
    render_job_row = rj_result.first()

    # ── Recent commits on the same branch for navigation ────────────────────
    bc_result = await db.execute(
        sa_select(
            musehub_db.MusehubCommit.commit_id,
            musehub_db.MusehubCommit.message,
            musehub_db.MusehubCommit.timestamp,
        ).where(
            musehub_db.MusehubCommit.repo_id == repo_id,
            musehub_db.MusehubCommit.branch == commit_branch,
        ).order_by(musehub_db.MusehubCommit.timestamp.desc())
        .limit(20)
    )
    branch_commits = list(bc_result.all())

    # Determine prev/next commit in time order on this branch
    commit_ids_asc = [c.commit_id for c in reversed(branch_commits)]
    current_idx    = next((i for i, c in enumerate(commit_ids_asc) if c == actual_commit_id), None)
    prev_commit_id = commit_ids_asc[current_idx - 1] if current_idx is not None and current_idx > 0 else None
    next_commit_id = commit_ids_asc[current_idx + 1] if current_idx is not None and current_idx < len(commit_ids_asc) - 1 else None

    # ── Arrangement matrix (computed server-side) ───────────────────────────
    matrix = musehub_analysis.compute_arrangement_matrix(
        repo_id=repo_id, ref=actual_commit_id
    )

    # Build cell_map[instrument][section] for easy template iteration
    cell_map: dict[str, dict[str, Any]] = {}
    for cell in matrix.cells:
        cell_map.setdefault(cell.instrument, {})[cell.section] = cell

    # Density → CSS level (0-4) for styling without inline CSS
    def _density_level(d: float) -> int:
        if d <= 0:
            return 0
        if d < 0.25:
            return 1
        if d < 0.5:
            return 2
        if d < 0.75:
            return 3
        return 4

    # Flatten for template with precomputed level
    cells_enriched: list[dict[str, Any]] = []
    for cell in matrix.cells:
        cells_enriched.append({
            "instrument": cell.instrument,
            "section": cell.section,
            "note_count": cell.note_count,
            "note_density": round(cell.note_density, 3),
            "beat_start": cell.beat_start,
            "beat_end": cell.beat_end,
            "pitch_low": cell.pitch_low,
            "pitch_high": cell.pitch_high,
            "active": cell.active,
            "level": _density_level(cell.note_density) if cell.active else 0,
        })

    # Rebuild cell_map with enriched data
    cell_map_enriched: dict[str, dict[str, Any]] = {}
    for c in cells_enriched:
        cell_map_enriched.setdefault(c["instrument"], {})[c["section"]] = c

    # Total beats across all sections
    total_beats = matrix.total_beats

    # Section beat widths as percentages (for the timeline bar)
    section_pcts: list[dict[str, Any]] = []
    for col in matrix.column_summaries:
        beats_span = col.beat_end - col.beat_start
        pct = round(beats_span / total_beats * 100, 1) if total_beats else 0
        section_pcts.append({
            "section": col.section,
            "beat_start": col.beat_start,
            "beat_end": col.beat_end,
            "pct": pct,
            "active_instruments": col.active_instruments,
            "total_notes": col.total_notes,
        })

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "base_url": base_url,
        "current_page": "arrange",
        # Commit context
        "commit_id": actual_commit_id,
        "commit_message": commit_row.message if commit_row else None,
        "commit_author": commit_row.author if commit_row else None,
        "commit_timestamp": commit_row.timestamp if commit_row else None,
        "commit_branch": commit_branch,
        # Navigation
        "prev_commit_id": prev_commit_id,
        "next_commit_id": next_commit_id,
        "branch_commits": [
            {"id": c.commit_id, "msg": c.message[:60], "ts": c.timestamp}
            for c in branch_commits[:10]
        ],
        # Render job
        "render_status": render_job_row.status if render_job_row else None,
        "midi_count": render_job_row.midi_count if render_job_row else 0,
        "mp3_count": len(render_job_row.mp3_object_ids or []) if render_job_row else 0,
        # Matrix
        "instruments": matrix.instruments,
        "sections": matrix.sections,
        "cell_map": cell_map_enriched,
        "row_summaries": matrix.row_summaries,
        "column_summaries": matrix.column_summaries,
        "section_pcts": section_pcts,
        "total_beats": total_beats,
        "total_notes": sum(rs.total_notes for rs in matrix.row_summaries),
        "active_cells": sum(1 for c in cells_enriched if c["active"]),
        "total_cells": len(cells_enriched),
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    context.update(nav_ctx)
    return templates.TemplateResponse(request, "musehub/pages/analysis/compare.html", context)


@router.get(
    "/{owner}/{repo_slug}/divergence",
    summary="MuseHub divergence visualization page",
)
async def divergence_page(  # noqa: C901 (complex but self-contained)
    request: Request,
    owner: str,
    repo_slug: str,
    fork_repo_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the supercharged Musical Analysis page — fully SSR.

    Computes composition profile, emotion averages, dimension activity,
    and pre-runs branch divergence between the default branch and its
    nearest neighbour so the radar chart renders without any client round-trip.
    """
    import math as _math
    import asyncio as _asyncio

    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # --- Fetch branches and commits in parallel -------------------------
    async def _get_branches() -> list[Any]:
        return await musehub_repository.list_branches(db, repo_id)

    async def _get_commits() -> list[Any]:
        r = await db.execute(
            sa_select(musehub_db.MusehubCommit)
            .where(musehub_db.MusehubCommit.repo_id == repo_id)
            .order_by(musehub_db.MusehubCommit.timestamp.desc())
            .limit(500)
        )
        return list(r.scalars())

    branches_list, commits_list = await _asyncio.gather(_get_branches(), _get_commits())

    total_commits: int = len(commits_list)
    total_branches: int = len(branches_list)
    branch_names: list[str] = [b.name for b in branches_list]
    # Which branches actually have commits — used to disable empty branches in UI
    branches_with_commits: set[str] = {c.branch for c in commits_list}
    _DEFAULT_NAMES = ("main", "master", "dev", "develop")
    default_branch: str = next(
        (n for n in _DEFAULT_NAMES if n in branch_names),
        branch_names[0] if branch_names else "main",
    )
    other_branches = [b for b in branch_names if b != default_branch]
    initial_branch_b: str = other_branches[0] if other_branches else default_branch

    # --- Section & track breakdowns from commit messages ---------------
    _SECTION_KW = [
        "intro", "verse", "chorus", "bridge", "outro", "hook",
        "pre-chorus", "breakdown", "drop", "refrain", "coda", "interlude",
    ]
    _TRACK_KW = [
        "bass", "drums", "piano", "guitar", "synth", "pad", "lead",
        "vocals", "strings", "brass", "flute", "cello", "violin",
        "organ", "arp", "melody", "kick", "snare", "keys",
    ]
    section_counts: dict[str, int] = {}
    track_counts: dict[str, int] = {}
    for c in commits_list:
        m = c.message.lower()
        for kw in _SECTION_KW:
            if kw in m:
                section_counts[kw] = section_counts.get(kw, 0) + 1
        for kw in _TRACK_KW:
            if kw in m:
                track_counts[kw] = track_counts.get(kw, 0) + 1

    top_sections: list[tuple[str, int]] = sorted(
        section_counts.items(), key=lambda x: -x[1]
    )[:10]
    top_tracks: list[tuple[str, int]] = sorted(
        track_counts.items(), key=lambda x: -x[1]
    )[:12]
    max_sec = max((c for _, c in top_sections), default=1)
    max_trk = max((c for _, c in top_tracks), default=1)

    # --- Dimension activity from commit message classification ----------
    dim_counts: dict[str, int] = {}
    for c in commits_list:
        for dim in musehub_divergence.classify_message(c.message):
            dim_counts[dim] = dim_counts.get(dim, 0) + 1
    dim_order = ["melodic", "harmonic", "rhythmic", "structural", "dynamic"]
    max_dim = max(dim_counts.values(), default=1)

    # --- Emotion averages (deterministic SHA derivation) ---------------
    def _sha_emo(sha: str) -> tuple[float, float, float]:
        sha = sha.ljust(12, "0")
        return (
            int(sha[0:4], 16) / 0xFFFF,
            int(sha[4:8], 16) / 0xFFFF,
            int(sha[8:12], 16) / 0xFFFF,
        )

    if commits_list:
        emos = [_sha_emo(c.commit_id) for c in commits_list]
        avg_valence = round(sum(e[0] for e in emos) / len(emos), 3)
        avg_energy  = round(sum(e[1] for e in emos) / len(emos), 3)
        avg_tension = round(sum(e[2] for e in emos) / len(emos), 3)
    else:
        avg_valence = avg_energy = avg_tension = 0.5

    # --- Pre-compute branch divergence for initial SSR render ----------
    _ALL_DIMS = ["melodic", "harmonic", "rhythmic", "structural", "dynamic"]
    initial_divergence = None
    radar_score_pts: str = ""
    radar_ring_25: str = ""
    radar_ring_50: str = ""
    radar_ring_75: str = ""
    radar_ring_100: str = ""
    radar_axes: list[dict[str, Any]] = []
    radar_dot_pts: list[dict[str, Any]] = []

    def _make_radar(scores: list[float], r: float = 90.0,
                    cx: float = 120.0, cy: float = 120.0) -> None:
        nonlocal radar_score_pts, radar_ring_25, radar_ring_50, radar_ring_75, radar_ring_100, radar_axes, radar_dot_pts
        n = 5
        angles = [-_math.pi / 2 + (2 * _math.pi / n) * i for i in range(n)]

        def _ring(pct: float) -> str:
            rr = r * pct
            return " ".join(f"{cx + rr * _math.cos(a):.1f},{cy + rr * _math.sin(a):.1f}" for a in angles)

        radar_ring_25  = _ring(0.25)
        radar_ring_50  = _ring(0.50)
        radar_ring_75  = _ring(0.75)
        radar_ring_100 = _ring(1.00)
        radar_score_pts = " ".join(
            f"{cx + s * r * _math.cos(a):.1f},{cy + s * r * _math.sin(a):.1f}"
            for s, a in zip(scores, angles)
        )
        LABELS = ["Melodic", "Harmonic", "Rhythmic", "Structural", "Dynamic"]
        radar_axes = []
        for i, a in enumerate(angles):
            x2 = cx + r * _math.cos(a)
            y2 = cy + r * _math.sin(a)
            tx = cx + r * 1.28 * _math.cos(a)
            ty = cy + r * 1.28 * _math.sin(a)
            anch = "middle" if abs(_math.cos(a)) < 0.2 else ("end" if _math.cos(a) < 0 else "start")
            radar_axes.append({"x2": round(x2, 1), "y2": round(y2, 1),
                                "tx": round(tx, 1), "ty": round(ty, 1),
                                "anchor": anch, "label": LABELS[i]})
        _LEVEL_COLOR = {"NONE": "#6e7681", "LOW": "#58a6ff", "MED": "#e3b341", "HIGH": "#f85149"}
        radar_dot_pts = [
            {
                "x": round(cx + s * r * _math.cos(a), 1),
                "y": round(cy + s * r * _math.sin(a), 1),
                "color": _LEVEL_COLOR.get("NONE", "#6e7681"),
            }
            for s, a in zip(scores, angles)
        ]

    if len(branch_names) >= 2:
        try:
            result = await musehub_divergence.compute_hub_divergence(
                db, repo_id=repo_id, branch_a=default_branch, branch_b=initial_branch_b
            )
            initial_divergence = result
            scores = [d.score for d in result.dimensions]
            _LEVEL_COLOR_MAP = {"NONE": "#6e7681", "LOW": "#58a6ff", "MED": "#e3b341", "HIGH": "#f85149"}
            _make_radar(scores)
            # Patch dot colours with actual levels
            for i, d in enumerate(result.dimensions):
                radar_dot_pts[i]["color"] = _LEVEL_COLOR_MAP.get(d.level.value, "#6e7681")
        except Exception:
            _make_radar([0.0] * 5)
    else:
        _make_radar([0.0] * 5)

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "analysis",
        # Branches
        "branch_names": branch_names,
        "branches_with_commits": branches_with_commits,
        "default_branch": default_branch,
        "initial_branch_b": initial_branch_b,
        "total_branches": total_branches,
        # Commits
        "total_commits": total_commits,
        # Composition profile
        "top_sections": top_sections,
        "top_tracks": top_tracks,
        "max_sec": max_sec,
        "max_trk": max_trk,
        # Dimension activity
        "dim_counts": dim_counts,
        "dim_order": dim_order,
        "max_dim": max_dim,
        # Emotion averages
        "avg_valence": avg_valence,
        "avg_energy": avg_energy,
        "avg_tension": avg_tension,
        # Pre-computed divergence
        "initial_divergence": initial_divergence,
        # Radar SVG geometry (pre-computed Python → Jinja2)
        "radar_score_pts": radar_score_pts,
        "radar_ring_25": radar_ring_25,
        "radar_ring_50": radar_ring_50,
        "radar_ring_75": radar_ring_75,
        "radar_ring_100": radar_ring_100,
        "radar_axes": radar_axes,
        "radar_dot_pts": radar_dot_pts,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # SSR stats — fast parallel queries for the stats bar
    import asyncio as _asyncio

    async def _commit_count() -> int:
        r = await db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubCommit).where(
                musehub_db.MusehubCommit.repo_id == repo_id
            )
        )
        return r.scalar_one_or_none() or 0

    async def _session_count() -> int:
        from musehub.db import musehub_models as _m
        r = await db.execute(
            sa_select(func.count()).select_from(_m.MusehubSession).where(
                _m.MusehubSession.repo_id == repo_id
            )
        )
        return r.scalar_one_or_none() or 0

    total_commits, total_sessions = await _asyncio.gather(
        _commit_count(), _session_count()
    )

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "timeline",
        "total_commits": total_commits,
        "total_sessions": total_sessions,
    }
    ctx.update(nav_ctx)
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
    """Render the supercharged release list page (SSR).

    The latest stable release is highlighted as a hero card in the page shell.
    The HTMX-swappable fragment renders remaining (previous) releases as rich
    cards below the hero.  All data is SSR'd — no client-side fetches needed.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    all_releases = await musehub_releases.list_releases(db, repo_id)

    # Split: hero = latest stable/prerelease (first in newest-first list),
    # list = everything else paginated.
    latest_release = all_releases[0] if all_releases else None
    other_releases = all_releases[1:] if len(all_releases) > 1 else []

    # Paginate the "other releases" list (below the hero).
    total = len(other_releases)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    releases = other_releases[start : start + per_page]

    # Stats for the bar.
    stable_count = sum(
        1 for r in all_releases if not r.is_prerelease and not r.is_draft
    )
    prerelease_count = sum(1 for r in all_releases if r.is_prerelease)
    draft_count = sum(1 for r in all_releases if r.is_draft)
    # Count distinct download format types available across all releases.
    formats_available: list[str] = []
    for r in all_releases:
        if r.download_urls.midi_bundle:
            formats_available.append("MIDI")
            break
    for r in all_releases:
        if r.download_urls.mp3:
            formats_available.append("MP3")
            break
    for r in all_releases:
        if r.download_urls.stems:
            formats_available.append("Stems")
            break
    for r in all_releases:
        if r.download_urls.musicxml:
            formats_available.append("MusicXML")
            break

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "releases",
        "releases": releases,
        "total": len(all_releases),
        "other_count": total,
        "page": page,
        "total_pages": total_pages,
        "latest_release": latest_release,
        # Stats
        "stable_count": stable_count,
        "prerelease_count": prerelease_count,
        "draft_count": draft_count,
        "formats_available": formats_available,
    }
    ctx.update(nav_ctx)
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
    pr_ct, issue_ct = await asyncio.gather(
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubPullRequest).where(
                musehub_db.MusehubPullRequest.repo_id == repo_id,
                musehub_db.MusehubPullRequest.state == "open",
            )
        ),
        db.execute(
            sa_select(func.count()).select_from(musehub_db.MusehubIssue).where(
                musehub_db.MusehubIssue.repo_id == repo_id,
                musehub_db.MusehubIssue.state == "open",
            )
        ),
    )
    nav_ctx_release: dict[str, Any] = {
        "repo_key": repo.key_signature or "",
        "repo_bpm": repo.tempo_bpm,
        "repo_tags": repo.tags or [],
        "repo_visibility": repo.visibility or "private",
        "nav_open_pr_count": pr_ct.scalar_one_or_none() or 0,
        "nav_open_issue_count": issue_ct.scalar_one_or_none() or 0,
    }
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
    ctx.update(nav_ctx_release)
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
    """Render the supercharged session log page (SSR).

    Fetches all sessions for stats computation (total hours, commits captured,
    unique collaborators) and the paginated slice for display.  Active sessions
    float to the top.  Stats are SSR'd in the page shell; the fragment carries
    paginated session cards for HTMX swapping.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # Fetch all sessions for aggregate stats (repos rarely exceed a few hundred).
    all_sessions, total = await musehub_repository.list_sessions(
        db, repo_id, limit=1000, offset=0
    )

    # Aggregate stats across all sessions.
    active_sessions = [s for s in all_sessions if s.is_active]
    ended_sessions  = [s for s in all_sessions if not s.is_active]
    total_hours = sum(
        (s.duration_seconds or 0) for s in all_sessions
    ) / 3600.0
    total_commits_in_sessions = sum(len(s.commits) for s in all_sessions)
    unique_collaborators = sorted(
        {p for s in all_sessions for p in s.participants}
    )

    # Paginated slice for the fragment.
    offset = (page - 1) * per_page
    paginated = all_sessions[offset : offset + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Most-recently-used locations for the sidebar vocabulary.
    seen_locs: list[str] = []
    for s in all_sessions:
        if s.location and s.location not in seen_locs:
            seen_locs.append(s.location)
    top_locations = seen_locs[:6]

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "sessions",
        "sessions": [s.model_dump(by_alias=True, mode="json") for s in paginated],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        # Stats
        "active_count": len(active_sessions),
        "ended_count": len(ended_sessions),
        "total_hours": round(total_hours, 1),
        "total_commits_in_sessions": total_commits_in_sessions,
        "unique_collaborators": unique_collaborators,
        "top_locations": top_locations,
        # Live sessions for the hero (first active session if any)
        "live_session": (
            active_sessions[0].model_dump(by_alias=True, mode="json")
            if active_sessions else None
        ),
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    """Render the fully server-side-rendered repo insights dashboard.

    All metrics — commit heatmap, branch activity, contributor leaderboard,
    PR/issue health, musical evolution, session analytics, and release cadence
    — are pre-computed in parallel here and passed to the Jinja2 template.
    No client-side API calls needed for the initial render.
    """
    import re as _re
    from datetime import date as _date, timedelta as _td, timezone as _tz

    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # ── Parallel DB fetches ─────────────────────────────────────────────────
    async def _q_commits() -> list[Any]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubCommit.commit_id,
                musehub_db.MusehubCommit.branch,
                musehub_db.MusehubCommit.author,
                musehub_db.MusehubCommit.timestamp,
                musehub_db.MusehubCommit.message,
            ).where(musehub_db.MusehubCommit.repo_id == repo_id)
            .order_by(musehub_db.MusehubCommit.timestamp.asc())
        )).all()
        return list(rows)

    async def _q_branches() -> list[Any]:
        rows = (await db.execute(
            sa_select(musehub_db.MusehubBranch.name)
            .where(musehub_db.MusehubBranch.repo_id == repo_id)
        )).scalars().all()
        return list(rows)

    async def _q_issues() -> list[Any]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubIssue.state,
                musehub_db.MusehubIssue.created_at,
                musehub_db.MusehubIssue.updated_at,
            ).where(musehub_db.MusehubIssue.repo_id == repo_id)
        )).all()
        return list(rows)

    async def _q_prs() -> list[Any]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubPullRequest.state,
                musehub_db.MusehubPullRequest.created_at,
                musehub_db.MusehubPullRequest.merged_at,
            ).where(musehub_db.MusehubPullRequest.repo_id == repo_id)
        )).all()
        return list(rows)

    async def _q_releases() -> list[Any]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubRelease.tag,
                musehub_db.MusehubRelease.title,
                musehub_db.MusehubRelease.is_prerelease,
                musehub_db.MusehubRelease.is_draft,
                musehub_db.MusehubRelease.created_at,
            ).where(musehub_db.MusehubRelease.repo_id == repo_id)
            .order_by(musehub_db.MusehubRelease.created_at.desc())
        )).all()
        return list(rows)

    async def _q_sessions() -> list[Any]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubSession.started_at,
                musehub_db.MusehubSession.ended_at,
                musehub_db.MusehubSession.participants,
                musehub_db.MusehubSession.location,
                musehub_db.MusehubSession.is_active,
            ).where(musehub_db.MusehubSession.repo_id == repo_id)
            .order_by(musehub_db.MusehubSession.started_at.desc())
        )).all()
        return list(rows)

    async def _q_stars() -> int:
        return await db.scalar(
            sa_select(func.count()).select_from(musehub_db.MusehubStar)
            .where(musehub_db.MusehubStar.repo_id == repo_id)
        ) or 0

    async def _q_forks() -> int:
        return await db.scalar(
            sa_select(func.count()).select_from(musehub_db.MusehubFork)
            .where(musehub_db.MusehubFork.source_repo_id == repo_id)
        ) or 0

    (
        commits_raw, branches_raw, issues_raw, prs_raw,
        releases_raw, sessions_raw, star_count, fork_count,
    ) = await asyncio.gather(
        _q_commits(), _q_branches(), _q_issues(), _q_prs(),
        _q_releases(), _q_sessions(), _q_stars(), _q_forks(),
    )

    # ── Heatmap: 52 weeks × 7 days ─────────────────────────────────────────
    today = _date.today()
    # Start on the nearest past Sunday covering 364 days
    _start_offset = (today.weekday() + 1) % 7  # days since last Sunday
    heatmap_start = today - _td(days=364 + _start_offset)
    commit_by_date: dict[str, int] = {}
    for c in commits_raw:
        dk = c.timestamp.date().isoformat()
        commit_by_date[dk] = commit_by_date.get(dk, 0) + 1

    heatmap_weeks: list[list[dict[str, Any]]] = []
    for w in range(53):
        week: list[dict[str, Any]] = []
        for d in range(7):
            cell_date = heatmap_start + _td(days=w * 7 + d)
            if cell_date > today:
                week.append({"date": "", "count": -1})  # future: skip
            else:
                cnt = commit_by_date.get(cell_date.isoformat(), 0)
                level = 0 if cnt == 0 else (1 if cnt == 1 else (2 if cnt <= 3 else (3 if cnt <= 6 else 4)))
                week.append({"date": cell_date.isoformat(), "count": cnt, "level": level})
        heatmap_weeks.append(week)

    commits_last_year = sum(
        1 for c in commits_raw
        if c.timestamp.date() >= (today - _td(days=365))
    )

    # ── Branch activity ─────────────────────────────────────────────────────
    branch_commit_counts: dict[str, int] = {}
    for c in commits_raw:
        branch_commit_counts[c.branch] = branch_commit_counts.get(c.branch, 0) + 1
    max_branch_commits = max(branch_commit_counts.values(), default=1)
    top_branches = sorted(branch_commit_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    branch_bars: list[dict[str, Any]] = [
        {
            "name": name,
            "count": cnt,
            "pct": round(cnt / max_branch_commits * 100),
        }
        for name, cnt in top_branches
    ]

    # ── Contributor leaderboard ─────────────────────────────────────────────
    author_commit_counts: dict[str, int] = {}
    for c in commits_raw:
        author_commit_counts[c.author] = author_commit_counts.get(c.author, 0) + 1
    max_author_commits = max(author_commit_counts.values(), default=1)
    top_authors = sorted(author_commit_counts.items(), key=lambda x: x[1], reverse=True)[:8]
    contributor_bars: list[dict[str, Any]] = [
        {
            "name": name,
            "count": cnt,
            "pct": round(cnt / max_author_commits * 100),
            "avatar_letter": name[0].upper() if name else "?",
        }
        for name, cnt in top_authors
    ]

    # ── Issue & PR health ───────────────────────────────────────────────────
    open_issues = sum(1 for i in issues_raw if i.state == "open")
    closed_issues = sum(1 for i in issues_raw if i.state == "closed")
    total_issues = len(issues_raw)
    issue_close_rate = round(closed_issues / total_issues * 100) if total_issues else 0

    open_prs = sum(1 for p in prs_raw if p.state == "open")
    merged_prs = sum(1 for p in prs_raw if p.state == "merged")
    closed_prs = sum(1 for p in prs_raw if p.state == "closed")
    total_prs = len(prs_raw)
    pr_merge_rate = round(merged_prs / total_prs * 100) if total_prs else 0

    # Average time to merge (for merged PRs that have both created_at and merged_at)
    merge_times_days: list[float] = [
        (p.merged_at - p.created_at).total_seconds() / 86400
        for p in prs_raw
        if p.state == "merged" and p.merged_at and p.created_at
    ]
    avg_merge_days = round(sum(merge_times_days) / len(merge_times_days), 1) if merge_times_days else None

    # ── Musical evolution: BPM timeline ────────────────────────────────────
    _BPM_RE = _re.compile(r'\b(?:bpm|tempo)[:\s=](\d+)', _re.IGNORECASE)
    bpm_points: list[dict[str, Any]] = []
    for c in commits_raw:
        m = _BPM_RE.search(c.message or "")
        if m:
            bpm_val = int(m.group(1))
            if 20 <= bpm_val <= 300:
                bpm_points.append({"ts": c.timestamp.isoformat(), "bpm": bpm_val})

    # Build SVG polyline for BPM — 600×80 viewport
    bpm_svg: str = ""
    if len(bpm_points) >= 2:
        bpms = [p["bpm"] for p in bpm_points]
        bpm_min, bpm_max = min(bpms), max(bpms)
        bpm_range = max(bpm_max - bpm_min, 10)
        pts: list[str] = []
        for i, p in enumerate(bpm_points):
            x = round(i / (len(bpm_points) - 1) * 580 + 10, 1)
            y = round((1 - (p["bpm"] - bpm_min) / bpm_range) * 60 + 10, 1)
            pts.append(f"{x},{y}")
        bpm_svg = " ".join(pts)

    # Key signature changes timeline
    _KEY_RE = _re.compile(r'\b(?:key|signature)[:\s=]([A-G][b#]?\s*(?:major|minor|maj|min)?)', _re.IGNORECASE)
    key_changes: list[dict[str, str]] = []
    for c in commits_raw:
        m = _KEY_RE.search(c.message or "")
        if m:
            key_changes.append({"ts": c.timestamp.date().isoformat(), "key": m.group(1).strip()})

    # ── Session analytics ───────────────────────────────────────────────────
    total_sessions = len(sessions_raw)
    active_sessions = sum(1 for s in sessions_raw if s.is_active)
    session_durations_h: list[float] = [
        (s.ended_at - s.started_at).total_seconds() / 3600
        for s in sessions_raw
        if s.ended_at and s.started_at and not s.is_active
    ]
    avg_session_h = round(sum(session_durations_h) / len(session_durations_h), 1) if session_durations_h else 0

    location_counts: dict[str, int] = {}
    for s in sessions_raw:
        loc = (s.location or "").strip()
        if loc:
            location_counts[loc] = location_counts.get(loc, 0) + 1
    top_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    all_participants: set[str] = set()
    for s in sessions_raw:
        for p in (s.participants or []):
            if p:
                all_participants.add(p)

    # ── Release cadence ─────────────────────────────────────────────────────
    stable_releases = sum(1 for r in releases_raw if not r.is_prerelease and not r.is_draft)
    prerelease_count = sum(1 for r in releases_raw if r.is_prerelease)
    draft_count = sum(1 for r in releases_raw if r.is_draft)
    recent_releases: list[dict[str, Any]] = [
        {
            "tag": r.tag,
            "title": r.title or r.tag,
            "is_prerelease": r.is_prerelease,
            "is_draft": r.is_draft,
            "date": r.created_at.date().isoformat() if r.created_at else "",
        }
        for r in releases_raw[:6]
    ]

    # ── Velocity metrics ────────────────────────────────────────────────────
    commits_last_30 = sum(
        1 for c in commits_raw
        if c.timestamp.date() >= (today - _td(days=30))
    )
    commits_last_7 = sum(
        1 for c in commits_raw
        if c.timestamp.date() >= (today - _td(days=7))
    )
    # Average commits per week (using last 12 weeks)
    commits_last_84 = sum(
        1 for c in commits_raw
        if c.timestamp.date() >= (today - _td(days=84))
    )
    avg_commits_per_week = round(commits_last_84 / 12, 1)

    # ── Top-level stats ─────────────────────────────────────────────────────
    total_commits = len(commits_raw)
    total_branches = len(branches_raw)
    total_releases = len(releases_raw)
    unique_contributors = len(author_commit_counts)

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "insights",
        # Stats bar
        "total_commits": total_commits,
        "total_branches": total_branches,
        "total_releases": total_releases,
        "total_sessions": total_sessions,
        "star_count": star_count,
        "fork_count": fork_count,
        "unique_contributors": unique_contributors,
        # Velocity
        "commits_last_7": commits_last_7,
        "commits_last_30": commits_last_30,
        "avg_commits_per_week": avg_commits_per_week,
        "commits_last_year": commits_last_year,
        # Heatmap
        "heatmap_weeks": heatmap_weeks,
        # Branch activity
        "branch_bars": branch_bars,
        # Contributor bars
        "contributor_bars": contributor_bars,
        # Issue health
        "open_issues": open_issues,
        "closed_issues": closed_issues,
        "total_issues": total_issues,
        "issue_close_rate": issue_close_rate,
        # PR health
        "open_prs": open_prs,
        "merged_prs": merged_prs,
        "closed_prs": closed_prs,
        "total_prs": total_prs,
        "pr_merge_rate": pr_merge_rate,
        "avg_merge_days": avg_merge_days,
        # Musical evolution
        "bpm_points": bpm_points,
        "bpm_svg": bpm_svg,
        "bpm_min": min((p["bpm"] for p in bpm_points), default=0),
        "bpm_max": max((p["bpm"] for p in bpm_points), default=0),
        "key_changes": key_changes,
        # Sessions
        "active_sessions": active_sessions,
        "avg_session_h": avg_session_h,
        "top_locations": top_locations,
        "unique_participants": len(all_participants),
        # Releases
        "stable_releases": stable_releases,
        "prerelease_count": prerelease_count,
        "draft_count": draft_count,
        "recent_releases": recent_releases,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "dir_path": "",
        "base_url": base_url,
        "current_page": "tree",
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "ref": ref,
        "dir_path": path,
        "base_url": base_url,
        "current_page": "tree",
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "groove-check",
    }
    ctx.update(nav_ctx)
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
    """Render the supercharged branch list page (SSR).

    Lists all branches enriched with HEAD commit metadata (author, timestamp,
    message preview), ahead/behind counts, branch type classification, and
    repository-level stats.  All data is SSR'd — no client-side API fetches.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    branch_data: BranchDetailListResponse = (
        await musehub_repository.list_branches_with_detail(db, repo_id)
    )
    if format == "json" or "application/json" in request.headers.get("accept", ""):
        return JSONResponse(branch_data.model_dump(by_alias=True, mode="json"))

    # Fetch HEAD commit metadata for all branches in a single query.
    head_ids = [b.head_commit_id for b in branch_data.branches if b.head_commit_id]
    commit_meta: dict[str, dict[str, Any]] = {}
    if head_ids:
        rows = (
            await db.execute(
                sa_select(
                    musehub_db.MusehubCommit.commit_id,
                    musehub_db.MusehubCommit.author,
                    musehub_db.MusehubCommit.timestamp,
                    musehub_db.MusehubCommit.message,
                ).where(musehub_db.MusehubCommit.commit_id.in_(head_ids))
            )
        ).all()
        for row in rows:
            commit_meta[row.commit_id] = {
                "author": row.author or "",
                "timestamp": row.timestamp,
                "message": (row.message or "").split("\n")[0][:80],
            }

    def _branch_type(name: str) -> str:
        n = name.lower()
        if n in ("main", "master", "dev", "develop"):
            return "default"
        if "feat" in n or "feature" in n:
            return "feature"
        if "experiment" in n or "remix" in n or "fusion" in n:
            return "experiment"
        if n.startswith("source-"):
            return "source"
        if any(
            x in n
            for x in ["analysis", "counterpoint", "ornament", "bassline", "arrangement"]
        ):
            return "collab"
        if any(
            x in n
            for x in [
                "mvt", "prelude", "fugue", "aria", "variation", "nocturne",
                "sonata", "march", "allegro", "adagio", "presto", "theme", "waltz",
            ]
        ) or (n.startswith("op") and len(n) > 2 and n[2].isdigit()):
            return "structure"
        if (n.startswith("v") and len(n) > 1 and n[1].isdigit()) or any(
            x in n for x in ["version", "slow-", "house-", "trap-", "swing-", "electro-"]
        ):
            return "version"
        return "feature"

    # Annotate each branch with its type for the template.
    branch_type_map: dict[str, str] = {
        b.name: _branch_type(b.name) for b in branch_data.branches
    }

    # Compute type counts (exclude default branch from per-type tabs).
    from collections import Counter as _Counter
    type_counts: dict[str, int] = _Counter(
        branch_type_map[b.name]
        for b in branch_data.branches
        if not b.is_default
    )

    default_branch = next((b for b in branch_data.branches if b.is_default), None)
    non_default = [b for b in branch_data.branches if not b.is_default]

    # Repo-level stats for the stats bar.
    active_count = len(non_default)
    ahead_count = sum(1 for b in non_default if b.ahead_count > 0)
    unique_authors = len({
        commit_meta[b.head_commit_id]["author"]
        for b in branch_data.branches
        if b.head_commit_id and b.head_commit_id in commit_meta
        and commit_meta[b.head_commit_id]["author"]
    })

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "branches",
        "branches": branch_data.branches,
        "default_branch": default_branch,
        "commit_meta": commit_meta,
        "branch_type_map": branch_type_map,
        "type_counts": type_counts,
        # Stats bar
        "total_branch_count": len(branch_data.branches),
        "active_branch_count": active_count,
        "ahead_branch_count": ahead_count,
        "unique_author_count": unique_authors,
    }
    ctx.update(nav_ctx)
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
    sort: str | None = Query(None, description="Sort order: 'newest' (default), 'alpha', 'namespace'"),
    format: str | None = Query(None, description="Force response format: 'json' or omit for HTML"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the supercharged tag browser page (SSR).

    Tags are derived from repo releases (tag field) plus repo semantic tags
    (stored on the repo row).  Release tags without a ``:`` prefix fall into
    the ``version`` namespace.  Semantic repo tags with a ``:`` are grouped by
    their prefix (``genre``, ``emotion``, ``stage``, ``key``, ``tempo``, etc.)
    and shown as a vocabulary vocabulary overview.  The optional ``?namespace``
    query parameter filters the release-tag list.
    """
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
    releases = await musehub_releases.list_releases(db, repo_id)

    # Build release-tag objects — keep full release data for rich card display.
    # Map tag_str → release so the template can access download_urls, author, etc.
    release_by_tag: dict[str, object] = {r.tag: r for r in releases}

    all_tags: list[TagResponse] = []
    for release in releases:
        tag_str = release.tag
        ns = tag_str.split(":", 1)[0] if ":" in tag_str else "version"
        all_tags.append(
            TagResponse(
                tag=tag_str,
                namespace=ns,
                commit_id=release.commit_id,
                message=release.title,
                created_at=release.created_at,
            )
        )

    # Sort.
    active_sort = sort or "newest"
    if active_sort == "alpha":
        all_tags.sort(key=lambda t: t.tag)
    elif active_sort == "namespace":
        all_tags.sort(key=lambda t: (t.namespace, t.tag))
    # default: newest first (releases already ordered by created_at desc)

    # Namespace filter.
    filtered_tags = [t for t in all_tags if t.namespace == namespace] if namespace else all_tags

    namespaces: list[str] = sorted({t.namespace for t in all_tags})

    # Per-namespace counts for the sidebar.
    from collections import Counter as _Counter
    ns_counts: dict[str, int] = _Counter(t.namespace for t in all_tags)

    # Stats.
    stable_count = sum(
        1 for r in releases if not r.is_prerelease and not r.is_draft
    )
    prerelease_count = sum(1 for r in releases if r.is_prerelease)
    draft_count = sum(1 for r in releases if r.is_draft)

    if format == "json" or "application/json" in request.headers.get("accept", ""):
        tag_list = TagListResponse(tags=filtered_tags, namespaces=namespaces)
        return JSONResponse(tag_list.model_dump(by_alias=True, mode="json"))

    ctx: dict[str, object] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "tags",           # fixed: was "releases"
        "tags": filtered_tags,
        "all_tags": all_tags,
        "namespaces": namespaces,
        "ns_counts": ns_counts,
        "active_namespace": namespace or "",
        "active_sort": active_sort,
        "release_by_tag": release_by_tag,
        # Stats bar
        "total_tag_count": len(all_tags),
        "namespace_count": len(namespaces),
        "stable_count": stable_count,
        "prerelease_count": prerelease_count,
        "draft_count": draft_count,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
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
    """Render the repo-level activity feed with a rich, date-grouped timeline.

    Pre-fetches events, per-type counts, unique actor count, and date range in
    parallel.  Groups events by calendar date for the template.  HTMX fragment
    requests receive only the ``activity_rows.html`` fragment (event list +
    filter pills + pagination); direct browser nav gets the full page.

    No JWT required — activity data is publicly readable.
    """
    from datetime import date as _date, timedelta as _td

    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)

    # ── Parallel queries ────────────────────────────────────────────────────
    async def _q_feed() -> Any:
        return await musehub_events.list_events(
            db, repo_id,
            event_type=event_type or None,
            page=page,
            page_size=per_page,
        )

    async def _q_type_counts() -> dict[str, int]:
        rows = (await db.execute(
            sa_select(
                musehub_db.MusehubEvent.event_type,
                func.count().label("cnt"),
            ).where(musehub_db.MusehubEvent.repo_id == repo_id)
            .group_by(musehub_db.MusehubEvent.event_type)
        )).all()
        return {r.event_type: r.cnt for r in rows}

    async def _q_unique_actors() -> int:
        return await db.scalar(
            sa_select(func.count(musehub_db.MusehubEvent.actor.distinct()))
            .where(musehub_db.MusehubEvent.repo_id == repo_id)
        ) or 0

    async def _q_date_range() -> tuple[Any, Any]:
        row = (await db.execute(
            sa_select(
                func.min(musehub_db.MusehubEvent.created_at),
                func.max(musehub_db.MusehubEvent.created_at),
            ).where(musehub_db.MusehubEvent.repo_id == repo_id)
        )).first()
        return (row[0] if row else None, row[1] if row else None)

    feed, type_counts, unique_actors, (first_event_at, last_event_at) = await asyncio.gather(
        _q_feed(), _q_type_counts(), _q_unique_actors(), _q_date_range(),
    )

    # ── Group events by calendar date ───────────────────────────────────────
    today     = _date.today()
    yesterday = today - _td(days=1)

    def _date_label(dt: Any) -> str:
        d = dt.date() if hasattr(dt, "date") else dt
        if d == today:
            return "Today"
        if d == yesterday:
            return "Yesterday"
        return f"{d.strftime('%B')} {d.day}, {d.year}"

    event_groups: list[dict[str, Any]] = []
    current_label: str | None = None
    current_group: dict[str, Any] = {}
    for ev in feed.events:
        lbl = _date_label(ev.created_at)
        if lbl != current_label:
            current_label = lbl
            current_group = {"label": lbl, "events": []}
            event_groups.append(current_group)
        current_group["events"].append(ev)

    total_pages = max(1, (feed.total + per_page - 1) // per_page)

    # Build per-type pill data sorted by count desc
    type_pills: list[dict[str, Any]] = [
        {"type": t, "count": type_counts.get(t, 0)}
        for t in sorted(musehub_events.KNOWN_EVENT_TYPES, key=lambda x: type_counts.get(x, 0), reverse=True)
    ]
    total_all = sum(type_counts.values())

    ctx: dict[str, Any] = {
        "owner": owner,
        "repo_slug": repo_slug,
        "repo_id": repo_id,
        "base_url": base_url,
        "current_page": "activity",
        # Feed
        "events": feed.events,
        "event_groups": event_groups,
        "total": feed.total,
        "total_all": total_all,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        # Filters
        "event_type": event_type or "",
        "event_types": sorted(musehub_events.KNOWN_EVENT_TYPES),
        "type_pills": type_pills,
        # Stats
        "unique_actors": unique_actors,
        "first_event_at": first_event_at,
        "last_event_at": last_event_at,
    }
    ctx.update(nav_ctx)
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
    repo_id, base_url, nav_ctx = await _resolve_repo(owner, repo_slug, db)
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
    ctx.update(nav_ctx)
    return json_or_html(
        request,
        lambda: templates.TemplateResponse(request, "musehub/pages/score.html", ctx),
        ctx,
    )

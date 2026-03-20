"""Generic domain viewer and insights UI routes.

Routes:
  GET /{owner}/{repo}/view/{ref}               — universal domain viewer
  GET /{owner}/{repo}/view/{ref}/{path:path}   — domain viewer for a specific file
  GET /{owner}/{repo}/insights/{ref}            — domain insights dashboard
  GET /{owner}/{repo}/insights/{ref}/{dim}      — single insight dimension

Redirect routes (301):
  GET /{owner}/{repo}/piano-roll/{ref}          → view/{ref}
  GET /{owner}/{repo}/listen/{ref}              → view/{ref}
  GET /{owner}/{repo}/arrange/{ref}             → view/{ref}
  GET /{owner}/{repo}/analysis/{ref}            → insights/{ref}
  GET /{owner}/{repo}/analysis/{ref}/{dim}      → insights/{ref}/{dim}

The ``view`` route delegates rendering to the domain's ``viewer_type``:
  - piano_roll   (MIDI)     → renders piano roll canvas via the TypeScript module
  - symbol_graph (Code)     → renders symbol dependency graph
  - generic      (fallback) → renders file tree

The ``insights`` route populates dimension tabs from ``domain.capabilities.dimensions``.
MIDI repos show harmony/rhythm/groove/etc; code repos show hotspots/coupling/symbols/etc.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select as sa_select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from musehub.api.routes.musehub._templates import templates as _templates
from musehub.api.routes.musehub._nav_ctx import build_repo_nav_ctx
from musehub.api.routes.musehub.htmx_helpers import htmx_fragment_or_full
from musehub.db import get_db
from musehub.db import musehub_models as musehub_db
from musehub.services import musehub_repository, musehub_domains, musehub_analysis

logger = logging.getLogger(__name__)

# Two separate routers: fixed_router for redirect paths, wildcard_router for the new paths.
# Both are exported and registered in main.py.
view_router = APIRouter(prefix="", tags=["musehub-ui-view"])
redirect_router = APIRouter(prefix="", tags=["musehub-ui-redirects"])


# ── Redirect routes (301) ─────────────────────────────────────────────────────


@redirect_router.get(
    "/{owner}/{repo_slug}/piano-roll/{ref:path}",
    include_in_schema=False,
)
async def redirect_piano_roll(owner: str, repo_slug: str, ref: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{owner}/{repo_slug}/view/{ref}",
        status_code=301,
    )


@redirect_router.get(
    "/{owner}/{repo_slug}/listen/{ref:path}",
    include_in_schema=False,
)
async def redirect_listen(owner: str, repo_slug: str, ref: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{owner}/{repo_slug}/view/{ref}",
        status_code=301,
    )


@redirect_router.get(
    "/{owner}/{repo_slug}/arrange/{ref:path}",
    include_in_schema=False,
)
async def redirect_arrange(owner: str, repo_slug: str, ref: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{owner}/{repo_slug}/view/{ref}",
        status_code=301,
    )


@redirect_router.get(
    "/{owner}/{repo_slug}/analysis/{ref}/{dim}",
    include_in_schema=False,
)
async def redirect_analysis_dim(owner: str, repo_slug: str, ref: str, dim: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{owner}/{repo_slug}/insights/{ref}/{dim}",
        status_code=301,
    )


@redirect_router.get(
    "/{owner}/{repo_slug}/analysis/{ref}",
    include_in_schema=False,
)
async def redirect_analysis(owner: str, repo_slug: str, ref: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/{owner}/{repo_slug}/insights/{ref}",
        status_code=301,
    )


# ── View route ────────────────────────────────────────────────────────────────


async def _get_domain_for_repo(
    db: AsyncSession,
    repo_id: str,
    domain_id: str | None,
) -> dict[str, object]:
    """Return domain capabilities dict for a repo, falling back to generic."""
    if not domain_id:
        return {
            "scoped_id": None,
            "display_name": "Generic",
            "viewer_type": "generic",
            "dimensions": [],
        }
    domain = await musehub_domains.get_domain_by_id(db, domain_id)
    if domain is None:
        return {
            "scoped_id": None,
            "display_name": "Generic",
            "viewer_type": "generic",
            "dimensions": [],
        }
    return {
        "scoped_id": domain.scoped_id,
        "display_name": domain.display_name,
        "viewer_type": domain.viewer_type,
        "dimensions": domain.capabilities.get("dimensions", []),
    }


@view_router.get(
    "/{owner}/{repo_slug}/view/{ref}",
    response_class=HTMLResponse,
    summary="Universal domain viewer",
    operation_id="domainViewerPage",
)
async def domain_viewer_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    format: str = "html",
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the universal domain viewer for a repository at a given ref.

    The viewer adapts to the repo's domain plugin:
    - MIDI domain → piano roll canvas (21-dimensional state)
    - Code domain → symbol dependency graph
    - Generic      → file tree fallback
    """
    repo = await musehub_repository.get_repo_by_owner_slug(db, owner, repo_slug)
    if repo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository not found.")

    nav_ctx = await build_repo_nav_ctx(db, repo, owner, repo_slug)
    domain_ctx = await _get_domain_for_repo(db, repo.repo_id, repo.domain_id)

    # Determine page_json for the TypeScript view module
    page_json: dict[str, object] = {
        "repoId": repo.repo_id,
        "owner": owner,
        "slug": repo_slug,
        "ref": ref,
        "viewerType": domain_ctx["viewer_type"],
        "domainScopedId": domain_ctx["scoped_id"],
        "domainDisplayName": domain_ctx["display_name"],
    }

    if format == "json":
        from fastapi.responses import JSONResponse
        return JSONResponse(content=page_json)

    ctx: dict[str, object] = {
        "title": f"View · {owner}/{repo_slug}@{ref}",
        "current_page": "view",
        "repo": repo,
        "owner": owner,
        "repo_slug": repo_slug,
        "ref": ref,
        "domain": domain_ctx,
        "muse_resource_uri": f"muse://repos/{owner}/{repo_slug}",
        **nav_ctx,
    }
    return _templates.TemplateResponse(
        request, "musehub/pages/view.html", ctx,
        headers={"X-Page-Json": str(page_json)},
    )


@view_router.get(
    "/{owner}/{repo_slug}/view/{ref}/{path:path}",
    response_class=HTMLResponse,
    summary="Universal domain viewer — specific file",
    operation_id="domainViewerFilePage",
    include_in_schema=False,
)
async def domain_viewer_file_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    path: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the viewer for a specific file within the snapshot."""
    repo = await musehub_repository.get_repo_by_owner_slug(db, owner, repo_slug)
    if repo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository not found.")

    nav_ctx = await build_repo_nav_ctx(db, repo, owner, repo_slug)
    domain_ctx = await _get_domain_for_repo(db, repo.repo_id, repo.domain_id)

    page_json: dict[str, object] = {
        "repoId": repo.repo_id,
        "owner": owner,
        "slug": repo_slug,
        "ref": ref,
        "path": path,
        "viewerType": domain_ctx["viewer_type"],
        "domainScopedId": domain_ctx["scoped_id"],
        "domainDisplayName": domain_ctx["display_name"],
    }

    ctx: dict[str, object] = {
        "title": f"View · {owner}/{repo_slug}@{ref}/{path}",
        "current_page": "view",
        "repo": repo,
        "owner": owner,
        "repo_slug": repo_slug,
        "ref": ref,
        "path": path,
        "domain": domain_ctx,
        "muse_resource_uri": f"muse://repos/{owner}/{repo_slug}",
        **nav_ctx,
    }
    return _templates.TemplateResponse(
        request, "musehub/pages/view.html", ctx,
        headers={"X-Page-Json": str(page_json)},
    )


# ── Insights data helpers ─────────────────────────────────────────────────────

_EXT_TO_LANG: dict[str, str] = {
    "py": "Python", "ts": "TypeScript", "tsx": "TypeScript",
    "js": "JavaScript", "jsx": "JavaScript", "mjs": "JavaScript",
    "rs": "Rust", "go": "Go", "swift": "Swift", "kt": "Kotlin",
    "java": "Java", "rb": "Ruby", "cpp": "C++", "cc": "C++",
    "c": "C", "h": "C/C++", "hpp": "C++", "hs": "Haskell",
    "md": "Markdown", "rst": "reStructuredText",
    "json": "JSON", "yaml": "YAML", "yml": "YAML", "toml": "TOML",
    "sh": "Shell", "bash": "Shell", "zsh": "Shell",
    "html": "HTML", "css": "CSS", "scss": "SCSS", "sql": "SQL",
    "txt": "Text", "xml": "XML",
}

_LANG_COLORS: dict[str, str] = {
    "Python": "#3572A5", "TypeScript": "#2b7489", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Go": "#00ADD8", "Swift": "#ffac45", "Kotlin": "#F18E33",
    "Java": "#b07219", "Ruby": "#701516", "C++": "#f34b7d", "C": "#555555",
    "C/C++": "#f34b7d", "Haskell": "#5e5086", "Markdown": "#083fa1",
    "YAML": "#cb171e", "TOML": "#9c4221", "JSON": "#292929", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "SCSS": "#c6538c", "SQL": "#e38c00",
}

_TEST_PATTERNS = frozenset(["test_", "_test.", ".test.", ".spec.", "tests/", "test/", "__tests__"])
_DOC_EXTS = frozenset(["md", "rst", "txt"])
_CODE_EXTS = frozenset(_EXT_TO_LANG.keys()) - _DOC_EXTS - frozenset(["json", "yaml", "yml", "toml", "xml"])


async def _compute_code_insights(db: AsyncSession, repo_id: str) -> dict[str, Any]:
    """Compute code-domain insight metrics from stored objects + commits."""
    objects_rows = (await db.execute(
        sa_select(musehub_db.MusehubObject.path, musehub_db.MusehubObject.size_bytes)
        .where(musehub_db.MusehubObject.repo_id == repo_id)
    )).all()

    commits_rows = (await db.execute(
        sa_select(musehub_db.MusehubCommit.author, musehub_db.MusehubCommit.timestamp,
                  musehub_db.MusehubCommit.branch, musehub_db.MusehubCommit.message)
        .where(musehub_db.MusehubCommit.repo_id == repo_id)
        .order_by(musehub_db.MusehubCommit.timestamp.desc())
    )).all()

    branches_count = (await db.execute(
        sa_select(func.count()).select_from(musehub_db.MusehubBranch)
        .where(musehub_db.MusehubBranch.repo_id == repo_id)
    )).scalar_one_or_none() or 0

    # ── File metrics ──
    lang_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "bytes": 0, "files": []})
    test_files, doc_files, total_bytes = [], [], 0
    largest_files: list[dict[str, Any]] = []

    for path, size in objects_rows:
        ext = Path(path).suffix.lstrip(".").lower()
        lang = _EXT_TO_LANG.get(ext, "Other")
        lang_stats[lang]["count"] += 1
        lang_stats[lang]["bytes"] += (size or 0)
        lang_stats[lang]["files"].append(path)
        total_bytes += size or 0

        is_test = any(p in path.lower() for p in _TEST_PATTERNS)
        if is_test:
            test_files.append({"path": path, "size": size or 0})
        if ext in _DOC_EXTS:
            doc_files.append({"path": path, "size": size or 0})

        largest_files.append({"path": path, "size": size or 0, "lang": lang})

    largest_files.sort(key=lambda f: f["size"], reverse=True)

    total_files = len(objects_rows)
    max_lang_count = max((v["count"] for v in lang_stats.values()), default=1)

    # Sort languages by file count desc, build display-ready list
    languages = sorted(
        [
            {
                "name": name,
                "count": s["count"],
                "bytes": s["bytes"],
                "pct": round(s["count"] / total_files * 100, 1) if total_files else 0,
                "pct_bytes": round(s["bytes"] / total_bytes * 100, 1) if total_bytes else 0,
                "bar_pct": round(s["count"] / max_lang_count * 100),
                "color": _LANG_COLORS.get(name, "#8b949e"),
            }
            for name, s in lang_stats.items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )

    # ── Commit / contributor metrics ──
    contributors: dict[str, int] = defaultdict(int)
    for row in commits_rows:
        contributors[row.author] += 1

    _contribs: list[dict[str, Any]] = [{"name": n, "commits": c} for n, c in contributors.items()]
    top_contributors = sorted(_contribs, key=lambda x: x["commits"], reverse=True)[:8]

    recent_commits = [
        {
            "message": row.message[:80],
            "author": row.author,
            "branch": row.branch,
            "ts": row.timestamp.isoformat() if row.timestamp else "",
        }
        for row in commits_rows[:10]
    ]

    code_file_count = sum(
        1 for path, _ in objects_rows
        if Path(path).suffix.lstrip(".").lower() in _CODE_EXTS
    )

    return {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_commits": len(commits_rows),
        "total_branches": branches_count,
        "contributor_count": len(contributors),
        "code_file_count": code_file_count,
        "test_file_count": len(test_files),
        "doc_file_count": len(doc_files),
        "test_ratio": round(len(test_files) / max(code_file_count, 1) * 100),
        "doc_ratio": round(len(doc_files) / max(total_files, 1) * 100),
        "languages": languages[:12],
        "top_contributors": top_contributors,
        "largest_files": largest_files[:10],
        "recent_commits": recent_commits,
        "total_size_kb": round(total_bytes / 1024),
        "avg_file_kb": round(total_bytes / max(total_files, 1) / 1024, 1),
    }


# ── Insights route ────────────────────────────────────────────────────────────


@view_router.get(
    "/{owner}/{repo_slug}/insights/{ref}",
    response_class=HTMLResponse,
    summary="Domain insights dashboard",
    operation_id="insightsDashboardPage",
)
async def insights_dashboard_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render the domain insights dashboard for a repository at a given ref.

    Dimensions are sourced from ``domain.capabilities.dimensions``:
    - MIDI domain: harmony, rhythm, melody, dynamics, tempo, key, meter, groove, etc.
    - Code domain: symbols, hotspots, coupling, complexity, churn, coverage, etc.
    - Generic: no dimensions (empty state).
    """
    repo = await musehub_repository.get_repo_by_owner_slug(db, owner, repo_slug)
    if repo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository not found.")

    nav_ctx = await build_repo_nav_ctx(db, repo, owner, repo_slug)
    domain_ctx = await _get_domain_for_repo(db, repo.repo_id, repo.domain_id)

    metrics: dict[str, Any] = {}
    if domain_ctx["viewer_type"] == "symbol_graph":
        metrics = await _compute_code_insights(db, repo.repo_id)

    # Pre-compute all dimension data for the dashboard cards
    _DASHBOARD_DIMS = ["key", "tempo", "meter", "groove", "form", "dynamics", "emotion", "motifs", "contour"]
    dim_map: dict[str, object] = {
        dim: musehub_analysis.compute_dimension(dim, ref)
        for dim in _DASHBOARD_DIMS
    }

    base_url = f"/{owner}/{repo_slug}"
    ctx: dict[str, object] = {
        "title": f"Insights · {owner}/{repo_slug}@{ref}",
        "current_page": "insights",
        "repo": repo,
        "repo_id": repo.repo_id,
        "owner": owner,
        "repo_slug": repo_slug,
        "base_url": base_url,
        "ref": ref,
        "domain": domain_ctx,
        "active_dimension": None,
        "metrics": metrics,
        "dim_map": dim_map,
        "muse_resource_uri": f"muse://repos/{owner}/{repo_slug}",
        **nav_ctx,
    }
    return await htmx_fragment_or_full(
        request, _templates, ctx,
        full_template="musehub/pages/insights.html",
        fragment_template="musehub/fragments/analysis/dashboard_content.html",
    )


@view_router.get(
    "/{owner}/{repo_slug}/insights/{ref}/{dim}",
    response_class=HTMLResponse,
    summary="Single domain insight dimension",
    operation_id="insightsDimensionPage",
)
async def insights_dimension_page(
    request: Request,
    owner: str,
    repo_slug: str,
    ref: str,
    dim: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render a single insight dimension for a domain repo."""
    repo = await musehub_repository.get_repo_by_owner_slug(db, owner, repo_slug)
    if repo is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Repository not found.")

    nav_ctx = await build_repo_nav_ctx(db, repo, owner, repo_slug)
    domain_ctx = await _get_domain_for_repo(db, repo.repo_id, repo.domain_id)

    metrics: dict[str, Any] = {}
    if domain_ctx["viewer_type"] == "symbol_graph":
        metrics = await _compute_code_insights(db, repo.repo_id)

    base_url = f"/{owner}/{repo_slug}"
    # Compute dimension-specific data using the correct function per dimension
    _dim_key = dim.replace("-", "_")
    if dim == "harmony":
        dim_data: object = musehub_analysis.compute_harmony_analysis(repo_id=repo.repo_id, ref=ref)
    elif dim == "emotion":
        dim_data = musehub_analysis.compute_emotion_map(repo_id=repo.repo_id, ref=ref)
    elif dim == "dynamics":
        dim_data = musehub_analysis.compute_dynamics_page_data(repo_id=repo.repo_id, ref=ref)
    else:
        dim_data = musehub_analysis.compute_dimension(dim, ref)
    ctx: dict[str, object] = {
        "title": f"{dim.replace('-', ' ').title()} Insight · {owner}/{repo_slug}@{ref}",
        "current_page": "insights",
        "repo": repo,
        "repo_id": repo.repo_id,
        "owner": owner,
        "repo_slug": repo_slug,
        "base_url": base_url,
        "ref": ref,
        "domain": domain_ctx,
        "active_dimension": dim,
        "metrics": metrics,
        "muse_resource_uri": f"muse://repos/{owner}/{repo_slug}",
        # Dimension-specific data keys expected by the dimension templates
        f"{_dim_key}_data": dim_data,
        **nav_ctx,
    }
    # Use dimension-specific template if it exists, otherwise fall back to insights.html
    _DIM_TEMPLATES: dict[str, str] = {
        "key": "musehub/pages/analysis/key.html",
        "tempo": "musehub/pages/analysis/tempo.html",
        "meter": "musehub/pages/analysis/meter.html",
        "groove": "musehub/pages/analysis/groove.html",
        "form": "musehub/pages/analysis/form.html",
        "harmony": "musehub/pages/analysis/harmony.html",
        "contour": "musehub/pages/analysis/contour.html",
        "dynamics": "musehub/pages/analysis/dynamics.html",
        "motifs": "musehub/pages/analysis/motifs.html",
        "chord_map": "musehub/pages/analysis/chord_map.html",
        "chord-map": "musehub/pages/analysis/chord_map.html",
        "context": "musehub/pages/analysis/context.html",
        "emotion": "musehub/pages/analysis/emotion.html",
        "compare": "musehub/pages/analysis/compare.html",
        "divergence": "musehub/pages/analysis/divergence.html",
    }
    _DIM_FRAGMENTS: dict[str, str] = {
        "key": "musehub/fragments/analysis/key_content.html",
        "tempo": "musehub/fragments/analysis/tempo_content.html",
        "meter": "musehub/fragments/analysis/meter_content.html",
        "groove": "musehub/fragments/analysis/groove_content.html",
        "form": "musehub/fragments/analysis/form_content.html",
        "harmony": "musehub/fragments/analysis/harmony_content.html",
        "contour": "musehub/fragments/analysis/contour_content.html",
        "dynamics": "musehub/fragments/analysis/dynamics_content.html",
        "motifs": "musehub/fragments/analysis/motifs_content.html",
        "chord_map": "musehub/fragments/analysis/chord_map_content.html",
        "chord-map": "musehub/fragments/analysis/chord_map_content.html",
        "emotion": "musehub/fragments/analysis/emotion_content.html",
    }
    full_template = _DIM_TEMPLATES.get(dim, "musehub/pages/insights.html")
    fragment_template = _DIM_FRAGMENTS.get(dim)
    return await htmx_fragment_or_full(
        request, _templates, ctx,
        full_template=full_template,
        fragment_template=fragment_template,
    )

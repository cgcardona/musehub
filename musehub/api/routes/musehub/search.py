
"""MuseHub search route handlers.

Endpoints:
  GET /musehub/search?q={q}&mode={mode}
    — Global cross-repo commit search (keyword or pattern).

  GET /repos/{repo_id}/search?q={q}&mode={mode}
    — In-repo commit search with four modes:
        property — filter by musical properties (harmony, rhythm, etc.)
        ask — natural-language query (keyword extraction + overlap scoring)
        keyword — keyword/phrase overlap scored search
        pattern — substring pattern match against message and branch name

Authentication: JWT Bearer token required (inherited from musehub router).

"""

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import TokenClaims, optional_token
from musehub.db import get_db
from musehub.models.musehub import GlobalSearchResult, SearchResponse

from musehub.services import musehub_repository, musehub_search, musehub_discover

logger = logging.getLogger(__name__)

router = APIRouter()


_VALID_MODES = frozenset({"property", "ask", "keyword", "pattern"})

_GLOBAL_VALID_MODES = frozenset({"keyword", "pattern"})
_REPO_VALID_MODES = frozenset({"property", "ask", "keyword", "pattern"})


@router.get(
    "/search/repos",
    summary="Discover repos by meaning or name",
    operation_id="searchRepos",
)
async def search_repos(
    q: str = Query(..., min_length=1, max_length=500, description="Natural-language or keyword query"),
    limit: int = Query(20, ge=1, le=50, description="Max results"),
    domain: str | None = Query(None, description="Filter by Muse domain"),
    db: AsyncSession = Depends(get_db),
    _: TokenClaims | None = Depends(optional_token),
) -> Response:
    """Discover public repos by semantic meaning (Qdrant) or text (fallback).

    When Qdrant + OpenAI are configured the query is embedded into the vector
    space and the nearest repos are returned — finding repos by *what they
    contain*, not just their names. Falls back to ILIKE search on name,
    slug, description and tags when vectors are unavailable.

    Returns ``{ query, semantic, repos: ExploreRepoResult[] }``.
    """
    from musehub.services import musehub_qdrant as qdrant_svc

    qdrant = qdrant_svc.get_qdrant()
    semantic = False
    repos = []

    if qdrant is not None:
        sem_hits = await qdrant_svc.semantic_search_repos(qdrant, q, limit=limit, domain=domain)
        repo_ids = [h.get("repo_id") for h in sem_hits if h.get("repo_id")]
        if repo_ids:
            repos = [r.model_dump(mode="json") for r in await musehub_discover.get_repos_by_ids(db, repo_ids)]
            semantic = bool(repos)

    if not repos:
        text_results = await musehub_discover.search_repos_by_text(db, q, limit=limit)
        repos = [r.model_dump(mode="json") for r in text_results]

    logger.info("🔍 search/repos q=%r semantic=%s → %d results", q, semantic, len(repos))
    return Response(
        content=json.dumps({"query": q, "semantic": semantic, "repos": repos}),
        media_type="application/json",
    )


@router.get(
    "/search",
    response_model=GlobalSearchResult,
    operation_id="globalSearch",
    summary="Global cross-repo search across all public MuseHub repos",
)
async def global_search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query string"),
    mode: str = Query("keyword", description="Search mode: 'keyword' or 'pattern'"),
    page: int = Query(1, ge=1, description="1-based page number for repo-group pagination"),
    page_size: int = Query(10, ge=1, le=50, description="Number of repo groups per page"),
    db: AsyncSession = Depends(get_db),
    _: TokenClaims | None = Depends(optional_token),
) -> GlobalSearchResult:
    """Search commit messages across all public MuseHub repos.

    Results are grouped by repo — each group contains up to 20 matching
    commits ordered newest-first with repo-level metadata (name, owner).

    Only ``visibility='public'`` repos are searched. Private repos are
    excluded at the persistence layer regardless of caller identity.

    Pagination applies to repo-groups: ``page=1&page_size=10`` returns the
    first 10 repos that had at least one match.

    Supported search modes:
    - ``keyword``: OR-match whitespace-split terms against commit messages and
      repo names (case-insensitive).
    - ``pattern``: raw SQL LIKE pattern applied to commit messages only.
      Use ``%`` as wildcard (e.g. ``q=%minor%``).

    Content negotiation: this endpoint always returns JSON. The companion
    HTML page at ``GET /search`` renders the browser UI shell.
    """
    effective_mode = mode if mode in _GLOBAL_VALID_MODES else "keyword"
    if effective_mode != mode:
        logger.warning("⚠️ Unknown search mode %r — falling back to 'keyword'", mode)

    result = await musehub_repository.global_search(
        db,
        query=q,
        mode=effective_mode,
        page=page,
        page_size=page_size,
    )
    logger.info(
        "✅ Global search q=%r mode=%s page=%d → %d repo groups",
        q,
        effective_mode,
        page,
        len(result.groups),
    )
    return result


@router.get(
    "/repos/{repo_id}/search",
    response_model=SearchResponse,
    operation_id="searchRepo",
    summary="Search Muse repo commits",
)
async def search_repo(
    repo_id: str,
    q: str = Query("", description="Search query — interpreted by the selected mode"),
    mode: str = Query("keyword", description="Search mode: property | ask | keyword | pattern"),
    harmony: str | None = Query(None, description="[property mode] Harmony filter"),
    rhythm: str | None = Query(None, description="[property mode] Rhythm filter"),
    melody: str | None = Query(None, description="[property mode] Melody filter"),
    structure: str | None = Query(None, description="[property mode] Structure filter"),
    dynamic: str | None = Query(None, description="[property mode] Dynamics filter"),
    emotion: str | None = Query(None, description="[property mode] Emotion filter"),
    since: datetime | None = Query(None, description="Only include commits on or after this ISO datetime"),
    until: datetime | None = Query(None, description="Only include commits on or before this ISO datetime"),
    limit: int = Query(20, ge=1, le=200, description="Maximum results to return"),
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> SearchResponse:
    """Search commit history using one of four musical search modes.

    The ``mode`` parameter selects the search algorithm:

    - **property** — filter commits by musical properties using AND logic.
      Supply any of ``harmony``, ``rhythm``, ``melody``, ``structure``,
      ``dynamic``, ``emotion`` query params. Accepts ``key=low-high`` range
      syntax (e.g. ``rhythm=tempo=120-130``).

    - **ask** — treat ``q`` as a natural-language question. Stop-words are
      stripped; remaining keywords are scored by overlap coefficient.

    - **keyword** — score commits by keyword overlap against ``q``.
      Useful for exact term search (e.g. ``q=Fmin_jazz_bassline``).

    - **pattern** — case-insensitive substring match of ``q`` against commit
      messages and branch names. No scoring; matched rows returned newest-first.

    Returns 404 if the repo does not exist. Returns an empty ``matches`` list
    when no commits satisfy the criteria (not a 404).
    """
    if mode not in _REPO_VALID_MODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid mode '{mode}'. Must be one of: {sorted(_REPO_VALID_MODES)}",
        )

    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    if repo.visibility != "public" and claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access private repos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if mode == "property":
        return await musehub_search.search_by_property(
            db,
            repo_id=repo_id,
            harmony=harmony,
            rhythm=rhythm,
            melody=melody,
            structure=structure,
            dynamic=dynamic,
            emotion=emotion,
            since=since,
            until=until,
            limit=limit,
        )

    if mode == "ask":
        return await musehub_search.search_by_ask(
            db,
            repo_id=repo_id,
            question=q,
            since=since,
            until=until,
            limit=limit,
        )

    if mode == "keyword":
        return await musehub_search.search_by_keyword(
            db,
            repo_id=repo_id,
            keyword=q,
            since=since,
            until=until,
            limit=limit,
        )

    return await musehub_search.search_by_pattern(
        db,
        repo_id=repo_id,
        pattern=q,
        since=since,
        until=until,
        limit=limit,
    )

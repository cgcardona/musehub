"""REST API — global search endpoint.

Mounted at /api/search

Unified search across repos, commits, and objects using:
    1. Qdrant semantic search (when configured)
    2. Postgres fulltext fallback

Example:
    GET /api/search?q=jazz+chord+progression&type=repos
    GET /api/search?q=fix+memory+leak&type=commits&repo_id=abc123
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from musehub.auth.dependencies import optional_token, TokenClaims
from musehub.services import musehub_qdrant as qdrant_svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Search"])


@router.get("/api/search", summary="Global semantic search")
async def global_search(
    q: str = Query(..., min_length=1, description="Natural language query"),
    type: str = Query("repos", description="What to search: repos | commits | objects"),
    domain: str | None = Query(None, description="Filter by Muse domain"),
    repo_id: str | None = Query(None, description="Scope commit/object search to a repo"),
    limit: int = Query(10, ge=1, le=50),
    _claims: TokenClaims | None = Depends(optional_token),
) -> Response:
    """Semantic search powered by Qdrant + OpenAI embeddings.

    Falls back to an empty result with a hint when Qdrant is not configured.

    Result shape:
    ```json
    {
      "query": "jazz chord progression",
      "type": "repos",
      "semantic": true,
      "results": [
        {"repo_id": "...", "owner": "...", "slug": "...", "score": 0.92}
      ]
    }
    ```
    """
    qdrant = qdrant_svc.get_qdrant()

    if qdrant is None:
        return Response(
            content=json.dumps({
                "query": q,
                "type": type,
                "semantic": False,
                "results": [],
                "hint": "Set QDRANT_URL and OPENAI_API_KEY to enable semantic search.",
            }),
            media_type="application/json",
        )

    if type == "repos":
        results = await qdrant_svc.semantic_search_repos(qdrant, q, limit=limit, domain=domain)
    elif type == "commits":
        results = await qdrant_svc.semantic_search_commits(qdrant, q, repo_id=repo_id, limit=limit)
    else:
        results = []

    return Response(
        content=json.dumps({
            "query": q,
            "type": type,
            "semantic": True,
            "results": results,
        }),
        media_type="application/json",
    )

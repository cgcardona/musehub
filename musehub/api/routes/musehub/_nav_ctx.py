"""Shared repo-resolution helper used by all MuseHub UI route modules.

Each UI page that includes ``repo_nav.html`` / ``repo_tabs.html`` requires:
  - repo_key, repo_bpm, repo_tags, repo_visibility  (displayed in the nav chips)
  - nav_open_pr_count, nav_open_issue_count          (tab count badges)

Centralising this lookup here avoids repeating it in every separate UI route
file and keeps the nav_ctx contract in one place.
"""

from typing import Any

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as musehub_db
from musehub.services import musehub_repository


async def resolve_repo_with_nav(
    owner: str,
    repo_slug: str,
    db: AsyncSession,
) -> tuple[str, str, dict[str, Any]]:
    """Resolve owner+slug → (repo_id, base_url, nav_ctx); raise 404 if not found.

    ``nav_ctx`` contains all variables required by ``repo_nav.html`` and
    ``repo_tabs.html``:

    - ``repo_key`` — key signature (e.g. "C major") or ""
    - ``repo_bpm`` — tempo in BPM or None
    - ``repo_tags`` — list of tag strings (may be empty)
    - ``repo_visibility`` — "public" | "private" | "unlisted"
    - ``nav_open_pr_count`` — count of open pull requests
    - ``nav_open_issue_count`` — count of open issues

    Callers should merge nav_ctx into their template context with
    ``ctx.update(nav_ctx)`` before passing ``ctx`` to ``TemplateResponse`` or
    ``negotiate_response``.
    """
    row = await musehub_repository.get_repo_orm_by_owner_slug(db, owner, repo_slug)
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Repo '{owner}/{repo_slug}' not found",
        )
    repo_id = str(row.repo_id)

    pr_count = await db.scalar(
        sa_select(func.count())
        .select_from(musehub_db.MusehubPullRequest)
        .where(
            musehub_db.MusehubPullRequest.repo_id == repo_id,
            musehub_db.MusehubPullRequest.state == "open",
        )
    ) or 0

    issue_count = await db.scalar(
        sa_select(func.count())
        .select_from(musehub_db.MusehubIssue)
        .where(
            musehub_db.MusehubIssue.repo_id == repo_id,
            musehub_db.MusehubIssue.state == "open",
        )
    ) or 0

    nav_ctx: dict[str, Any] = {
        "repo_key": row.key_signature or "",
        "repo_bpm": row.tempo_bpm,
        "repo_tags": row.tags or [],
        "repo_visibility": row.visibility or "private",
        "nav_open_pr_count": pr_count,
        "nav_open_issue_count": issue_count,
    }
    return repo_id, f"/{owner}/{repo_slug}", nav_ctx

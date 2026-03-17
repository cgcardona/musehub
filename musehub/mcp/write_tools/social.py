"""Write executors for social operations: star_repo, create_label."""
from __future__ import annotations

import logging
import uuid

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_discover, musehub_repository
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

logger = logging.getLogger(__name__)


async def execute_star_repo(
    *,
    repo_id: str,
    actor: str,
) -> MusehubToolResult:
    """Star a MuseHub repository on behalf of the authenticated user.

    Idempotent: starring a repo that is already starred returns success.

    Args:
        repo_id: UUID of the repository to star.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.starred`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        async with AsyncSessionLocal() as session:
            repo = await musehub_repository.get_repo(session, repo_id)
            if repo is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Repository '{repo_id}' not found.",
                )
            result = await musehub_discover.star_repo(session, repo_id, actor)
            await session.commit()
            data: dict[str, JSONValue] = {
                "repo_id": repo_id,
                "starred": True,
                "star_count": result.star_count,
            }
            logger.info("MCP star_repo %s by %s", repo_id, actor)
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP star_repo failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_create_label(
    *,
    repo_id: str,
    name: str,
    color: str,
    description: str = "",
    actor: str = "",
) -> MusehubToolResult:
    """Create a repo-scoped label with a name and hex colour.

    Label names must be unique within the repository.

    Args:
        repo_id: UUID of the repository.
        name: Label name (must be unique per repo).
        color: 6-char hex colour string without ``#`` prefix (e.g. ``"e11d48"``).
        description: Optional label description.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.label_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        from sqlalchemy import text  # local import

        async with AsyncSessionLocal() as session:
            repo = await musehub_repository.get_repo(session, repo_id)
            if repo is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Repository '{repo_id}' not found.",
                )

            # Check name uniqueness.
            existing = await session.execute(
                text(
                    "SELECT 1 FROM musehub_labels "
                    "WHERE repo_id = :repo_id AND name = :name"
                ),
                {"repo_id": repo_id, "name": name},
            )
            if existing.scalar_one_or_none() is not None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Label '{name}' already exists in repo '{repo_id}'.",
                )

            label_id = str(uuid.uuid4())
            await session.execute(
                text(
                    "INSERT INTO musehub_labels "
                    "(id, repo_id, name, color, description, created_at) "
                    "VALUES (:label_id, :repo_id, :name, :color, :description, CURRENT_TIMESTAMP)"
                ),
                {
                    "label_id": label_id,
                    "repo_id": repo_id,
                    "name": name,
                    "color": color,
                    "description": description,
                },
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "label_id": label_id,
                "repo_id": repo_id,
                "name": name,
                "color": color,
                "description": description,
            }
            logger.info("MCP create_label '%s' (%s) in repo %s", name, label_id, repo_id)
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP create_label failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )

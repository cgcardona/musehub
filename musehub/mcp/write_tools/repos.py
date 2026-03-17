"""Write executors for repository operations: create_repo, fork_repo."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_repository
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

logger = logging.getLogger(__name__)


async def execute_create_repo(
    *,
    name: str,
    owner: str,
    owner_user_id: str,
    description: str = "",
    visibility: str = "public",
    tags: list[str] | None = None,
    key_signature: str | None = None,
    tempo_bpm: int | None = None,
    initialize: bool = True,
) -> MusehubToolResult:
    """Create a new MuseHub repository owned by ``owner``.

    Args:
        name: Human-readable repo name (slug auto-generated).
        owner: Username of the repo owner.
        owner_user_id: Authenticated user ID (JWT ``sub`` claim).
        description: Optional markdown description.
        visibility: ``"public"`` (default) or ``"private"``.
        tags: Optional list of tag strings for musical categorisation.
        key_signature: Optional key (e.g. ``"C major"``).
        tempo_bpm: Optional tempo in BPM.
        initialize: When True (default) an empty initial commit + default branch are created.

    Returns:
        ``MusehubToolResult`` with ``data.repo_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        async with AsyncSessionLocal() as session:
            repo = await musehub_repository.create_repo(
                session,
                name=name,
                owner=owner,
                visibility=visibility,
                owner_user_id=owner_user_id,
                description=description,
                tags=tags,
                key_signature=key_signature,
                tempo_bpm=tempo_bpm,
                initialize=initialize,
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "repo_id": repo.repo_id,
                "name": repo.name,
                "slug": repo.slug,
                "owner": repo.owner,
                "visibility": repo.visibility,
                "clone_url": repo.clone_url,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
            }
            logger.info("MCP create_repo: %s/%s (%s)", owner, repo.slug, repo.repo_id)
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP create_repo failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_fork_repo(
    *,
    repo_id: str,
    actor: str,
) -> MusehubToolResult:
    """Fork a public repository under the ``actor``'s account.

    Copies all branch head pointers from the source into the new fork and
    records the fork lineage so the UI can render "Forked from" badges.

    Args:
        repo_id: UUID of the source repository.
        actor: Authenticated user ID (JWT ``sub`` claim) who will own the fork.

    Returns:
        ``MusehubToolResult`` with ``data.fork_repo_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        from musehub.db.musehub_models import MusehubFork, MusehubBranch  # local import

        async with AsyncSessionLocal() as session:
            source = await musehub_repository.get_repo(session, repo_id)
            if source is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Repository '{repo_id}' not found.",
                )
            if source.visibility != "public":
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message="Only public repositories can be forked.",
                )

            fork_repo = await musehub_repository.create_repo(
                session,
                name=source.name,
                owner=actor,
                visibility=source.visibility,
                owner_user_id=actor,
                description=f"Fork of {source.owner}/{source.slug}",
                tags=list(source.tags) if source.tags else [],
                key_signature=source.key_signature,
                tempo_bpm=source.tempo_bpm,
            )

            from datetime import datetime, timezone
            now = datetime.now(tz=timezone.utc)
            fork_record = MusehubFork(
                fork_id=str(uuid.uuid4()),
                source_repo_id=repo_id,
                fork_repo_id=fork_repo.repo_id,
                forked_by=actor,
                created_at=now,
            )
            session.add(fork_record)

            source_branches = await musehub_repository.list_branches(session, repo_id)
            for branch in source_branches:
                session.add(MusehubBranch(
                    repo_id=fork_repo.repo_id,
                    name=branch.name,
                    head_commit_id=branch.head_commit_id,
                ))

            await session.commit()
            data: dict[str, JSONValue] = {
                "fork_repo_id": fork_repo.repo_id,
                "fork_slug": fork_repo.slug,
                "fork_owner": fork_repo.owner,
                "source_repo_id": repo_id,
                "clone_url": fork_repo.clone_url,
            }
            logger.info("MCP fork_repo: %s -> %s by %s", repo_id, fork_repo.repo_id, actor)
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP fork_repo failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )

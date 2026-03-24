"""Write executor for release operations: create_release."""

import logging

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_releases, musehub_repository
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

logger = logging.getLogger(__name__)


async def execute_create_release(
    *,
    repo_id: str,
    tag: str,
    title: str = "",
    body: str = "",
    commit_id: str | None = None,
    channel: str = "stable",
    actor: str = "",
) -> MusehubToolResult:
    """Publish a new release for a MuseHub repository.

    A release pins a semver tag to a specific commit.  The ``channel`` field
    replaces the old ``is_prerelease`` boolean with a named distribution tier
    (stable | beta | alpha | nightly).  Tags must be unique per repo.

    Args:
        repo_id: UUID of the repository.
        tag: Semver tag string (e.g. ``"v1.2.3"``). Must be unique per repo.
        title: Human-readable release title.
        body: Markdown release notes.
        commit_id: Optional commit UUID to pin this release to.
        channel: Distribution channel: stable | beta | alpha | nightly.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.release_id`` and ``data.tag`` on success.
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

            release = await musehub_releases.create_release(
                session,
                repo_id=repo_id,
                tag=tag,
                title=title,
                body=body,
                commit_id=commit_id,
                channel=channel,
                author=actor,
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "release_id": release.release_id,
                "repo_id": repo_id,
                "tag": release.tag,
                "title": release.title,
                "body": release.body,
                "channel": release.channel,
                "commit_id": release.commit_id,
                "author": release.author,
                "created_at": release.created_at.isoformat() if release.created_at else None,
            }
            logger.info("MCP create_release %s for repo %s: %s", tag, repo_id, title)
            return MusehubToolResult(ok=True, data=data)
    except ValueError as exc:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("MCP create_release failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )

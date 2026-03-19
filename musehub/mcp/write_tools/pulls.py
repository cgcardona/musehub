"""Write executors: create_pr, merge_pr, create_pr_comment, submit_pr_review."""

import logging

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_pull_requests, musehub_repository
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

logger = logging.getLogger(__name__)


def _pr_data(pr: object) -> dict[str, JSONValue]:
    """Serialise a PRResponse to a ``dict[str, JSONValue]``."""
    from musehub.models.musehub import PRResponse  # local import

    assert isinstance(pr, PRResponse)
    return {
        "pr_id": pr.pr_id,
        "title": pr.title,
        "body": pr.body,
        "state": pr.state,
        "from_branch": pr.from_branch,
        "to_branch": pr.to_branch,
        "author": pr.author,
        "merge_commit_id": pr.merge_commit_id,
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
    }


async def execute_create_pr(
    *,
    repo_id: str,
    title: str,
    from_branch: str,
    to_branch: str,
    body: str = "",
    actor: str = "",
) -> MusehubToolResult:
    """Open a new pull request proposing to merge ``from_branch`` into ``to_branch``.

    Args:
        repo_id: UUID of the repository.
        title: PR title.
        from_branch: Source branch name.
        to_branch: Target branch name.
        body: Optional markdown description.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.pr_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    if from_branch == to_branch:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message="from_branch and to_branch must be different.",
        )

    try:
        async with AsyncSessionLocal() as session:
            repo = await musehub_repository.get_repo(session, repo_id)
            if repo is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Repository '{repo_id}' not found.",
                )
            pr = await musehub_pull_requests.create_pr(
                session,
                repo_id=repo_id,
                title=title,
                from_branch=from_branch,
                to_branch=to_branch,
                body=body,
                author=actor,
            )
            await session.commit()
            logger.info("MCP create_pr '%s' (%s→%s) in %s", title, from_branch, to_branch, repo_id)
            return MusehubToolResult(ok=True, data=_pr_data(pr))
    except ValueError as exc:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("MCP create_pr failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_merge_pr(
    *,
    repo_id: str,
    pr_id: str,
    merge_strategy: str = "merge_commit",
) -> MusehubToolResult:
    """Merge an open pull request using the specified merge strategy.

    Args:
        repo_id: UUID of the repository.
        pr_id: UUID of the pull request.
        merge_strategy: ``"merge_commit"`` (default), ``"squash"``, or ``"rebase"``.

    Returns:
        ``MusehubToolResult`` with merged PR data and ``data.merge_commit_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        async with AsyncSessionLocal() as session:
            pr = await musehub_pull_requests.merge_pr(
                session,
                repo_id,
                pr_id,
                merge_strategy=merge_strategy,
            )
            await session.commit()
            logger.info("MCP merge_pr %s in %s", pr_id, repo_id)
            return MusehubToolResult(ok=True, data=_pr_data(pr))
    except ValueError as exc:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )
    except RuntimeError as exc:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("MCP merge_pr failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_create_pr_comment(
    *,
    repo_id: str,
    pr_id: str,
    body: str,
    actor: str = "",
    target_type: str = "general",
    target_track: str | None = None,
    target_beat_start: float | None = None,
    target_beat_end: float | None = None,
) -> MusehubToolResult:
    """Post a comment on a pull request, optionally anchored to a track or region.

    Musical comments can target:
    - ``target_type="general"`` — plain PR-level comment
    - ``target_type="track"`` — targets a named track (``target_track`` required)
    - ``target_type="region"`` — targets a beat range (``target_beat_start`` + ``target_beat_end`` required)

    Args:
        repo_id: UUID of the repository.
        pr_id: UUID of the pull request.
        body: Markdown comment body.
        actor: Authenticated user ID (JWT ``sub`` claim).
        target_type: One of ``"general"``, ``"track"``, or ``"region"``.
        target_track: Track name for track/region comments.
        target_beat_start: Start beat for region comments.
        target_beat_end: End beat for region comments.

    Returns:
        ``MusehubToolResult`` with ``data.comment_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        async with AsyncSessionLocal() as session:
            comment = await musehub_pull_requests.create_pr_comment(
                session,
                pr_id=pr_id,
                repo_id=repo_id,
                author=actor,
                body=body,
                target_type=target_type,
                target_track=target_track,
                target_beat_start=target_beat_start,
                target_beat_end=target_beat_end,
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "comment_id": comment.comment_id,
                "pr_id": pr_id,
                "author": comment.author,
                "body": comment.body,
                "target_type": comment.target_type,
                "target_track": comment.target_track,
                "target_beat_start": comment.target_beat_start,
                "target_beat_end": comment.target_beat_end,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
            }
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP create_pr_comment failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_submit_pr_review(
    *,
    repo_id: str,
    pr_id: str,
    event: str,
    body: str = "",
    reviewer: str = "",
) -> MusehubToolResult:
    """Submit a formal review on a pull request.

    ``event`` determines the review verdict:
    - ``"approve"`` → marks PR approved
    - ``"request_changes"`` → requests changes from the author
    - ``"comment"`` → adds a body-only comment without verdict change

    Args:
        repo_id: UUID of the repository.
        pr_id: UUID of the pull request.
        event: Review event: ``"approve"``, ``"request_changes"``, or ``"comment"``.
        body: Optional review summary body.
        reviewer: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.state`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    valid_events = {"approve", "request_changes", "comment"}
    if event not in valid_events:
        return MusehubToolResult(
            ok=False,
            error_code="invalid_mode",
            error_message=f"event must be one of {sorted(valid_events)}.",
        )

    try:
        async with AsyncSessionLocal() as session:
            review = await musehub_pull_requests.submit_review(
                session,
                repo_id=repo_id,
                pr_id=pr_id,
                reviewer_username=reviewer,
                event=event,
                body=body,
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "review_id": review.id,
                "pr_id": pr_id,
                "reviewer": review.reviewer_username,
                "state": review.state,
                "body": review.body,
                "submitted_at": review.submitted_at.isoformat() if review.submitted_at else None,
            }
            logger.info("MCP submit_pr_review %s on %s by %s", event, pr_id, reviewer)
            return MusehubToolResult(ok=True, data=data)
    except ValueError as exc:
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )
    except Exception as exc:
        logger.exception("MCP submit_pr_review failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )

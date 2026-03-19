"""Write executors for issue operations: create_issue, update_issue, create_issue_comment."""

import logging

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_issues, musehub_repository
from musehub.services.musehub_mcp_executor import MusehubToolResult, _check_db_available

logger = logging.getLogger(__name__)


def _issue_data(issue: object) -> dict[str, JSONValue]:
    """Serialise an IssueResponse to a ``dict[str, JSONValue]``."""
    from musehub.models.musehub import IssueResponse  # local import

    assert isinstance(issue, IssueResponse)
    return {
        "issue_id": issue.issue_id,
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "state": issue.state,
        "labels": list(issue.labels),
        "author": issue.author,
        "assignee": issue.assignee,
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
    }


async def execute_create_issue(
    *,
    repo_id: str,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    actor: str = "",
) -> MusehubToolResult:
    """Open a new issue in a MuseHub repository.

    Args:
        repo_id: UUID of the target repository.
        title: Issue title.
        body: Optional markdown description.
        labels: Optional list of label strings to apply on creation.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.issue_id`` and ``data.number`` on success.
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

            issue = await musehub_issues.create_issue(
                session,
                repo_id=repo_id,
                title=title,
                body=body,
                labels=labels or [],
                author=actor,
            )
            await session.commit()
            logger.info("MCP create_issue #%d in %s: %s", issue.number, repo_id, title)
            return MusehubToolResult(ok=True, data=_issue_data(issue))
    except Exception as exc:
        logger.exception("MCP create_issue failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_update_issue(
    *,
    repo_id: str,
    issue_number: int,
    title: str | None = None,
    body: str | None = None,
    labels: list[str] | None = None,
    state: str | None = None,
    assignee: str | None = None,
) -> MusehubToolResult:
    """Update an existing issue's title, body, labels, state, or assignee.

    Only supplied (non-None) fields are modified. Closing/reopening an issue
    requires passing ``state="closed"`` or ``state="open"`` respectively.

    Args:
        repo_id: UUID of the repository.
        issue_number: Per-repo issue number.
        title: New title (optional).
        body: New markdown body (optional).
        labels: Replacement label list (optional; replaces existing labels).
        state: ``"open"`` or ``"closed"`` (optional).
        assignee: Username to assign, or empty string to unassign (optional).

    Returns:
        ``MusehubToolResult`` with updated issue data on success.
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

            if title is not None or body is not None or labels is not None:
                issue = await musehub_issues.update_issue(
                    session,
                    repo_id,
                    issue_number,
                    title=title,
                    body=body,
                    labels=labels,
                )
                if issue is None:
                    return MusehubToolResult(
                        ok=False,
                        error_code="not_found",
                        error_message=f"Issue #{issue_number} not found in repo '{repo_id}'.",
                    )

            if state == "closed":
                issue = await musehub_issues.close_issue(session, repo_id, issue_number)
            elif state == "open":
                issue = await musehub_issues.reopen_issue(session, repo_id, issue_number)

            if assignee is not None:
                issue = await musehub_issues.assign_issue(
                    session,
                    repo_id,
                    issue_number,
                    assignee=assignee or None,
                )

            # Fetch final state if not already set.
            if title is None and body is None and labels is None and state is None and assignee is None:
                issue = await musehub_issues.get_issue(session, repo_id, issue_number)

            await session.commit()

            if issue is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Issue #{issue_number} not found in repo '{repo_id}'.",
                )
            return MusehubToolResult(ok=True, data=_issue_data(issue))
    except Exception as exc:
        logger.exception("MCP update_issue failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )


async def execute_create_issue_comment(
    *,
    repo_id: str,
    issue_number: int,
    body: str,
    actor: str = "",
) -> MusehubToolResult:
    """Add a comment to an existing issue.

    Args:
        repo_id: UUID of the repository.
        issue_number: Per-repo issue number.
        body: Markdown comment body.
        actor: Authenticated user ID (JWT ``sub`` claim).

    Returns:
        ``MusehubToolResult`` with ``data.comment_id`` on success.
    """
    if (err := _check_db_available()) is not None:
        return err

    try:
        async with AsyncSessionLocal() as session:
            issue = await musehub_issues.get_issue(session, repo_id, issue_number)
            if issue is None:
                return MusehubToolResult(
                    ok=False,
                    error_code="not_found",
                    error_message=f"Issue #{issue_number} not found in repo '{repo_id}'.",
                )

            comment = await musehub_issues.create_comment(
                session,
                issue_id=issue.issue_id,
                repo_id=repo_id,
                author=actor,
                body=body,
            )
            await session.commit()
            data: dict[str, JSONValue] = {
                "comment_id": comment.comment_id,
                "issue_number": issue_number,
                "author": comment.author,
                "body": comment.body,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
            }
            logger.info("MCP create_issue_comment on #%d in %s", issue_number, repo_id)
            return MusehubToolResult(ok=True, data=data)
    except Exception as exc:
        logger.exception("MCP create_issue_comment failed: %s", exc)
        return MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message=str(exc),
        )

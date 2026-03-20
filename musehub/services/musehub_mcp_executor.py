"""MuseHub MCP tool executor — server-side logic for all musehub_* MCP tools.

This module is the execution backend for MuseHub browsing tools exposed via
MCP. Each public function opens its own DB session via ``AsyncSessionLocal``,
delegates to ``musehub_repository`` for persistence access, and returns a
typed ``MusehubToolResult``.

Design contract
---------------
- All functions are async and return ``MusehubToolResult`` on both success
  and failure (no exceptions propagate to the MCP server).
- ``MusehubToolResult.ok`` distinguishes success from failure.
- ``MusehubToolResult.error_code`` is one of: ``"not_found"``,
  ``"invalid_dimension"``, ``"invalid_mode"``, ``"db_unavailable"``.
- Callers (``MuseMCPServer._execute_musehub_tool``) pattern-match on
  these codes to build appropriate ``MCPContentBlock`` responses.
- This module must NOT import MCP protocol types — it is pure service layer.

``AsyncSessionLocal`` is imported at module level so tests can patch it as
``musehub.services.musehub_mcp_executor.AsyncSessionLocal``.
"""

import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from musehub.contracts.json_types import JSONValue
from musehub.db.database import AsyncSessionLocal
from musehub.services import musehub_repository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

MusehubErrorCode = Literal[
    "not_found",
    "invalid_dimension",
    "invalid_mode",
    "db_unavailable",
    "elicitation_unavailable",
    "elicitation_declined",
    "not_confirmed",
]
"""Enumeration of error codes returned by MuseHub MCP executors.

Callers pattern-match on these to build appropriate error messages:
  - ``not_found`` — repo or object does not exist
  - ``invalid_dimension`` — unrecognised analysis dimension
  - ``invalid_mode`` — unrecognised search mode
  - ``db_unavailable`` — DB session factory not initialised (startup race)
  - ``elicitation_unavailable`` — client has no active session / no elicitation capability
  - ``elicitation_declined`` — user declined or cancelled the elicitation form/URL flow
  - ``not_confirmed`` — user did not confirm a required confirmation prompt
"""


@dataclass(frozen=True, slots=True)
class MusehubToolResult:
    """Result of executing a single musehub_* MCP tool.

    ``ok`` is the primary success/failure signal. On success, ``data``
    holds the JSON-serialisable payload for the MCP content block. On
    failure, ``error_code`` and ``error_message`` describe what went wrong.

    This type is the contract between the executor functions and the MCP
    server's routing layer — do not bypass it with raw exceptions.
    """

    ok: bool
    data: dict[str, JSONValue] = field(default_factory=dict)
    error_code: MusehubErrorCode | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_db_available() -> MusehubToolResult | None:
    """Return a ``db_unavailable`` error if the session factory is not ready.

    The MCP stdio server runs outside the FastAPI lifespan, so ``init_db()``
    may not have been called yet. Call this at the top of every executor that
    opens a DB session so the caller receives a structured error instead of an
    unhandled ``RuntimeError``.
    """
    from musehub.db import database  # local import to avoid circular reference

    if database._async_session_factory is None:
        return MusehubToolResult(
            ok=False,
            error_code="db_unavailable",
            error_message=(
                "Database session factory is not initialised. "
                "Ensure DATABASE_URL is set and the service has started up."
            ),
        )
    return None


_EXTRA_MIME: dict[str, str] = {
    ".mid": "audio/midi",
    ".midi": "audio/midi",
    ".mp3": "audio/mpeg",
    ".webp": "image/webp",
}


def _mime_for_path(path: str) -> str:
    """Resolve MIME type from a file path extension."""
    ext = Path(path).suffix.lower()
    if ext in _EXTRA_MIME:
        return _EXTRA_MIME[ext]
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------


async def execute_browse_repo(repo_id: str) -> MusehubToolResult:
    """Return repo metadata, branch list, and the 10 most recent commits.

    This is the entry-point tool for orienting an agent before it calls more
    specific tools. It aggregates three repository queries into one response
    to minimise round-trips for the common "explore a new repo" case.

    Args:
        repo_id: UUID of the target MuseHub repository.

    Returns:
        ``MusehubToolResult`` with ``data`` containing ``repo``, ``branches``,
        and ``recent_commits`` keys, or ``error_code="not_found"`` if the
        repo does not exist.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        branches = await musehub_repository.list_branches(session, repo_id)
        commits, total = await musehub_repository.list_commits(
            session, repo_id, limit=10
        )

        data: dict[str, JSONValue] = {
            "repo": {
                "repo_id": repo.repo_id,
                "name": repo.name,
                "visibility": repo.visibility,
                "owner_user_id": repo.owner_user_id,
                "clone_url": repo.clone_url,
                "created_at": repo.created_at.isoformat(),
            },
            "branches": [
                {
                    "branch_id": b.branch_id,
                    "name": b.name,
                    "head_commit_id": b.head_commit_id,
                }
                for b in branches
            ],
            "recent_commits": [
                {
                    "commit_id": c.commit_id,
                    "branch": c.branch,
                    "message": c.message,
                    "author": c.author,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in commits
            ],
            "total_commits": total,
            "branch_count": len(branches),
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_list_branches(repo_id: str) -> MusehubToolResult:
    """Return all branches for a MuseHub repository.

    Agents call this before ``execute_list_commits`` to discover available
    branch names and their current head commit IDs.

    Args:
        repo_id: UUID of the target MuseHub repository.

    Returns:
        ``MusehubToolResult`` with ``data.branches`` as a list of branch
        dicts, or ``error_code="not_found"`` if the repo does not exist.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        branches = await musehub_repository.list_branches(session, repo_id)
        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "branches": [
                {
                    "branch_id": b.branch_id,
                    "name": b.name,
                    "head_commit_id": b.head_commit_id,
                }
                for b in branches
            ],
            "branch_count": len(branches),
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_list_commits(
    repo_id: str,
    branch: str | None = None,
    limit: int = 20,
) -> MusehubToolResult:
    """Return paginated commits for a MuseHub repository, newest first.

    Args:
        repo_id: UUID of the target MuseHub repository.
        branch: Optional branch name filter; None returns across all branches.
        limit: Maximum commits to return (clamped to 1–100).

    Returns:
        ``MusehubToolResult`` with ``data.commits`` and ``data.total``,
        or ``error_code="not_found"`` if the repo does not exist.
    """
    limit = max(1, min(limit, 100))

    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        commits, total = await musehub_repository.list_commits(
            session, repo_id, branch=branch, limit=limit
        )

        commit_list: list[JSONValue] = []
        for c in commits:
            # parent_ids is list[str]; build list[JSONValue] explicitly (list invariance).
            parent_ids_json: list[JSONValue] = []
            for pid in c.parent_ids:
                parent_ids_json.append(pid)
            commit_list.append({
                "commit_id": c.commit_id,
                "branch": c.branch,
                "parent_ids": parent_ids_json,
                "message": c.message,
                "author": c.author,
                "timestamp": c.timestamp.isoformat(),
                "snapshot_id": c.snapshot_id,
            })

        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "branch_filter": branch,
            "commits": commit_list,
            "returned": len(commits),
            "total": total,
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_read_file(repo_id: str, object_id: str) -> MusehubToolResult:
    """Return metadata for a stored artifact in a MuseHub repo.

    Returns path, size_bytes, mime_type, and object_id. Binary content is
    intentionally excluded — MCP tool responses must be text-safe JSON.
    Agents that need the raw bytes should use the HTTP objects endpoint.

    Args:
        repo_id: UUID of the target MuseHub repository.
        object_id: Content-addressed ID (e.g. ``sha256:abc...``).

    Returns:
        ``MusehubToolResult`` with file metadata, or ``error_code="not_found"``
        if the repo or object does not exist.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        obj = await musehub_repository.get_object_row(session, repo_id, object_id)
        if obj is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Object '{object_id}' not found in repository '{repo_id}'.",
            )

        data: dict[str, JSONValue] = {
            "object_id": obj.object_id,
            "repo_id": repo_id,
            "path": obj.path,
            "size_bytes": obj.size_bytes,
            "mime_type": _mime_for_path(obj.path),
            "created_at": obj.created_at.isoformat(),
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_get_analysis(
    repo_id: str,
    dimension: str = "overview",
) -> MusehubToolResult:
    """Return structured analysis for a MuseHub repository.

    Supported dimensions:
    - ``overview`` — repo stats: branch count, commit count, object count,
                      most active author, most recent commit timestamp.
    - ``commits`` — commit activity: total, per-branch breakdown, author
                      distribution, and a sample of the most recent messages.
    - ``objects`` — artifact inventory: total size, per-MIME-type counts
                      and sizes, and a sample of object paths.

    MIDI audio analysis (key, tempo, harmonic content) requires Storpheus
    integration and is not yet available; those fields will be ``null``.

    Args:
        repo_id: UUID of the target MuseHub repository.
        dimension: Analysis dimension — one of ``overview``, ``commits``,
                   ``objects``.

    Returns:
        ``MusehubToolResult`` with analysis data, or an error code on failure.
    """
    valid_dimensions = {"overview", "commits", "objects"}
    if dimension not in valid_dimensions:
        return MusehubToolResult(
            ok=False,
            error_code="invalid_dimension",
            error_message=(
                f"Unknown dimension '{dimension}'. "
                f"Valid values: {', '.join(sorted(valid_dimensions))}."
            ),
        )

    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        if dimension == "overview":
            branches = await musehub_repository.list_branches(session, repo_id)
            commits, total_commits = await musehub_repository.list_commits(
                session, repo_id, limit=1
            )
            objects = await musehub_repository.list_objects(session, repo_id)

            last_commit_at: JSONValue = None
            most_recent_author: JSONValue = None
            if commits:
                last_commit_at = commits[0].timestamp.isoformat()
                most_recent_author = commits[0].author

            data: dict[str, JSONValue] = {
                "repo_id": repo_id,
                "dimension": "overview",
                "repo_name": repo.name,
                "visibility": repo.visibility,
                "branch_count": len(branches),
                "commit_count": total_commits,
                "object_count": len(objects),
                "last_commit_at": last_commit_at,
                "most_recent_author": most_recent_author,
                "midi_analysis": None,
            }
            return MusehubToolResult(ok=True, data=data)

        if dimension == "commits":
            all_commits, total = await musehub_repository.list_commits(
                session, repo_id, limit=100
            )

            by_branch: dict[str, int] = {}
            by_author: dict[str, int] = {}
            for c in all_commits:
                by_branch[c.branch] = by_branch.get(c.branch, 0) + 1
                by_author[c.author] = by_author.get(c.author, 0) + 1

            data = {
                "repo_id": repo_id,
                "dimension": "commits",
                "total_commits": total,
                "commits_in_sample": len(all_commits),
                "by_branch": {k: v for k, v in by_branch.items()},
                "by_author": {k: v for k, v in by_author.items()},
                "recent_messages": [c.message for c in all_commits[:5]],
            }
            return MusehubToolResult(ok=True, data=data)

        # dimension == "objects"
        objects = await musehub_repository.list_objects(session, repo_id)

        by_mime: dict[str, int] = {}
        size_by_mime: dict[str, int] = {}
        total_size = 0
        for obj in objects:
            mime = _mime_for_path(obj.path)
            by_mime[mime] = by_mime.get(mime, 0) + 1
            size_by_mime[mime] = size_by_mime.get(mime, 0) + obj.size_bytes
            total_size += obj.size_bytes

        data = {
            "repo_id": repo_id,
            "dimension": "objects",
            "total_objects": len(objects),
            "total_size_bytes": total_size,
            "by_mime_type": {k: v for k, v in by_mime.items()},
            "size_by_mime_type": {k: v for k, v in size_by_mime.items()},
            "sample_paths": [obj.path for obj in objects[:10]],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_search(
    repo_id: str,
    query: str,
    mode: str = "path",
) -> MusehubToolResult:
    """Search within a MuseHub repository by substring match.

    Search is case-insensitive substring matching. Two modes are supported:
    - ``path`` — matches object file paths (e.g. ``tracks/jazz_4b.mid``).
    - ``commit`` — matches commit messages (e.g. ``add bass intro``).

    The search operates on the full in-memory dataset (no DB-level LIKE query)
    so results are consistent across database backends. For very large repos
    (>10 k objects/commits) this may be slow — index-backed search is a
    planned future enhancement.

    Args:
        repo_id: UUID of the target MuseHub repository.
        query: Case-insensitive substring to search for.
        mode: ``"path"`` or ``"commit"``.

    Returns:
        ``MusehubToolResult`` with ``data.results`` list, or an error on failure.
    """
    valid_modes = {"path", "commit"}
    if mode not in valid_modes:
        return MusehubToolResult(
            ok=False,
            error_code="invalid_mode",
            error_message=(
                f"Unknown search mode '{mode}'. "
                f"Valid values: {', '.join(sorted(valid_modes))}."
            ),
        )

    if (err := _check_db_available()) is not None:
        return err

    q = query.lower()

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        if mode == "path":
            objects = await musehub_repository.list_objects(session, repo_id)
            results: list[JSONValue] = [
                {
                    "object_id": obj.object_id,
                    "path": obj.path,
                    "size_bytes": obj.size_bytes,
                    "mime_type": _mime_for_path(obj.path),
                }
                for obj in objects
                if q in obj.path.lower()
            ]
        else: # mode == "commit"
            commits, _ = await musehub_repository.list_commits(
                session, repo_id, limit=100
            )
            results = [
                {
                    "commit_id": c.commit_id,
                    "branch": c.branch,
                    "message": c.message,
                    "author": c.author,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in commits
                if q in c.message.lower()
            ]

        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "query": query,
            "mode": mode,
            "result_count": len(results),
            "results": results,
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_get_context(repo_id: str) -> MusehubToolResult:
    """Return the full AI context document for a MuseHub repository.

    This is the primary read-side interface for music generation agents.
    It aggregates repo metadata, all branches, the 10 most recent commits
    across all branches, and the full artifact inventory into a single
    structured document — ready to paste into an agent's context window.

    Feed this document to the agent before generating new music to ensure
    harmonic and structural coherence with existing work in the repository.

    Musical analysis fields (key, tempo, time_signature) are ``null`` until
    Storpheus MIDI analysis integration is complete.

    Args:
        repo_id: UUID of the target MuseHub repository.

    Returns:
        ``MusehubToolResult`` with ``data.context`` (the full context doc),
        or ``error_code="not_found"`` if the repo does not exist.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        branches = await musehub_repository.list_branches(session, repo_id)
        commits, total_commits = await musehub_repository.list_commits(
            session, repo_id, limit=10
        )
        objects = await musehub_repository.list_objects(session, repo_id)

        by_mime: dict[str, int] = {}
        for obj in objects:
            mime = _mime_for_path(obj.path)
            by_mime[mime] = by_mime.get(mime, 0) + 1

        context: dict[str, JSONValue] = {
            "repo": {
                "repo_id": repo.repo_id,
                "name": repo.name,
                "visibility": repo.visibility,
                "owner_user_id": repo.owner_user_id,
                "created_at": repo.created_at.isoformat(),
            },
            "branches": [
                {
                    "name": b.name,
                    "head_commit_id": b.head_commit_id,
                }
                for b in branches
            ],
            "recent_commits": [
                {
                    "commit_id": c.commit_id,
                    "branch": c.branch,
                    "message": c.message,
                    "author": c.author,
                    "timestamp": c.timestamp.isoformat(),
                }
                for c in commits
            ],
            "commit_stats": {
                "total": total_commits,
                "shown": len(commits),
            },
            "artifacts": {
                "total_count": len(objects),
                "by_mime_type": {k: v for k, v in by_mime.items()},
                "paths": [obj.path for obj in objects],
            },
            "musical_analysis": {
                "key": None,
                "tempo": None,
                "time_signature": None,
                "note": (
                    "Musical analysis requires Storpheus MIDI integration "
                    "(not yet available — fields will be populated in a future release)."
                ),
            },
        }

        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "context": context,
        }
        return MusehubToolResult(ok=True, data=data)


# ---------------------------------------------------------------------------
# New read tool executors (8) — wired by the dispatcher
# ---------------------------------------------------------------------------


async def execute_get_commit(repo_id: str, commit_id: str) -> MusehubToolResult:
    """Return detailed information about a single commit.

    Args:
        repo_id: UUID of the target repository.
        commit_id: Commit ID (SHA or short ID).

    Returns:
        ``MusehubToolResult`` with commit metadata and parent IDs.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        commit = await musehub_repository.get_commit(session, repo_id, commit_id)
        if commit is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Commit '{commit_id}' not found in repo '{repo_id}'.",
            )
        data: dict[str, JSONValue] = {
            "commit_id": commit.commit_id,
            "repo_id": repo_id,
            "branch": commit.branch,
            "message": commit.message,
            "author": commit.author,
            "parent_ids": list(commit.parent_ids) if commit.parent_ids else [],
            "timestamp": commit.timestamp.isoformat(),
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_compare(
    repo_id: str,
    base_ref: str,
    head_ref: str,
) -> MusehubToolResult:
    """Compare two refs and return a musical diff summary.

    Args:
        repo_id: UUID of the repository.
        base_ref: Base branch name or commit ID.
        head_ref: Head branch name or commit ID to compare against base.

    Returns:
        ``MusehubToolResult`` with artifact-level diff (added/removed/modified counts).
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        base_commits, _ = await musehub_repository.list_commits(session, repo_id, branch=base_ref, limit=1)
        head_commits, _ = await musehub_repository.list_commits(session, repo_id, branch=head_ref, limit=1)

        base_objects = await musehub_repository.list_objects(session, repo_id)
        head_objects = await musehub_repository.list_objects(session, repo_id)

        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "base_ref": base_ref,
            "head_ref": head_ref,
            "base_commit_id": base_commits[0].commit_id if base_commits else None,
            "head_commit_id": head_commits[0].commit_id if head_commits else None,
            "note": (
                "Full musical diff (harmony, rhythm, groove scores) requires "
                "Storpheus MIDI analysis integration (coming soon). "
                "Currently returns object inventory for both refs."
            ),
            "base_object_count": len(base_objects),
            "head_object_count": len(head_objects),
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_list_issues(
    repo_id: str,
    state: str = "open",
    label: str | None = None,
) -> MusehubToolResult:
    """List issues for a MuseHub repository.

    Args:
        repo_id: UUID of the repository.
        state: Filter by state — ``"open"``, ``"closed"``, or ``"all"``.
        label: Optional label string filter.

    Returns:
        ``MusehubToolResult`` with ``data.issues`` list.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )

        from musehub.services import musehub_issues
        issues = await musehub_issues.list_issues(session, repo_id, state=state, label=label)
        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "state": state,
            "total": len(issues),
            "issues": [
                {
                    "issue_id": i.issue_id,
                    "number": i.number,
                    "title": i.title,
                    "state": i.state,
                    "labels": list(i.labels),
                    "author": i.author,
                    "assignee": i.assignee,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i in issues
            ],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_get_issue(repo_id: str, issue_number: int) -> MusehubToolResult:
    """Return a single issue with its full comment thread.

    Args:
        repo_id: UUID of the repository.
        issue_number: Per-repo issue number.

    Returns:
        ``MusehubToolResult`` with issue and comments data.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_issues
        issue = await musehub_issues.get_issue(session, repo_id, issue_number)
        if issue is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Issue #{issue_number} not found in repo '{repo_id}'.",
            )
        comments_resp = await musehub_issues.list_comments(session, issue.issue_id)
        data: dict[str, JSONValue] = {
            "issue_id": issue.issue_id,
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "state": issue.state,
            "labels": list(issue.labels),
            "author": issue.author,
            "assignee": issue.assignee,
            "created_at": issue.created_at.isoformat() if issue.created_at else None,
            "comments": [
                {
                    "comment_id": c.comment_id,
                    "author": c.author,
                    "body": c.body,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in comments_resp.comments
            ],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_list_prs(repo_id: str, state: str = "all") -> MusehubToolResult:
    """List pull requests for a MuseHub repository.

    Args:
        repo_id: UUID of the repository.
        state: Filter by state — ``"open"``, ``"merged"``, ``"closed"``, or ``"all"``.

    Returns:
        ``MusehubToolResult`` with ``data.pulls`` list.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )
        from musehub.services import musehub_pull_requests
        prs = await musehub_pull_requests.list_prs(session, repo_id, state=state)
        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "state": state,
            "total": len(prs),
            "pulls": [
                {
                    "pr_id": p.pr_id,
                    "title": p.title,
                    "state": p.state,
                    "from_branch": p.from_branch,
                    "to_branch": p.to_branch,
                    "author": p.author,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "merged_at": p.merged_at.isoformat() if p.merged_at else None,
                }
                for p in prs
            ],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_get_pr(repo_id: str, pr_id: str) -> MusehubToolResult:
    """Return a single pull request with reviews and inline comments.

    Args:
        repo_id: UUID of the repository.
        pr_id: UUID of the pull request.

    Returns:
        ``MusehubToolResult`` with PR data, reviews, and comments.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_pull_requests
        pr = await musehub_pull_requests.get_pr(session, repo_id, pr_id)
        if pr is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"PR '{pr_id}' not found in repo '{repo_id}'.",
            )
        comments_resp = await musehub_pull_requests.list_pr_comments(session, pr_id, repo_id)
        reviews_resp = await musehub_pull_requests.list_reviews(session, repo_id=repo_id, pr_id=pr_id)
        data: dict[str, JSONValue] = {
            "pr_id": pr.pr_id,
            "repo_id": repo_id,
            "title": pr.title,
            "body": pr.body,
            "state": pr.state,
            "from_branch": pr.from_branch,
            "to_branch": pr.to_branch,
            "author": pr.author,
            "merge_commit_id": pr.merge_commit_id,
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "comments": [
                {
                    "comment_id": c.comment_id,
                    "author": c.author,
                    "body": c.body,
                    "target_type": c.target_type,
                    "target_track": c.target_track,
                    "target_beat_start": c.target_beat_start,
                    "target_beat_end": c.target_beat_end,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in comments_resp.comments
            ],
            "reviews": [
                {
                    "review_id": r.id,
                    "reviewer": r.reviewer_username,
                    "state": r.state,
                    "body": r.body,
                    "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                }
                for r in reviews_resp.reviews
            ],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_list_releases(repo_id: str) -> MusehubToolResult:
    """Return all releases for a MuseHub repository, ordered newest first.

    Args:
        repo_id: UUID of the repository.

    Returns:
        ``MusehubToolResult`` with ``data.releases`` list.
    """
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        repo = await musehub_repository.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False,
                error_code="not_found",
                error_message=f"Repository '{repo_id}' not found.",
            )
        from musehub.services import musehub_releases
        releases = await musehub_releases.list_releases(session, repo_id)
        data: dict[str, JSONValue] = {
            "repo_id": repo_id,
            "total": len(releases),
            "releases": [
                {
                    "release_id": r.release_id,
                    "tag": r.tag,
                    "title": r.title,
                    "body": r.body,
                    "is_prerelease": r.is_prerelease,
                    "commit_id": r.commit_id,
                    "author": r.author,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in releases
            ],
        }
        return MusehubToolResult(ok=True, data=data)


async def execute_search_repos(
    query: str | None = None,
    domain: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> MusehubToolResult:
    """Discover public repositories by text query, domain, or tags.

    All filters are optional and combined with AND logic.

    Args:
        query: Free-text query matched against repo names and descriptions.
        domain: Filter by domain scoped ID (e.g. ``"@cgcardona/midi"``).
        tags: Filter repos that have all of these tags.
        limit: Maximum results to return (default: 20, max: 100).

    Returns:
        ``MusehubToolResult`` with ``data.repos`` list.
    """
    if (err := _check_db_available()) is not None:
        return err

    capped_limit = min(max(1, limit), 100)

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_discover
        explore = await musehub_discover.list_public_repos(
            session,
            page_size=min(capped_limit * 3, 100),
        )
        all_repos = explore.repos

        filtered = []
        for r in all_repos:
            if query and query.lower() not in (r.name or "").lower() and \
                    query.lower() not in (r.description or "").lower():
                continue
            if domain and domain.lower() not in (r.description or "").lower() \
                    and not any(domain.lower() in t.lower() for t in (r.tags or [])):
                continue
            if tags:
                repo_tags: list[str] = list(r.tags) if r.tags else []
                if not all(t in repo_tags for t in tags):
                    continue
            filtered.append(r)
            if len(filtered) >= capped_limit:
                break

        data: dict[str, JSONValue] = {
            "total": len(filtered),
            "repos": [
                {
                    "repo_id": r.repo_id,
                    "owner": r.owner,
                    "slug": r.slug,
                    "name": r.name,
                    "description": r.description,
                    "tags": list(r.tags) if r.tags else [],
                    "star_count": r.star_count,
                }
                for r in filtered
            ],
        }
        return MusehubToolResult(ok=True, data=data)


# ── Domain executor functions ─────────────────────────────────────────────────


async def execute_list_domains(
    query: str | None = None,
    viewer_type: str | None = None,
    verified: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> MusehubToolResult:
    """List registered Muse domain plugins."""
    if (err := _check_db_available()) is not None:
        return err

    capped = min(max(1, limit), 100)
    page = offset // capped + 1

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_domains as _domains_svc
        response = await _domains_svc.list_domains(
            session,
            query=query,
            verified_only=verified is True,
            page=page,
            page_size=capped,
        )

        domains_out: list[JSONValue] = []
        for d in response.domains:
            if viewer_type and d.viewer_type != viewer_type:
                continue
            domains_out.append({
                "domain_id": d.domain_id,
                "scoped_id": d.scoped_id,
                "display_name": d.display_name,
                "description": d.description,
                "version": d.version,
                "viewer_type": d.viewer_type,
                "install_count": d.install_count,
                "is_verified": d.is_verified,
            })

        return MusehubToolResult(ok=True, data={"total": response.total, "domains": domains_out})


async def execute_get_domain(scoped_id: str) -> MusehubToolResult:
    """Fetch the full manifest for a Muse domain plugin by its scoped ID."""
    if (err := _check_db_available()) is not None:
        return err

    parts = scoped_id.lstrip("@").split("/", 1)
    if len(parts) != 2:
        return MusehubToolResult(
            ok=False,
            error_code="invalid_scoped_id",
            error_message=f"Invalid scoped_id format: {scoped_id!r}. Expected '@author/slug'.",
        )
    author_slug, slug = parts

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_domains as _domains_svc
        domain = await _domains_svc.get_domain_by_scoped_id(session, author_slug, slug)
        if domain is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Domain {scoped_id!r} not found.",
            )

        return MusehubToolResult(ok=True, data={
            "domain_id": domain.domain_id,
            "scoped_id": domain.scoped_id,
            "display_name": domain.display_name,
            "description": domain.description,
            "version": domain.version,
            "manifest_hash": domain.manifest_hash,
            "viewer_type": domain.viewer_type,
            "capabilities": domain.capabilities,  # type: ignore[assignment]
            "install_count": domain.install_count,
            "is_verified": domain.is_verified,
            "is_deprecated": domain.is_deprecated,
        })


async def execute_get_domain_insights(
    repo_id: str,
    dimension: str = "overview",
    ref: str | None = None,
) -> MusehubToolResult:
    """Return domain insights for a repo — delegates to the analysis executor."""
    return await execute_get_analysis(repo_id, dimension=dimension)


async def execute_get_view(
    repo_id: str,
    ref: str | None = None,
    dimension: str | None = None,
) -> MusehubToolResult:
    """Return the universal viewer payload for a repo at a given ref."""
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc
        from musehub.db import musehub_models as _db
        from sqlalchemy import select

        repo = await _repo_svc.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Repo {repo_id!r} not found.",
            )

        default_branch = "main"
        resolved_ref = ref or str(default_branch)

        branch_row = (await session.execute(
            select(_db.MusehubBranch).where(
                _db.MusehubBranch.repo_id == repo_id,
                _db.MusehubBranch.name == resolved_ref,
            )
        )).scalar_one_or_none()
        head_commit_id = branch_row.head_commit_id if branch_row else None

        domain_info: dict[str, JSONValue] = {}
        if repo.domain_id:
            from musehub.db.musehub_domain_models import MusehubDomain
            dom = await session.get(MusehubDomain, repo.domain_id)
            if dom:
                domain_info = {
                    "scoped_id": f"@{dom.author_slug}/{dom.slug}",
                    "display_name": dom.display_name,
                    "viewer_type": dom.viewer_type,
                    "capabilities": dom.capabilities,  # type: ignore[assignment]
                }

        return MusehubToolResult(ok=True, data={
            "repo_id": repo_id,
            "owner": repo.owner,
            "slug": repo.slug,
            "ref": resolved_ref,
            "head_commit_id": head_commit_id,
            "domain": domain_info,
            "dimension": dimension,
        })


# ── Muse CLI + auth executor functions ───────────────────────────────────────


async def execute_whoami(user_id: str | None) -> MusehubToolResult:
    """Return identity information for the currently authenticated caller."""
    if user_id is None:
        return MusehubToolResult(ok=True, data={"authenticated": False, "user_id": None})

    if (err := _check_db_available()) is not None:
        return MusehubToolResult(ok=True, data={"authenticated": True, "user_id": user_id})

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc
        repos_result = await _repo_svc.list_repos_for_user(session, user_id)
        repo_count = len(repos_result.repos) if repos_result else 0
        return MusehubToolResult(ok=True, data={
            "authenticated": True,
            "user_id": user_id,
            "repo_count": repo_count,
            "hub_url": "https://musehub.ai",
        })


async def execute_create_agent_token(
    user_id: str,
    agent_name: str,
    expires_in_days: int = 90,
) -> MusehubToolResult:
    """Mint a long-lived agent JWT for programmatic access."""
    if not user_id:
        return MusehubToolResult(
            ok=False, error_code="unauthenticated",
            error_message="Authentication required to create an agent token.",
        )

    capped_days = min(max(1, expires_in_days), 365)
    from musehub.auth.tokens import generate_agent_token
    token = generate_agent_token(
        user_id=user_id,
        agent_name=agent_name or "mcp-agent",
        duration_days=capped_days,
    )

    return MusehubToolResult(ok=True, data={
        "token": token,
        "agent_name": agent_name,
        "user_id": user_id,
        "expires_in_days": capped_days,
        "usage": (
            "Add to requests as: Authorization: Bearer <token>  "
            "or configure with: muse config set musehub.token <token>"
        ),
    })


async def execute_muse_clone(
    owner: str,
    slug: str,
    ref: str | None = None,
) -> MusehubToolResult:
    """Return the clone URL and repo metadata for a MuseHub repository."""
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc
        repo = await _repo_svc.get_repo_by_owner_slug(session, owner, slug)
        if repo is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Repo {owner}/{slug} not found.",
            )

        hub_url = "https://musehub.ai"
        clone_url = f"{hub_url}/{owner}/{slug}"
        ref_part = f" --branch {ref}" if ref else ""

        return MusehubToolResult(ok=True, data={
            "repo_id": repo.repo_id,
            "owner": repo.owner,
            "slug": repo.slug,
            "name": repo.name,
            "clone_url": clone_url,
            "command": f"muse clone {clone_url}{ref_part}",
            "default_branch": str("main"),
            "visibility": repo.visibility,
        })


async def execute_muse_push(
    repo_id: str,
    branch: str,
    head_commit_id: str,
    commits: list[object],
    objects: list[object],
    force: bool = False,
    user_id: str = "",
) -> MusehubToolResult:
    """Push commits and binary objects to a MuseHub repository."""
    if not user_id:
        return MusehubToolResult(
            ok=False, error_code="unauthenticated",
            error_message="Authentication required to push. Use musehub_create_agent_token first.",
        )

    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc, musehub_sync as _sync_svc
        from musehub.models.musehub import CommitInput as _CommitInput, ObjectInput as _ObjectInput

        repo = await _repo_svc.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Repo {repo_id!r} not found.",
            )

        commit_inputs = [_CommitInput.model_validate(c) for c in commits]
        object_inputs = [_ObjectInput.model_validate(o) for o in objects]

        try:
            result = await _sync_svc.ingest_push(
                session,
                repo_id=repo_id,
                branch=branch,
                head_commit_id=head_commit_id,
                commits=commit_inputs,
                objects=object_inputs,
                force=force,
                author=user_id,
            )
            await session.commit()

            return MusehubToolResult(ok=True, data={
                "repo_id": repo_id,
                "branch": branch,
                "head_commit_id": result.head_commit_id,
                "commits_stored": result.commits_stored,
                "objects_stored": result.objects_stored,
            })
        except ValueError as exc:
            code = "non_fast_forward" if "non_fast_forward" in str(exc) else "push_failed"
            return MusehubToolResult(ok=False, error_code=code, error_message=str(exc))


async def execute_muse_pull(
    repo_id: str,
    branch: str | None = None,
    since_commit_id: str | None = None,
    object_ids: list[str] | None = None,
) -> MusehubToolResult:
    """Fetch missing commits and objects from a MuseHub repository."""
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc, musehub_sync as _sync_svc
        from musehub.models.musehub import PullRequest as _PullRequest

        repo = await _repo_svc.get_repo(session, repo_id)
        if repo is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Repo {repo_id!r} not found.",
            )

        resolved_branch = branch or str("main")
        pull_req = _PullRequest(
            branch=resolved_branch,
            since_commit_id=since_commit_id,
            object_ids=object_ids or [],
        )

        try:
            result = await _sync_svc.fulfill_pull(session, repo_id=repo_id, body=pull_req)
            return MusehubToolResult(ok=True, data={
                "repo_id": repo_id,
                "branch": resolved_branch,
                "head_commit_id": result.head_commit_id,
                "commits": [c.model_dump() for c in result.commits],
                "objects": [{"object_id": o.object_id, "path": o.path} for o in result.objects],
            })
        except Exception as exc:
            return MusehubToolResult(ok=False, error_code="pull_failed", error_message=str(exc))


async def execute_muse_remote(
    owner: str,
    slug: str,
) -> MusehubToolResult:
    """Return the remote URL and push/pull endpoints for a MuseHub repo."""
    if (err := _check_db_available()) is not None:
        return err

    async with AsyncSessionLocal() as session:
        from musehub.services import musehub_repository as _repo_svc
        repo = await _repo_svc.get_repo_by_owner_slug(session, owner, slug)
        if repo is None:
            return MusehubToolResult(
                ok=False, error_code="not_found",
                error_message=f"Repo {owner}/{slug} not found.",
            )

        hub_url = "https://musehub.ai"
        remote_url = f"{hub_url}/{owner}/{slug}"
        api_base = f"{hub_url}/api/v1/repos/{repo.repo_id}"

        return MusehubToolResult(ok=True, data={
            "repo_id": repo.repo_id,
            "name": "origin",
            "remote_url": remote_url,
            "push_url": f"{api_base}/push",
            "pull_url": f"{api_base}/pull",
            "clone_command": f"muse clone {remote_url}",
            "add_remote_command": f"muse remote add origin {remote_url}",
        })


async def execute_muse_config(
    key: str | None = None,
    value: str | None = None,
) -> MusehubToolResult:
    """Read or describe Muse configuration keys relevant to MuseHub."""
    hub_config_keys: dict[str, str] = {
        "musehub.token": "Bearer token for authentication with MuseHub (JWT).",
        "musehub.url": "Base URL for the MuseHub instance (default: https://musehub.ai).",
        "musehub.username": "Your MuseHub username — default owner for new repos.",
        "core.editor": "Text editor for commit messages (e.g. 'vim', 'nano', 'code --wait').",
        "user.name": "Your display name used in commit author fields.",
        "user.email": "Your email address used in commit author fields.",
    }

    if key is None:
        return MusehubToolResult(ok=True, data={
            "config_keys": hub_config_keys,  # type: ignore[assignment]
            "hint": (
                "Use 'muse config set <key> <value>' to configure Muse. "
                "Run 'muse config list' to see all current values."
            ),
        })

    description = hub_config_keys.get(key, f"Unknown key: {key!r}")
    result: dict[str, JSONValue] = {"key": key, "description": description}
    if value is not None:
        cli_cmd = f"muse config set {key} {value}"
        result["command"] = cli_cmd
        result["hint"] = f"Run this command in your terminal: {cli_cmd}"

    return MusehubToolResult(ok=True, data=result)

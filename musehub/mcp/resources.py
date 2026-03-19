"""MuseHub MCP Resource catalogue — ``musehub://`` URI scheme.

Resources are side-effect-free, cacheable reads addressable by URI.
Every resource returns ``application/json``.

## URI design

Static resources (5):
  musehub://trending          — top public repos by star count
  musehub://me                — authenticated user profile + pinned repos
  musehub://me/notifications  — unread notification inbox
  musehub://me/starred        — repos the authenticated user has starred
  musehub://me/feed           — activity feed for watched repos

Templated resources (15, RFC 6570 Level 1):
  musehub://repos/{owner}/{slug}
  musehub://repos/{owner}/{slug}/branches
  musehub://repos/{owner}/{slug}/commits
  musehub://repos/{owner}/{slug}/commits/{commit_id}
  musehub://repos/{owner}/{slug}/tree/{ref}
  musehub://repos/{owner}/{slug}/blob/{ref}/{path}
  musehub://repos/{owner}/{slug}/issues
  musehub://repos/{owner}/{slug}/issues/{number}
  musehub://repos/{owner}/{slug}/pulls
  musehub://repos/{owner}/{slug}/pulls/{number}
  musehub://repos/{owner}/{slug}/releases
  musehub://repos/{owner}/{slug}/releases/{tag}
  musehub://repos/{owner}/{slug}/analysis/{ref}
  musehub://repos/{owner}/{slug}/timeline
  musehub://users/{username}

## Ownership / auth

The dispatcher passes ``user_id`` extracted from the JWT (or ``None`` for
anonymous requests). Resource handlers check repo visibility and return a
structured error dict when the caller lacks access.
"""
from __future__ import annotations


import logging
import re
from typing import TypedDict, Required, NotRequired

from musehub.contracts.json_types import JSONValue

logger = logging.getLogger(__name__)


# ── Catalogue TypedDicts ──────────────────────────────────────────────────────


class MCPResource(TypedDict, total=False):
    """A concrete MCP resource (static URI)."""

    uri: Required[str]
    name: Required[str]
    description: str
    mimeType: str  # noqa: N815


class MCPResourceTemplate(TypedDict, total=False):
    """An MCP resource template (RFC 6570 URI template)."""

    uriTemplate: Required[str]  # noqa: N815
    name: Required[str]
    description: str
    mimeType: str  # noqa: N815


class MCPResourceContent(TypedDict):
    """The content object returned inside a ``resources/read`` response."""

    uri: str
    mimeType: str  # noqa: N815
    text: str


# ── Static resource catalogue ─────────────────────────────────────────────────

STATIC_RESOURCES: list[MCPResource] = [
    {
        "uri": "musehub://trending",
        "name": "Trending Repositories",
        "description": (
            "Top public MuseHub repositories ranked by recent star count. "
            "Use this to discover popular music projects before browsing or forking."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": "musehub://me",
        "name": "My Profile",
        "description": (
            "Authenticated user's profile, public stats, and pinned repositories. "
            "Requires authentication."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": "musehub://me/notifications",
        "name": "My Notifications",
        "description": (
            "Unread notification inbox for the authenticated user: "
            "PR reviews, issue mentions, and new comments. Requires authentication."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": "musehub://me/starred",
        "name": "My Starred Repositories",
        "description": (
            "Repositories the authenticated user has starred. Requires authentication."
        ),
        "mimeType": "application/json",
    },
    {
        "uri": "musehub://me/feed",
        "name": "My Activity Feed",
        "description": (
            "Recent activity (commits, PRs, issues) across repositories the "
            "authenticated user watches. Requires authentication."
        ),
        "mimeType": "application/json",
    },
]

# ── Resource template catalogue ───────────────────────────────────────────────

RESOURCE_TEMPLATES: list[MCPResourceTemplate] = [
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}",
        "name": "Repository Overview",
        "description": "Metadata, stats, and recent activity for a public repository.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/branches",
        "name": "Repository Branches",
        "description": "All branches with their head commit IDs.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/commits",
        "name": "Repository Commits",
        "description": "Paginated commit history (newest first) across all branches.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/commits/{commit_id}",
        "name": "Single Commit",
        "description": "Detailed commit metadata including parent IDs and artifact snapshot.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/tree/{ref}",
        "name": "File Tree",
        "description": "All artifact paths and MIME types at the given branch or commit ref.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/blob/{ref}/{path}",
        "name": "File Metadata",
        "description": "Metadata for a single artifact (path, size, MIME type, object ID).",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/issues",
        "name": "Issues",
        "description": "Open issues for the repository.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/issues/{number}",
        "name": "Single Issue",
        "description": "A single issue with its full comment thread.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/pulls",
        "name": "Pull Requests",
        "description": "Pull requests for the repository.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/pulls/{number}",
        "name": "Single Pull Request",
        "description": "A single pull request with reviews and inline musical comments.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/releases",
        "name": "Releases",
        "description": "All releases ordered newest first.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/releases/{tag}",
        "name": "Single Release",
        "description": "A specific release by tag with asset download counts.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/analysis/{ref}",
        "name": "Musical Analysis",
        "description": "Structured harmonic, rhythmic, and groove analysis at a given ref.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://repos/{owner}/{slug}/timeline",
        "name": "Musical Timeline",
        "description": "Chronological evolution of the repository's musical content.",
        "mimeType": "application/json",
    },
    {
        "uriTemplate": "musehub://users/{username}",
        "name": "User Profile",
        "description": "Public profile and list of public repositories for a user.",
        "mimeType": "application/json",
    },
]


# ── URI router ────────────────────────────────────────────────────────────────


def _err(message: str) -> dict[str, JSONValue]:
    return {"error": message}


async def read_resource(uri: str, user_id: str | None = None) -> dict[str, JSONValue]:
    """Dispatch a ``musehub://`` URI to the appropriate resource handler.

    Args:
        uri: The ``musehub://`` URI requested by the MCP client.
        user_id: Authenticated user ID from JWT, or ``None`` for anonymous access.

    Returns:
        JSON-serialisable dict. On auth/not-found errors, returns
        ``{"error": "<message>"}`` — the caller wraps this in an
        ``MCPResourceContent`` text block.
    """
    if not uri.startswith("musehub://"):
        return _err(f"Unsupported URI scheme: {uri!r}")

    path = uri[len("musehub://"):]

    # ── Static resources ─────────────────────────────────────────────────────

    if path == "trending":
        return await _read_trending()
    if path == "me":
        return await _read_me(user_id)
    if path == "me/notifications":
        return await _read_me_notifications(user_id)
    if path == "me/starred":
        return await _read_me_starred(user_id)
    if path == "me/feed":
        return await _read_me_feed(user_id)

    # ── Templated resources ──────────────────────────────────────────────────

    # musehub://repos/{owner}/{slug}[/...]
    m = re.match(r"^repos/([^/]+)/([^/]+)(/.*)?$", path)
    if m:
        owner, slug, rest = m.group(1), m.group(2), m.group(3) or ""
        return await _read_repo_resource(owner, slug, rest, user_id)

    # musehub://users/{username}
    m2 = re.match(r"^users/([^/]+)$", path)
    if m2:
        return await _read_user(m2.group(1))

    return _err(f"Unknown resource URI: {uri!r}")


# ── Resource handlers ─────────────────────────────────────────────────────────


async def _read_trending() -> dict[str, JSONValue]:
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_discover

    if _check_db_available() is not None:
        return _err("Database unavailable")

    try:
        async with AsyncSessionLocal() as session:
            explore = await musehub_discover.list_public_repos(session, sort="stars", page_size=20)
            return {
                "trending": [
                    {
                        "repo_id": r.repo_id,
                        "owner": r.owner,
                        "slug": r.slug,
                        "name": r.name,
                        "description": r.description,
                        "tags": list(r.tags) if r.tags else [],
                        "star_count": r.star_count,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in explore.repos
                ]
            }
    except Exception as exc:
        logger.exception("trending resource failed: %s", exc)
        return _err(str(exc))


async def _read_me(user_id: str | None) -> dict[str, JSONValue]:
    if user_id is None:
        return _err("Authentication required for musehub://me")
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_repository

    if _check_db_available() is not None:
        return _err("Database unavailable")

    try:
        async with AsyncSessionLocal() as session:
            repo_list = await musehub_repository.list_repos_for_user(session, user_id, limit=20)
            return {
                "user_id": user_id,
                "repos": [
                    {
                        "repo_id": r.repo_id,
                        "slug": r.slug,
                        "name": r.name,
                        "visibility": r.visibility,
                    }
                    for r in repo_list.repos
                ],
            }
    except Exception as exc:
        logger.exception("me resource failed: %s", exc)
        return _err(str(exc))


async def _read_me_notifications(user_id: str | None) -> dict[str, JSONValue]:
    if user_id is None:
        return _err("Authentication required for musehub://me/notifications")
    return {"user_id": user_id, "notifications": [], "note": "Notification inbox coming soon."}


async def _read_me_starred(user_id: str | None) -> dict[str, JSONValue]:
    if user_id is None:
        return _err("Authentication required for musehub://me/starred")
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_repository

    if _check_db_available() is not None:
        return _err("Database unavailable")

    try:
        async with AsyncSessionLocal() as session:
            starred_resp = await musehub_repository.get_user_starred(session, user_id)
            return {
                "user_id": user_id,
                "starred": [
                    {
                        "repo_id": entry.repo.repo_id,
                        "owner": entry.repo.owner,
                        "slug": entry.repo.slug,
                        "name": entry.repo.name,
                    }
                    for entry in starred_resp.starred
                ],
            }
    except Exception as exc:
        logger.exception("me/starred resource failed: %s", exc)
        return _err(str(exc))


async def _read_me_feed(user_id: str | None) -> dict[str, JSONValue]:
    if user_id is None:
        return _err("Authentication required for musehub://me/feed")
    return {"user_id": user_id, "events": [], "note": "Activity feed coming soon."}


async def _read_repo_resource(
    owner: str,
    slug: str,
    rest: str,
    user_id: str | None,
) -> dict[str, JSONValue]:
    """Route repo sub-resources once owner/slug have been extracted."""
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_repository

    if _check_db_available() is not None:
        return _err("Database unavailable")

    try:
        async with AsyncSessionLocal() as session:
            repo = await musehub_repository.get_repo_by_owner_slug(session, owner, slug)
            if repo is None:
                return _err(f"Repository '{owner}/{slug}' not found.")
            if repo.visibility != "public" and user_id is None:
                return _err(f"Repository '{owner}/{slug}' is private. Authentication required.")

            repo_id = repo.repo_id

            if rest == "" or rest == "/":
                return await _repo_overview(session, repo, repo_id)
            if rest == "/branches":
                return await _repo_branches(session, repo_id)
            if rest == "/commits":
                return await _repo_commits(session, repo_id)
            if rest == "/issues":
                return await _repo_issues(session, repo_id)
            if rest == "/pulls":
                return await _repo_pulls(session, repo_id)
            if rest == "/releases":
                return await _repo_releases(session, repo_id)

            m = re.match(r"^/commits/(.+)$", rest)
            if m:
                return await _repo_commit(session, repo_id, m.group(1))

            m = re.match(r"^/tree/([^/]+)$", rest)
            if m:
                return await _repo_tree(session, repo_id, m.group(1))

            m = re.match(r"^/blob/([^/]+)/(.+)$", rest)
            if m:
                return await _repo_blob(session, repo_id, m.group(1), m.group(2))

            m = re.match(r"^/issues/(\d+)$", rest)
            if m:
                return await _repo_issue(session, repo_id, int(m.group(1)))

            m = re.match(r"^/pulls/(.+)$", rest)
            if m:
                return await _repo_pull(session, repo_id, m.group(1))

            m = re.match(r"^/releases/(.+)$", rest)
            if m:
                return await _repo_release_by_tag(session, repo_id, m.group(1))

            m = re.match(r"^/analysis/(.+)$", rest)
            if m:
                return await _repo_analysis(session, repo_id, m.group(1))

            if rest == "/timeline":
                return await _repo_timeline(session, repo_id)

            return _err(f"Unknown resource path: musehub://repos/{owner}/{slug}{rest}")
    except Exception as exc:
        logger.exception("repo resource failed (%s/%s%s): %s", owner, slug, rest, exc)
        return _err(str(exc))


# ── Sub-resource helpers ──────────────────────────────────────────────────────


async def _repo_overview(session: object, repo: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    branches = await musehub_repository.list_branches(session, repo_id)
    commits, total = await musehub_repository.list_commits(session, repo_id, limit=5)

    from musehub.models.musehub import RepoResponse  # local import
    assert isinstance(repo, RepoResponse)

    return {
        "repo_id": repo_id,
        "owner": repo.owner,
        "slug": repo.slug,
        "name": repo.name,
        "description": repo.description,
        "visibility": repo.visibility,
        "tags": list(repo.tags) if repo.tags else [],
        "key_signature": repo.key_signature,
        "tempo_bpm": repo.tempo_bpm,
        "branch_count": len(branches),
        "total_commits": total,
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
        "created_at": repo.created_at.isoformat() if repo.created_at else None,
    }


async def _repo_branches(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    branches = await musehub_repository.list_branches(session, repo_id)
    return {
        "repo_id": repo_id,
        "branches": [
            {"name": b.name, "head_commit_id": b.head_commit_id}
            for b in branches
        ],
    }


async def _repo_commits(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    commits, total = await musehub_repository.list_commits(session, repo_id, limit=20)
    return {
        "repo_id": repo_id,
        "total": total,
        "commits": [
            {
                "commit_id": c.commit_id,
                "branch": c.branch,
                "message": c.message,
                "author": c.author,
                "timestamp": c.timestamp.isoformat(),
            }
            for c in commits
        ],
    }


async def _repo_commit(session: object, repo_id: str, commit_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    commit = await musehub_repository.get_commit(session, repo_id, commit_id)
    if commit is None:
        return _err(f"Commit '{commit_id}' not found.")
    return {
        "commit_id": commit.commit_id,
        "repo_id": repo_id,
        "branch": commit.branch,
        "message": commit.message,
        "author": commit.author,
        "parent_ids": list(commit.parent_ids) if commit.parent_ids else [],
        "timestamp": commit.timestamp.isoformat(),
    }


async def _repo_tree(session: object, repo_id: str, ref: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    try:
        tree_resp = await musehub_repository.list_tree(session, repo_id, "", "", ref, "")
        return {
            "repo_id": repo_id,
            "ref": ref,
            "entries": [
                {
                    "type": e.type,
                    "name": e.name,
                    "path": e.path,
                    "size_bytes": e.size_bytes,
                }
                for e in tree_resp.entries
            ],
        }
    except Exception as exc:
        return _err(str(exc))


async def _repo_blob(
    session: object, repo_id: str, ref: str, path: str
) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    import mimetypes as _mt
    obj = await musehub_repository.get_object_by_path(session, repo_id, path)
    if obj is None:
        return _err(f"File '{path}' not found in repo '{repo_id}' at ref '{ref}'.")
    guessed, _ = _mt.guess_type(obj.path)
    return {
        "repo_id": repo_id,
        "ref": ref,
        "path": obj.path,
        "object_id": obj.object_id,
        "size_bytes": obj.size_bytes,
        "mime_type": guessed or "application/octet-stream",
    }


async def _repo_issues(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_issues
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    issues = await musehub_issues.list_issues(session, repo_id, state="open")
    return {
        "repo_id": repo_id,
        "issues": [
            {
                "issue_id": i.issue_id,
                "number": i.number,
                "title": i.title,
                "state": i.state,
                "labels": list(i.labels),
                "author": i.author,
            }
            for i in issues
        ],
    }


async def _repo_issue(session: object, repo_id: str, number: int) -> dict[str, JSONValue]:
    from musehub.services import musehub_issues
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    issue = await musehub_issues.get_issue(session, repo_id, number)
    if issue is None:
        return _err(f"Issue #{number} not found.")
    comments_resp = await musehub_issues.list_comments(session, issue.issue_id)
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


async def _repo_pulls(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_pull_requests
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    prs = await musehub_pull_requests.list_prs(session, repo_id, state="all")
    return {
        "repo_id": repo_id,
        "pulls": [
            {
                "pr_id": p.pr_id,
                "title": p.title,
                "state": p.state,
                "from_branch": p.from_branch,
                "to_branch": p.to_branch,
                "author": p.author,
            }
            for p in prs
        ],
    }


async def _repo_pull(session: object, repo_id: str, pr_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_pull_requests
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    pr = await musehub_pull_requests.get_pr(session, repo_id, pr_id)
    if pr is None:
        return _err(f"PR '{pr_id}' not found.")
    comments_resp = await musehub_pull_requests.list_pr_comments(session, pr_id, repo_id)
    reviews_resp = await musehub_pull_requests.list_reviews(session, repo_id=repo_id, pr_id=pr_id)
    return {
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
            }
            for c in comments_resp.comments
        ],
        "reviews": [
            {
                "review_id": r.id,
                "reviewer": r.reviewer_username,
                "state": r.state,
                "body": r.body,
            }
            for r in reviews_resp.reviews
        ],
    }


async def _repo_releases(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_releases
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    releases = await musehub_releases.list_releases(session, repo_id)
    return {
        "repo_id": repo_id,
        "releases": [
            {
                "release_id": r.release_id,
                "tag": r.tag,
                "title": r.title,
                "is_prerelease": r.is_prerelease,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in releases
        ],
    }


async def _repo_release_by_tag(session: object, repo_id: str, tag: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_releases
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    release = await musehub_releases.get_release_by_tag(session, repo_id, tag)
    if release is None:
        return _err(f"Release '{tag}' not found.")
    return {
        "release_id": release.release_id,
        "repo_id": repo_id,
        "tag": release.tag,
        "title": release.title,
        "body": release.body,
        "commit_id": release.commit_id,
        "is_prerelease": release.is_prerelease,
        "author": release.author,
        "created_at": release.created_at.isoformat() if release.created_at else None,
    }


async def _repo_analysis(session: object, repo_id: str, ref: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_mcp_executor
    result = await musehub_mcp_executor.execute_get_analysis(repo_id, dimension="overview")
    if not result.ok:
        return _err(result.error_message or "Analysis failed")
    return {"repo_id": repo_id, "ref": ref, "analysis": result.data}


async def _repo_timeline(session: object, repo_id: str) -> dict[str, JSONValue]:
    from musehub.services import musehub_repository
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)
    timeline = await musehub_repository.get_timeline_events(session, repo_id)
    return {
        "repo_id": repo_id,
        "total_commits": timeline.total_commits,
        "commits": [
            {
                "commit_id": c.commit_id,
                "branch": c.branch,
                "message": c.message,
                "author": c.author,
                "timestamp": c.timestamp.isoformat(),
            }
            for c in timeline.commits
        ],
        "sections": [
            {
                "section_name": s.section_name,
                "action": s.action,
                "timestamp": s.timestamp.isoformat(),
                "commit_id": s.commit_id,
            }
            for s in timeline.sections
        ],
        "tracks": [
            {
                "track_name": t.track_name,
                "action": t.action,
                "timestamp": t.timestamp.isoformat(),
                "commit_id": t.commit_id,
            }
            for t in timeline.tracks
        ],
    }


async def _read_user(username: str) -> dict[str, JSONValue]:
    from musehub.services.musehub_mcp_executor import _check_db_available
    from musehub.db.database import AsyncSessionLocal
    from musehub.services import musehub_repository

    if _check_db_available() is not None:
        return _err("Database unavailable")

    try:
        async with AsyncSessionLocal() as session:
            repo_list = await musehub_repository.list_repos_for_user(session, username, limit=20)
            return {
                "username": username,
                "repos": [
                    {
                        "repo_id": r.repo_id,
                        "slug": r.slug,
                        "name": r.name,
                        "visibility": r.visibility,
                    }
                    for r in repo_list.repos
                    if r.visibility == "public"
                ],
            }
    except Exception as exc:
        logger.exception("user resource failed (%s): %s", username, exc)
        return _err(str(exc))

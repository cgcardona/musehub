"""Deep API contract tests for core MuseHub endpoints.

This file addresses the shallow-assertion gap: many existing tests only
assert on status codes.  Here we verify complete response bodies, field
types, and envelope structure for the most critical endpoints — repos,
commits, branches, issues, and explore.

Uses ``tests.factories`` for clean, declarative data setup.
All tests are module-level async functions (not class-based) to ensure
pytest-asyncio fixture injection works correctly.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_repo, create_branch, create_commit


# ---------------------------------------------------------------------------
# Repo CRUD response contracts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_repo_response_shape(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """POST /repos returns all required fields with correct types."""
    resp = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "contract-test", "owner": "tester", "visibility": "public"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()

    for key in ("repoId", "name", "owner", "slug", "visibility", "ownerUserId",
                "cloneUrl", "createdAt"):
        assert key in body, f"Missing field: {key}"
        assert isinstance(body[key], str), f"Field {key} should be a string"

    assert body["name"] == "contract-test"
    assert body["owner"] == "tester"
    assert body["visibility"] == "public"
    assert body["slug"] == "contract-test"
    assert isinstance(body["tags"], list)


@pytest.mark.anyio
async def test_get_repo_response_shape(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """GET /repos/{id} returns all expected fields."""
    create = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "get-shape-test", "owner": "tester"},
        headers=auth_headers,
    )
    repo_id = create.json()["repoId"]

    resp = await client.get(f"/api/v1/musehub/repos/{repo_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["repoId"] == repo_id
    assert body["name"] == "get-shape-test"
    assert isinstance(body["tags"], list)
    assert isinstance(body["createdAt"], str)


@pytest.mark.anyio
async def test_update_repo_settings_returns_updated_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """PATCH /repos/{id}/settings returns the updated repo fields."""
    create = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "patch-test-repo", "owner": "patcher"},
        headers=auth_headers,
    )
    repo_id = create.json()["repoId"]

    patch_resp = await client.patch(
        f"/api/v1/musehub/repos/{repo_id}/settings",
        json={"description": "Updated description", "visibility": "public"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["description"] == "Updated description"
    assert body["visibility"] == "public"
    assert "name" in body  # RepoSettingsResponse fields


# ---------------------------------------------------------------------------
# Branch response contracts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_branches_envelope(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """GET /repos/{id}/branches returns a 'branches' list with name fields."""
    repo = await create_repo(db_session, owner="brancher", slug="branch-contract")
    await create_branch(db_session, repo_id=str(repo.repo_id), name="main")
    await create_branch(db_session, repo_id=str(repo.repo_id), name="feature-x")

    resp = await client.get(
        f"/api/v1/musehub/repos/{repo.repo_id}/branches",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "branches" in body
    assert isinstance(body["branches"], list)
    assert len(body["branches"]) == 2
    for branch in body["branches"]:
        assert "name" in branch
        assert isinstance(branch["name"], str)


@pytest.mark.anyio
async def test_branch_names_are_correct(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Branch names returned by the API match what was inserted."""
    repo = await create_repo(db_session, owner="brancher2", slug="branch-names")
    await create_branch(db_session, repo_id=str(repo.repo_id), name="develop")

    resp = await client.get(
        f"/api/v1/musehub/repos/{repo.repo_id}/branches",
        headers=auth_headers,
    )
    names = [b["name"] for b in resp.json()["branches"]]
    assert "develop" in names


# ---------------------------------------------------------------------------
# Commit response contracts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_commits_envelope(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """GET /repos/{id}/commits returns a 'commits' list envelope."""
    repo = await create_repo(db_session, owner="committer", slug="commit-contract")
    await create_commit(db_session, str(repo.repo_id), message="init: first commit")
    await create_commit(db_session, str(repo.repo_id), message="feat: second commit")

    resp = await client.get(
        f"/api/v1/musehub/repos/{repo.repo_id}/commits",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "commits" in body
    assert isinstance(body["commits"], list)
    assert len(body["commits"]) == 2


@pytest.mark.anyio
async def test_commit_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """Each commit object has message, author, branch, commitId, timestamp, parentIds."""
    repo = await create_repo(db_session, owner="committer2", slug="commit-fields")
    await create_commit(
        db_session, str(repo.repo_id),
        message="feat: piano track",
        author="mozart",
        branch="main",
    )

    resp = await client.get(
        f"/api/v1/musehub/repos/{repo.repo_id}/commits",
        headers=auth_headers,
    )
    commits = resp.json()["commits"]
    assert len(commits) == 1
    c = commits[0]

    assert c["message"] == "feat: piano track"
    assert c["author"] == "mozart"
    assert c["branch"] == "main"
    assert "commitId" in c
    assert "timestamp" in c
    assert isinstance(c["parentIds"], list)


# ---------------------------------------------------------------------------
# Issue response contracts
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_issue_response_shape(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """POST /repos/{id}/issues returns title, body, status, number, createdAt."""
    create_repo_resp = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "issue-contract-repo", "owner": "issuer"},
        headers=auth_headers,
    )
    repo_id = create_repo_resp.json()["repoId"]

    resp = await client.post(
        f"/api/v1/musehub/repos/{repo_id}/issues",
        json={"title": "Bug: tempo drift", "body": "The tempo drifts by 3 BPM"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()

    assert body["title"] == "Bug: tempo drift"
    assert body["body"] == "The tempo drifts by 3 BPM"
    assert body["state"] == "open"
    assert "number" in body
    assert isinstance(body["number"], int)
    assert "createdAt" in body


@pytest.mark.anyio
async def test_list_issues_returns_open_issues(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """GET /repos/{id}/issues returns issues envelope with status=open."""
    create_repo_resp = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "issue-list-contract", "owner": "issuer2"},
        headers=auth_headers,
    )
    repo_id = create_repo_resp.json()["repoId"]

    for i in range(3):
        await client.post(
            f"/api/v1/musehub/repos/{repo_id}/issues",
            json={"title": f"Issue {i}"},
            headers=auth_headers,
        )

    resp = await client.get(
        f"/api/v1/musehub/repos/{repo_id}/issues",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()

    assert "issues" in body
    assert len(body["issues"]) == 3
    for issue in body["issues"]:
        assert issue["state"] == "open"
        assert "title" in issue
        assert "number" in issue


@pytest.mark.anyio
async def test_close_issue_changes_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """POST /repos/{id}/issues/{n}/close sets status to 'closed'."""
    create_repo_resp = await client.post(
        "/api/v1/musehub/repos",
        json={"name": "close-issue-contract", "owner": "closer"},
        headers=auth_headers,
    )
    repo_id = create_repo_resp.json()["repoId"]

    issue_resp = await client.post(
        f"/api/v1/musehub/repos/{repo_id}/issues",
        json={"title": "Close me"},
        headers=auth_headers,
    )
    number = issue_resp.json()["number"]

    close_resp = await client.post(
        f"/api/v1/musehub/repos/{repo_id}/issues/{number}/close",
        headers=auth_headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["state"] == "closed"


# ---------------------------------------------------------------------------
# Explore / discover
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_explore_returns_public_repos(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    """GET /repos/explore returns public repos and excludes private ones."""
    await client.post(
        "/api/v1/musehub/repos",
        json={"name": "explore-public", "owner": "explorer", "visibility": "public"},
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/musehub/repos",
        json={"name": "explore-private", "owner": "explorer", "visibility": "private"},
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/musehub/discover/repos")
    assert resp.status_code == 200
    body = resp.json()
    repos = body if isinstance(body, list) else body.get("repos", body.get("items", []))

    slugs = [r.get("slug", "") for r in repos]
    assert "explore-public" in slugs
    assert "explore-private" not in slugs

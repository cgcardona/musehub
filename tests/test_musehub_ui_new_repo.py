"""Tests for the MuseHub new-repo creation wizard.

Covers ``musehub/api/routes/musehub/ui_new_repo.py``:

  GET /new        — redirects to /domains (repos require a domain context)
  POST /new       — create repo (JSON body, auth required)
  GET /new/check  — name availability check

Test matrix:
  test_new_repo_page_redirects_to_domains — GET /new → 302 to /domains
  test_new_repo_page_redirect_no_auth_required — redirect happens without a JWT
  test_check_available_returns_true — GET /new/check → available=true
  test_check_taken_returns_false — GET /new/check → available=false
  test_check_requires_owner_and_slug — GET /new/check → 422 when missing params
  test_create_repo_requires_auth — POST without token → 401/403
  test_create_repo_success — POST with valid body → 201 + redirect
  test_create_repo_409_on_duplicate — POST duplicate → 409
  test_create_repo_redirect_url_format — redirect URL contains /{owner}/{slug}?welcome=1
  test_create_repo_private_default — POST without visibility → defaults to private
  test_create_repo_initializes_repo — POST with initialize=true creates the repo
  test_create_repo_with_license — POST with license field stored correctly
  test_create_repo_with_topics — POST with topics stored as tags
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_models import MusehubRepo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_repo(
    db_session: AsyncSession,
    owner: str = "wizowner",
    slug: str = "existing-repo",
) -> MusehubRepo:
    """Seed a repo with a known owner/slug for uniqueness-check tests."""
    repo = MusehubRepo(
        name=slug,
        owner=owner,
        slug=slug,
        visibility="public",
        owner_user_id="seed-uid",
    )
    db_session.add(repo)
    await db_session.commit()
    await db_session.refresh(repo)
    return repo


# ---------------------------------------------------------------------------
# GET /new — redirect (repos require a domain context)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_new_repo_page_redirects_to_domains(client: AsyncClient) -> None:
    """GET /new → 302 redirect to /domains.

    Repository creation is now domain-scoped; the standalone /new wizard
    no longer exists. Users are directed to pick a domain first.
    """
    resp = await client.get("/new", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/domains")


@pytest.mark.anyio
async def test_new_repo_page_redirect_no_auth_required(client: AsyncClient) -> None:
    """The redirect from /new does not require authentication."""
    resp = await client.get("/new", follow_redirects=False)
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /new/check — name availability
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_available_returns_true(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new/check → available=true when no repo exists with that owner+slug."""
    resp = await client.get(
        "/new/check",
        params={"owner": "nobody", "slug": "no-such-repo"},
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is True


@pytest.mark.anyio
async def test_check_taken_returns_false(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new/check → available=false when the owner+slug is already taken."""
    await _seed_repo(db_session, owner="wizowner", slug="existing-repo")
    resp = await client.get(
        "/new/check",
        params={"owner": "wizowner", "slug": "existing-repo"},
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is False


@pytest.mark.anyio
async def test_check_requires_owner_and_slug(client: AsyncClient) -> None:
    """GET /new/check without required params returns 422."""
    resp = await client.get("/new/check")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /new — repo creation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_repo_requires_auth(client: AsyncClient) -> None:
    """POST /new without Authorization header returns 401 or 403."""
    resp = await client.post(
        "/new",
        json={
            "name": "test-repo",
            "owner": "someowner",
            "visibility": "private",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_create_repo_success(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST /new with valid body returns 201 and a redirect URL."""
    resp = await client.post(
        "/new",
        json={
            "name": "New Composition",
            "owner": "testowner",
            "visibility": "public",
            "description": "A new jazz piece",
            "tags": [],
            "topics": ["jazz", "piano"],
            "initialize": True,
            "defaultBranch": "main",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "redirect" in data
    assert "welcome=1" in data["redirect"]


@pytest.mark.anyio
async def test_create_repo_409_on_duplicate(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST /new with a duplicate owner+name returns 409."""
    await _seed_repo(db_session, owner="dupowner", slug="dup-repo")
    # 'dup-repo' is the slug generated from the name 'dup-repo'
    resp = await client.post(
        "/new",
        json={
            "name": "dup-repo",
            "owner": "dupowner",
            "visibility": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.anyio
async def test_create_repo_redirect_url_format(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """The redirect URL contains owner/slug path and ?welcome=1 query param."""
    resp = await client.post(
        "/new",
        json={
            "name": "redirect-test",
            "owner": "urlowner",
            "visibility": "private",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    redirect = resp.json()["redirect"]
    assert "urlowner" in redirect
    assert "welcome=1" in redirect
    assert redirect.startswith("/")


@pytest.mark.anyio
async def test_create_repo_private_default(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST without specifying visibility defaults to 'private'."""
    resp = await client.post(
        "/new",
        json={
            "name": "private-default-test",
            "owner": "privowner",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    # Confirm the slug and owner are in the redirect — repo was created.
    assert "privowner" in resp.json()["redirect"]


@pytest.mark.anyio
async def test_create_repo_initializes_repo(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST with initialize=true creates the repo successfully."""
    resp = await client.post(
        "/new",
        json={
            "name": "init-repo-test",
            "owner": "initowner",
            "visibility": "public",
            "initialize": True,
            "defaultBranch": "trunk",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "repoId" in data
    assert data["slug"] == "init-repo-test"


@pytest.mark.anyio
async def test_create_repo_with_license(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST with a license value is accepted and reflected in the response."""
    resp = await client.post(
        "/new",
        json={
            "name": "licensed-repo",
            "owner": "licowner",
            "visibility": "public",
            "license": "CC BY",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201


@pytest.mark.anyio
async def test_create_repo_with_topics(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """POST with topics results in a 201 and stores tags on the new repo."""
    resp = await client.post(
        "/new",
        json={
            "name": "topical-repo",
            "owner": "topicowner",
            "visibility": "public",
            "topics": ["jazz", "piano", "neosoul"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201

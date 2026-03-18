"""Auth guard tests for MuseHub routes.

Auth model (updated in Phase 0–4 UX overhaul):
- GET endpoints use ``optional_token`` — public repos are accessible
  unauthenticated; private repos return 401.
- POST / DELETE / write endpoints always use ``require_valid_token``.
- Non-existent repos return 404 regardless of auth status (no auth
  pre-filter that exposes 401 before a DB lookup for GET routes).

Covers:
- Write endpoints (POST/DELETE) always return 401 without a token.
- GET endpoints return 404 (not 401) for non-existent repos without a token,
  because the auth check is deferred to the visibility guard.
- GET endpoints return 401 for real private repos without a token.
- Valid tokens are accepted on write endpoints.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Write endpoints — always require auth (401 without token)
# Parametrized: eliminates five near-identical test functions.
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.parametrize("method,url,body", [
    # POST endpoints that require auth regardless of whether the repo exists
    ("POST", "/api/v1/repos",                            {"name": "beats", "owner": "testuser"}),
    ("POST", "/api/v1/repos/any-repo-id/issues",         {"title": "Bug report"}),
    ("POST", "/api/v1/repos/any-repo-id/issues/1/close", {}),
])
async def test_write_endpoints_require_auth(
    client: AsyncClient,
    method: str,
    url: str,
    body: dict,
) -> None:
    """Write endpoints return 401 when no Bearer token is supplied."""
    fn = getattr(client, method.lower())
    response = await fn(url, json=body)
    assert response.status_code == 401, (
        f"{method} {url} expected 401, got {response.status_code}: {response.text[:200]}"
    )


@pytest.mark.anyio
async def test_delete_webhook_requires_auth(client: AsyncClient, db_session: AsyncSession) -> None:
    """DELETE /webhooks/{id} returns 401 without a token."""
    response = await client.delete("/api/v1/repos/any-repo-id/webhooks/fake-hook-id")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET endpoints — non-existent repos return 404 (not 401) without token
#
# Rationale: optional_token + visibility guard — unauthenticated requests
# reach the DB; a non-existent repo returns 404 before the auth check fires.
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.parametrize("url", [
    "/api/v1/repos/non-existent-repo-id",
    "/api/v1/repos/non-existent-repo-id/branches",
    "/api/v1/repos/non-existent-repo-id/commits",
    "/api/v1/repos/non-existent-repo-id/issues",
    "/api/v1/repos/non-existent-repo-id/issues/1",
    "/api/v1/repos/non-existent-repo-id/pulls",
    "/api/v1/repos/non-existent-repo-id/releases",
])
async def test_get_nonexistent_repo_returns_404_without_auth(
    client: AsyncClient,
    url: str,
) -> None:
    """GET on a non-existent resource returns 404 without auth (not 401).

    The DB lookup happens before the visibility guard fires, so a missing
    repo surfaces as 404 regardless of authentication status.
    """
    response = await client.get(url)
    assert response.status_code == 404, (
        f"GET {url} expected 404, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Private repo visibility — GET returns 401 for private repos without token
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_private_repo_returns_401_without_auth(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /repos/{id} returns 401 for a private repo without a token."""
    create_resp = await client.post(
        "/api/v1/repos",
        json={"name": "private-auth-test", "owner": "authtest", "visibility": "private"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["repoId"]

    unauth_resp = await client.get(f"/api/v1/repos/{repo_id}")
    assert unauth_resp.status_code == 401, (
        f"Expected 401 for private repo, got {unauth_resp.status_code}"
    )


@pytest.mark.anyio
async def test_public_repo_accessible_without_auth(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """GET /repos/{id} returns 200 for a public repo without a token."""
    create_resp = await client.post(
        "/api/v1/repos",
        json={"name": "public-auth-test", "owner": "authtest", "visibility": "public"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    repo_id = create_resp.json()["repoId"]

    unauth_resp = await client.get(f"/api/v1/repos/{repo_id}")
    assert unauth_resp.status_code == 200, (
        f"Expected 200 for public repo, got {unauth_resp.status_code}: {unauth_resp.text}"
    )
    # Body should contain the repo data
    body = unauth_resp.json()
    assert body["repoId"] == repo_id
    assert body["visibility"] == "public"


# ---------------------------------------------------------------------------
# Authenticated requests are accepted
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_hub_routes_accept_valid_token(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """POST /musehub/repos succeeds (201) with a valid Bearer token."""
    response = await client.post(
        "/api/v1/repos",
        json={"name": "auth-sanity-repo", "owner": "testuser"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "auth-sanity-repo"
    assert body["owner"] == "testuser"
    assert "repoId" in body

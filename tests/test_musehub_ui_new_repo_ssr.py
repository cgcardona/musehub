"""SSR tests for MuseHub repo creation endpoints (issue #562).

GET /new is now a redirect to /domains (domain-scoped creation flow).
The wizard form previously at /new no longer exists at that path.

Covers:
- test_new_repo_page_redirect_is_html_compatible — GET /new → 302 (no SSR form)
- test_new_repo_name_check_htmx_returns_available_html — HTMX → HTML span "Available"
- test_new_repo_name_check_htmx_returns_taken_html — HTMX → HTML span "taken"
- test_new_repo_name_check_json_path_unchanged — no HX-Request → JSON response
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_models import MusehubRepo


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------


async def _seed_repo(
    db: AsyncSession,
    owner: str = "existingowner",
    slug: str = "taken-repo",
) -> None:
    """Seed a public repo so the slug appears as taken in check requests."""
    repo = MusehubRepo(
        name=slug,
        owner=owner,
        slug=slug,
        visibility="public",
        owner_user_id="seed-uid",
    )
    db.add(repo)
    await db.commit()


# ---------------------------------------------------------------------------
# Tests — /new redirect (form moved to /domains/@author/slug/new)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_new_repo_page_redirect_is_html_compatible(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new returns a 302 redirect — no SSR wizard form at this path.

    Repository creation is now domain-scoped; the wizard moved to
    /domains/@{author}/{slug}/new. This test confirms the old path
    cleanly redirects without requiring authentication.
    """
    response = await client.get("/new", follow_redirects=False)
    assert response.status_code == 302
    assert "/domains" in response.headers["location"]


# ---------------------------------------------------------------------------
# Tests — /new/check availability endpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_new_repo_name_check_htmx_returns_available_html(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new/check with HX-Request header returns an HTML availability span.

    The span is swapped into #name-check by HTMX — no JS needed.
    """
    response = await client.get(
        "/new/check",
        params={"owner": "newowner", "slug": "unique-name-xyz-123"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<span" in response.text
    assert "Available" in response.text


@pytest.mark.anyio
async def test_new_repo_name_check_htmx_returns_taken_html(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new/check for an existing slug returns a "taken" HTML span."""
    await _seed_repo(db_session, owner="existingowner", slug="taken-repo")
    response = await client.get(
        "/new/check",
        params={"owner": "existingowner", "slug": "taken-repo"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "<span" in body
    assert "taken" in body.lower() or "✗" in body


@pytest.mark.anyio
async def test_new_repo_name_check_json_path_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """GET /new/check without HX-Request header returns JSON — backward-compat path."""
    response = await client.get(
        "/new/check",
        params={"owner": "anyowner", "slug": "any-slug-999"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert "available" in data
    assert isinstance(data["available"], bool)

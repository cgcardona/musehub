"""Unit tests for musehub/services/musehub_profile.py.

Tests the service-layer profile functions directly (no HTTP), covering:
- Profile CRUD (create, get_by_username, get_by_user_id, update)
- Contribution graph shape and zero-commit baseline
- get_public_repos filters private repos
- get_session_credits baseline (no sessions → 0)
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.models.musehub import ProfileUpdateRequest
from musehub.services import musehub_profile
from tests.factories import create_profile, create_repo


# ---------------------------------------------------------------------------
# create_profile / get_profile_by_username
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_profile_and_get_by_username(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="artistone", display_name="Artist One")
    found = await musehub_profile.get_profile_by_username(db_session, "artistone")
    assert found is not None
    assert found.username == "artistone"
    assert found.display_name == "Artist One"


@pytest.mark.anyio
async def test_get_profile_by_username_missing_returns_none(db_session: AsyncSession) -> None:
    result = await musehub_profile.get_profile_by_username(db_session, "ghost-user")
    assert result is None


@pytest.mark.anyio
async def test_get_profile_by_user_id(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="byid-user")
    found = await musehub_profile.get_profile_by_user_id(db_session, profile.user_id)
    assert found is not None
    assert found.username == "byid-user"


@pytest.mark.anyio
async def test_get_profile_by_user_id_missing_returns_none(db_session: AsyncSession) -> None:
    result = await musehub_profile.get_profile_by_user_id(db_session, "00000000-dead-beef-0000-000000000000")
    assert result is None


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_profile_bio(db_session: AsyncSession) -> None:
    orm_profile = await create_profile(db_session, username="bio-user", bio="old bio")
    await musehub_profile.update_profile(
        db_session,
        orm_profile,
        ProfileUpdateRequest(bio="new bio"),
    )
    updated = await musehub_profile.get_profile_by_username(db_session, "bio-user")
    assert updated is not None
    assert updated.bio == "new bio"


@pytest.mark.anyio
async def test_update_profile_display_name(db_session: AsyncSession) -> None:
    orm_profile = await create_profile(db_session, username="name-user", display_name="Old Name")
    await musehub_profile.update_profile(
        db_session,
        orm_profile,
        ProfileUpdateRequest(display_name="New Name"),
    )
    updated = await musehub_profile.get_profile_by_username(db_session, "name-user")
    assert updated is not None
    assert updated.display_name == "New Name"


# ---------------------------------------------------------------------------
# get_public_repos
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_public_repos_returns_public_only(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="pub-repo-user")
    await create_repo(
        db_session,
        owner="pub-repo-user",
        owner_user_id=profile.user_id,
        slug="public-one",
        visibility="public",
    )
    await create_repo(
        db_session,
        owner="pub-repo-user",
        owner_user_id=profile.user_id,
        slug="private-one",
        visibility="private",
    )

    repos = await musehub_profile.get_public_repos(db_session, profile.user_id)
    slugs = [r.slug for r in repos]
    assert "public-one" in slugs
    assert "private-one" not in slugs


@pytest.mark.anyio
async def test_get_public_repos_empty_for_no_repos(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="no-repos-user")
    repos = await musehub_profile.get_public_repos(db_session, profile.user_id)
    assert repos == []


# ---------------------------------------------------------------------------
# get_contribution_graph
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_contribution_graph_returns_52_weeks(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="graph-user")
    graph = await musehub_profile.get_contribution_graph(db_session, profile.user_id)
    # 52 weeks × 7 days = 364, but the implementation may include today making it 365
    assert len(graph) in (364, 365)


@pytest.mark.anyio
async def test_contribution_graph_all_zero_for_no_commits(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="zero-commits-user")
    graph = await musehub_profile.get_contribution_graph(db_session, profile.user_id)
    assert all(day.count == 0 for day in graph)


# ---------------------------------------------------------------------------
# get_session_credits
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_session_credits_zero_baseline(db_session: AsyncSession) -> None:
    profile = await create_profile(db_session, username="credit-user")
    credits = await musehub_profile.get_session_credits(db_session, profile.user_id)
    assert credits == 0


# ---------------------------------------------------------------------------
# get_full_profile
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_full_profile_returns_structured_response(db_session: AsyncSession) -> None:
    profile = await create_profile(
        db_session,
        username="full-profile-user",
        bio="Full profile bio",
        display_name="Full User",
    )
    result = await musehub_profile.get_full_profile(db_session, "full-profile-user")

    assert result is not None
    assert result.username == "full-profile-user"
    assert result.bio == "Full profile bio"
    assert result.display_name == "Full User"
    assert isinstance(result.repos, list)
    assert isinstance(result.contribution_graph, list)
    assert result.session_credits == 0


@pytest.mark.anyio
async def test_get_full_profile_missing_returns_none(db_session: AsyncSession) -> None:
    result = await musehub_profile.get_full_profile(db_session, "nobody-at-all")
    assert result is None

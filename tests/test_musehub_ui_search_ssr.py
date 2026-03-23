"""SSR tests for MuseHub global search page.

Verifies that global_search_page() renders results server-side in Jinja2
templates without requiring JavaScript execution.
Tests assert on HTML content directly returned by the server.

Covers GET /search (global search):
- test_global_search_renders_results_server_side
- test_global_search_no_results_shows_empty_state
- test_global_search_short_query_shows_prompt
- test_global_search_htmx_fragment_path
- test_global_search_empty_query_shows_prompt
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_models import MusehubBranch, MusehubCommit, MusehubRepo
from musehub.muse_cli import models as _cli_models  # noqa: F401 — register tables
from musehub.muse_cli.db import insert_commit, upsert_snapshot
from musehub.muse_cli.models import MuseCliCommit
from musehub.muse_cli.snapshot import compute_commit_id, compute_snapshot_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_repo(
    db: AsyncSession,
    owner: str = "search_ssr_artist",
    slug: str = "search-ssr-album",
    visibility: str = "public",
) -> str:
    """Seed a public repo and return its repo_id string."""
    repo = MusehubRepo(
        name=slug,
        owner=owner,
        slug=slug,
        visibility=visibility,
        owner_user_id=f"uid-{owner}",
    )
    db.add(repo)
    await db.commit()
    await db.refresh(repo)
    return str(repo.repo_id)


async def _make_musehub_commit(
    db: AsyncSession,
    repo_id: str,
    *,
    commit_id: str,
    message: str,
    branch: str = "main",
    author: str = "musician",
) -> None:
    """Seed a MusehubCommit (used by global_search via musehub_commits table)."""
    commit = MusehubCommit(
        commit_id=commit_id,
        repo_id=repo_id,
        branch=branch,
        parent_ids=[],
        message=message,
        author=author,
        timestamp=datetime.now(tz=timezone.utc),
    )
    db_branch = MusehubBranch(
        repo_id=repo_id,
        name=branch,
        head_commit_id=commit_id,
    )
    db.add(commit)
    db.add(db_branch)
    await db.commit()


async def _make_cli_commit(
    db: AsyncSession,
    repo_id: str,
    *,
    message: str,
    branch: str = "main",
    author: str = "musician",
) -> str:
    """Seed a MuseCliCommit (used by in-repo search via muse_commits table).

    Returns the generated commit_id.
    """
    manifest: dict[str, str] = {"track.mid": "deadbeef"}
    snap_id = compute_snapshot_id(manifest)
    await upsert_snapshot(db, manifest=manifest, snapshot_id=snap_id)
    committed_at = datetime.now(tz=timezone.utc)
    commit_id = compute_commit_id(
        parent_ids=[],
        snapshot_id=snap_id,
        message=message,
        committed_at_iso=committed_at.isoformat(),
    )
    commit = MuseCliCommit(
        commit_id=commit_id,
        repo_id=repo_id,
        branch=branch,
        parent_commit_id=None,
        snapshot_id=snap_id,
        message=message,
        author=author,
        committed_at=committed_at,
    )
    await insert_commit(db, commit)
    await db.flush()
    return commit_id


# ---------------------------------------------------------------------------
# Global search — GET /search
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_global_search_renders_results_server_side(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Commit message appears in the HTML returned by the server (not injected by JS)."""
    repo_id = await _make_repo(db_session)
    await _make_musehub_commit(
        db_session,
        repo_id,
        commit_id="aabbccddeeff00112233445566778899aabbccd1",
        message="beatbox groove pattern in D minor",
    )
    response = await client.get("/search?q=beatbox")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "beatbox" in response.text


@pytest.mark.anyio
async def test_global_search_no_results_shows_empty_state(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A query with no matches renders the empty-state block."""
    await _make_repo(db_session, owner="search_noresult", slug="noresult-album")
    response = await client.get("/search?q=zzznomatch")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "No results" in response.text


@pytest.mark.anyio
async def test_global_search_short_query_shows_prompt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A single-character query renders the tips/idle state (no results run)."""
    response = await client.get("/search?q=a")
    assert response.status_code == 200
    assert "Global Search" in response.text


@pytest.mark.anyio
async def test_global_search_empty_query_shows_prompt(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """An empty query renders the search page without running any DB search."""
    response = await client.get("/search")
    assert response.status_code == 200
    assert "Global Search" in response.text


@pytest.mark.anyio
async def test_global_search_htmx_fragment_path(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """HX-Request: true causes the handler to return only the fragment - no <html> shell."""
    repo_id = await _make_repo(db_session, owner="htmx_search_artist", slug="htmx-search-album")
    await _make_musehub_commit(
        db_session,
        repo_id,
        commit_id="aabbccddeeff00112233445566778899aabbccd2",
        message="funky bassline in Eb",
    )
    response = await client.get(
        "/search?q=funky",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "<html" not in response.text
    assert "funky" in response.text



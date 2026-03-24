"""Wire protocol endpoint tests.

Covers the three Muse CLI transport endpoints (Git-style URLs):
    GET  /{owner}/{slug}/refs
    POST /{owner}/{slug}/push
    POST /{owner}/{slug}/fetch

And the content-addressed CDN endpoint:
    GET  /o/{object_id}

Remote URL format (same pattern as Git):
    muse remote add origin https://musehub.ai/cgcardona/muse
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import msgpack
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.tokens import create_access_token
from musehub.db import musehub_models as db
from tests.factories import create_repo as factory_create_repo


# ── helpers ────────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_commit(repo_id: str, commit_id: str | None = None, parent: str | None = None) -> dict:
    return {
        "commit_id": commit_id or str(uuid.uuid4()),
        "repo_id": repo_id,
        "branch": "main",
        "snapshot_id": f"snap_{uuid.uuid4().hex[:8]}",
        "message": "chore: add test commit",
        "committed_at": _utc_now().isoformat(),
        "parent_commit_id": parent,
        "author": "Test User <test@example.com>",
        "sem_ver_bump": "patch",
    }


def _make_object(content: bytes = b"hello world") -> dict:
    oid = uuid.uuid4().hex
    return {
        "object_id": oid,
        "content": content,
        "path": "README.md",
    }


def _make_snapshot(snap_id: str, object_id: str) -> dict:
    return {
        "snapshot_id": snap_id,
        "manifest": {"README.md": object_id},
        "created_at": _utc_now().isoformat(),
    }


@pytest.fixture(autouse=True)
def _tmp_objects_dir(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Override object storage to use a temp directory in tests."""
    import musehub.storage.backends as _backends
    import musehub.services.musehub_wire as _wire_svc
    import musehub.api.routes.wire as _wire_route

    obj_dir = str(tmp_path) + "/objects"  # type: ignore[operator]
    os.makedirs(obj_dir, exist_ok=True)
    test_backend = _backends.LocalBackend(objects_dir=obj_dir)
    monkeypatch.setattr(_wire_svc, "get_backend", lambda: test_backend)
    monkeypatch.setattr(_wire_route, "get_backend", lambda: test_backend)


@pytest.fixture
def auth_wire_token() -> str:
    return create_access_token(user_id="test-user-wire", expires_hours=1)


@pytest.fixture
def wire_headers(auth_wire_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {auth_wire_token}",
        "Content-Type": "application/x-msgpack",
        "Accept": "application/x-msgpack",
    }


def _mp(data: object) -> bytes:
    """Encode data as msgpack for test request bodies."""
    return msgpack.packb(data, use_bin_type=True)


# ── refs endpoint ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refs_returns_404_for_unknown_owner_slug(client: AsyncClient) -> None:
    resp = await client.get("/no-such-owner/no-such-slug/refs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_refs_returns_branch_heads(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="muse-test", domain_meta={"domain": "code"})
    branch = db.MusehubBranch(
        repo_id=repo.repo_id,
        name="main",
        head_commit_id="abc123",
    )
    db_session.add(branch)
    await db_session.commit()

    owner = repo.owner
    slug = repo.slug
    resp = await client.get(f"/{owner}/{slug}/refs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_id"] == repo.repo_id
    assert data["default_branch"] == "main"
    assert data["domain"] == "code"
    assert data["branch_heads"]["main"] == "abc123"


@pytest.mark.asyncio
async def test_refs_url_is_owner_slash_slug(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Confirm the remote URL pattern matches Git: /{owner}/{slug}/refs — no /wire/ prefix."""
    repo = await factory_create_repo(db_session, slug="git-style-test")
    owner, slug = repo.owner, repo.slug

    resp = await client.get(f"/{owner}/{slug}/refs")
    assert resp.status_code == 200
    # Should NOT need /wire/ in the path
    resp_wire = await client.get(f"/wire/repos/{repo.repo_id}/refs")
    assert resp_wire.status_code == 404


@pytest.mark.asyncio
async def test_refs_empty_repo_has_empty_branch_heads(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="empty-test")
    resp = await client.get(f"/{repo.owner}/{repo.slug}/refs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["branch_heads"] == {}


# ── push endpoint ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_requires_auth(client: AsyncClient, db_session: AsyncSession) -> None:
    repo = await factory_create_repo(db_session, slug="push-auth-test", owner_user_id="test-user-wire")
    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/push",
        content=_mp({"bundle": {"commits": [], "snapshots": [], "objects": []}, "branch": "main"}),
        headers={"Content-Type": "application/x-msgpack"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_push_404_for_unknown_repo(
    client: AsyncClient,
    wire_headers: dict,
) -> None:
    resp = await client.post(
        "/nobody/no-such-repo/push",
        content=_mp({"bundle": {"commits": [], "snapshots": [], "objects": []}, "branch": "main"}),
        headers=wire_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_push_rejected_for_non_owner(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    """Authenticated user who is NOT the repo owner must be rejected."""
    repo = await factory_create_repo(
        db_session,
        slug="push-nonowner-test",
        owner_user_id="someone-else",  # different from test-user-wire
    )
    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/push",
        content=_mp({"bundle": {"commits": [], "snapshots": [], "objects": []}, "branch": "main"}),
        headers=wire_headers,
    )
    assert resp.status_code == 409
    assert "not authorized" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_push_ingests_commit_and_branch(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-ingest-test", owner_user_id="test-user-wire")

    commit_id = uuid.uuid4().hex
    obj = _make_object()
    snap_id = f"snap_{uuid.uuid4().hex[:8]}"
    snap = _make_snapshot(snap_id, obj["object_id"])
    commit = _make_commit(repo.repo_id, commit_id=commit_id)
    commit["snapshot_id"] = snap_id

    payload = {
        "bundle": {
            "commits": [commit],
            "snapshots": [snap],
            "objects": [obj],
        },
        "branch": "main",
        "force": False,
    }
    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/push",
        content=_mp(payload),
        headers=wire_headers,
    )
    assert resp.status_code == 200, resp.text
    data = msgpack.unpackb(resp.content, raw=False)
    assert data["ok"] is True
    assert "main" in data["branch_heads"]
    assert data["remote_head"] == commit_id


@pytest.mark.asyncio
async def test_push_is_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    """Pushing the same commit twice must succeed both times."""
    repo = await factory_create_repo(db_session, slug="push-idempotent-test", owner_user_id="test-user-wire")
    commit = _make_commit(repo.repo_id)
    payload = {
        "bundle": {"commits": [commit], "snapshots": [], "objects": []},
        "branch": "main",
    }
    url = f"/{repo.owner}/{repo.slug}/push"
    resp1 = await client.post(url, content=_mp(payload), headers=wire_headers)
    assert resp1.status_code == 200
    resp2 = await client.post(url, content=_mp(payload), headers=wire_headers)
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_push_non_fast_forward_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-nff-test", owner_user_id="test-user-wire")
    existing_commit_id = uuid.uuid4().hex
    branch = db.MusehubBranch(
        repo_id=repo.repo_id,
        name="main",
        head_commit_id=existing_commit_id,
    )
    db_session.add(branch)
    await db_session.commit()

    # Push a commit without existing_commit_id as parent
    new_commit = _make_commit(repo.repo_id, parent=None)
    payload = {
        "bundle": {"commits": [new_commit], "snapshots": [], "objects": []},
        "branch": "main",
        "force": False,
    }
    resp = await client.post(f"/{repo.owner}/{repo.slug}/push", content=_mp(payload), headers=wire_headers)
    assert resp.status_code == 409  # 409 Conflict for non-fast-forward
    assert "non-fast-forward" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_push_force_overwrites_branch(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-force-test", owner_user_id="test-user-wire")
    old_head = uuid.uuid4().hex
    branch = db.MusehubBranch(
        repo_id=repo.repo_id,
        name="main",
        head_commit_id=old_head,
    )
    db_session.add(branch)
    await db_session.commit()

    new_commit = _make_commit(repo.repo_id, parent=None)
    payload = {
        "bundle": {"commits": [new_commit], "snapshots": [], "objects": []},
        "branch": "main",
        "force": True,
    }
    resp = await client.post(f"/{repo.owner}/{repo.slug}/push", content=_mp(payload), headers=wire_headers)
    assert resp.status_code == 200
    data = msgpack.unpackb(resp.content, raw=False)
    assert data["ok"] is True
    assert data["branch_heads"]["main"] != old_head


# ── fetch endpoint ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_404_for_unknown_repo(client: AsyncClient) -> None:
    resp = await client.post(
        "/nobody/no-such-repo/fetch",
        content=_mp({"want": [], "have": []}),
        headers={"Content-Type": "application/x-msgpack"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fetch_empty_want_returns_empty_bundle(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="fetch-empty-test")
    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/fetch",
        content=_mp({"want": [], "have": []}),
        headers={"Content-Type": "application/x-msgpack", "Accept": "application/x-msgpack"},
    )
    assert resp.status_code == 200
    data = msgpack.unpackb(resp.content, raw=False)
    assert data["commits"] == []
    assert data["snapshots"] == []
    assert data["objects"] == []


@pytest.mark.asyncio
async def test_fetch_returns_missing_commits(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="fetch-commits-test")
    commit_id = uuid.uuid4().hex
    commit_row = db.MusehubCommit(
        commit_id=commit_id,
        repo_id=repo.repo_id,
        branch="main",
        parent_ids=[],
        message="initial commit",
        author="Test",
        timestamp=_utc_now(),
        snapshot_id=None,
        commit_meta={},
    )
    branch_row = db.MusehubBranch(
        repo_id=repo.repo_id,
        name="main",
        head_commit_id=commit_id,
    )
    db_session.add(commit_row)
    db_session.add(branch_row)
    await db_session.commit()

    resp = await client.post(
        f"/{repo.owner}/{repo.slug}/fetch",
        content=_mp({"want": [commit_id], "have": []}),
        headers={"Content-Type": "application/x-msgpack", "Accept": "application/x-msgpack"},
    )
    assert resp.status_code == 200
    data = msgpack.unpackb(resp.content, raw=False)
    assert len(data["commits"]) == 1
    assert data["commits"][0]["commit_id"] == commit_id
    assert data["branch_heads"]["main"] == commit_id


# ── content-addressed CDN ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_object_cdn_returns_404_for_missing(client: AsyncClient) -> None:
    resp = await client.get("/o/nonexistent-sha-12345")
    assert resp.status_code == 404


# ── unit tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wire_models_parse_correctly() -> None:
    """WireBundle Pydantic parsing mirrors Muse CLI format."""
    from musehub.models.wire import WireBundle, WirePushRequest

    commit_dict = {
        "commit_id": "abc123",
        "message": "feat: add track",
        "committed_at": "2026-03-19T10:00:00+00:00",
        "author": "Gabriel <g@example.com>",
        "sem_ver_bump": "minor",
        "breaking_changes": [],
        "agent_id": "",
        "format_version": 5,
    }
    req = WirePushRequest(
        bundle=WireBundle(commits=[commit_dict], snapshots=[], objects=[]),  # type: ignore[list-item]
        branch="main",
        force=False,
    )
    assert req.bundle.commits[0].commit_id == "abc123"
    assert req.bundle.commits[0].sem_ver_bump == "minor"
    assert req.force is False


@pytest.mark.asyncio
async def test_topological_sort_orders_parents_first() -> None:
    from musehub.models.wire import WireCommit
    from musehub.services.musehub_wire import _topological_sort

    c1 = WireCommit(commit_id="parent", message="parent")
    c2 = WireCommit(commit_id="child", message="child", parent_commit_id="parent")
    sorted_ = _topological_sort([c2, c1])
    ids = [c.commit_id for c in sorted_]
    assert ids.index("parent") < ids.index("child")


@pytest.mark.asyncio
async def test_remote_url_format_matches_git_pattern(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """The remote URL is /{owner}/{slug} — no /wire/ prefix, no UUID.

    This mirrors Git:
        git remote add origin https://github.com/owner/repo
    versus UUID-based alternatives like:
        muse remote add origin https://musehub.ai/wire/repos/550e8400-.../
    """
    repo = await factory_create_repo(db_session, slug="url-format-test")

    # /{owner}/{slug}/refs must work
    resp = await client.get(f"/{repo.owner}/{repo.slug}/refs")
    assert resp.status_code == 200

    # The response confirms which repo was resolved — no UUID needed in the URL
    data = resp.json()
    assert data["repo_id"] == repo.repo_id

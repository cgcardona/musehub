"""Wire protocol endpoint tests.

Covers the three Muse CLI transport endpoints:
    GET  /wire/repos/{repo_id}/refs
    POST /wire/repos/{repo_id}/push
    POST /wire/repos/{repo_id}/fetch

And the content-addressed CDN endpoint:
    GET  /o/{object_id}
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

import os
import tempfile

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.tokens import create_access_token
from musehub.db import musehub_models as db
from tests.factories import create_repo as factory_create_repo, create_branch as factory_create_branch


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
        "content_b64": base64.b64encode(content).decode(),
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
        "Content-Type": "application/json",
    }


# ── refs endpoint ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refs_returns_404_for_unknown_repo(client: AsyncClient) -> None:
    resp = await client.get("/wire/repos/nonexistent-repo-id/refs")
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

    resp = await client.get(f"/wire/repos/{repo.repo_id}/refs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["repo_id"] == repo.repo_id
    assert data["default_branch"] == "main"
    assert data["domain"] == "code"
    assert data["branch_heads"]["main"] == "abc123"


@pytest.mark.asyncio
async def test_refs_empty_repo_has_empty_branch_heads(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="empty-test")
    resp = await client.get(f"/wire/repos/{repo.repo_id}/refs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["branch_heads"] == {}


# ── push endpoint ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_push_requires_auth(client: AsyncClient, db_session: AsyncSession) -> None:
    repo = await factory_create_repo(db_session, slug="push-auth-test")
    resp = await client.post(
        f"/wire/repos/{repo.repo_id}/push",
        json={"bundle": {"commits": [], "snapshots": [], "objects": []}, "branch": "main"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_push_404_for_unknown_repo(
    client: AsyncClient,
    wire_headers: dict,
) -> None:
    resp = await client.post(
        "/wire/repos/does-not-exist/push",
        json={"bundle": {"commits": [], "snapshots": [], "objects": []}, "branch": "main"},
        headers=wire_headers,
    )
    assert resp.status_code == 422  # wire service returns ok=False → 422


@pytest.mark.asyncio
async def test_push_ingests_commit_and_branch(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-ingest-test")

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
        f"/wire/repos/{repo.repo_id}/push",
        json=payload,
        headers=wire_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
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
    repo = await factory_create_repo(db_session, slug="push-idempotent-test")
    commit = _make_commit(repo.repo_id)
    payload = {
        "bundle": {"commits": [commit], "snapshots": [], "objects": []},
        "branch": "main",
    }

    resp1 = await client.post(f"/wire/repos/{repo.repo_id}/push", json=payload, headers=wire_headers)
    assert resp1.status_code == 200
    resp2 = await client.post(f"/wire/repos/{repo.repo_id}/push", json=payload, headers=wire_headers)
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_push_non_fast_forward_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-nff-test")
    existing_commit_id = uuid.uuid4().hex
    branch = db.MusehubBranch(
        repo_id=repo.repo_id,
        name="main",
        head_commit_id=existing_commit_id,
    )
    db_session.add(branch)
    await db_session.commit()

    # Push a commit that does NOT have existing_commit_id as parent
    new_commit = _make_commit(repo.repo_id, parent=None)
    payload = {
        "bundle": {"commits": [new_commit], "snapshots": [], "objects": []},
        "branch": "main",
        "force": False,
    }
    resp = await client.post(f"/wire/repos/{repo.repo_id}/push", json=payload, headers=wire_headers)
    assert resp.status_code == 422
    assert "non-fast-forward" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_push_force_overwrites_branch(
    client: AsyncClient,
    db_session: AsyncSession,
    wire_headers: dict,
) -> None:
    repo = await factory_create_repo(db_session, slug="push-force-test")
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
    resp = await client.post(f"/wire/repos/{repo.repo_id}/push", json=payload, headers=wire_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["branch_heads"]["main"] != old_head


# ── fetch endpoint ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_404_for_unknown_repo(client: AsyncClient) -> None:
    resp = await client.post(
        "/wire/repos/no-such-repo/fetch",
        json={"want": [], "have": []},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fetch_empty_want_returns_empty_bundle(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    repo = await factory_create_repo(db_session, slug="fetch-empty-test")

    resp = await client.post(
        f"/wire/repos/{repo.repo_id}/fetch",
        json={"want": [], "have": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["commits"] == []
    assert data["snapshots"] == []
    assert data["objects"] == []


@pytest.mark.asyncio
async def test_fetch_returns_missing_commits(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After a push, fetch should return the pushed commits when wanted."""
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
        f"/wire/repos/{repo.repo_id}/fetch",
        json={"want": [commit_id], "have": []},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["commits"]) == 1
    assert data["commits"][0]["commit_id"] == commit_id
    assert data["branch_heads"]["main"] == commit_id


# ── content-addressed CDN ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_object_cdn_returns_404_for_missing(client: AsyncClient) -> None:
    resp = await client.get("/o/nonexistent-sha-12345")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_wire_models_parse_correctly() -> None:
    """Unit test: WireBundle Pydantic parsing from dict mirrors Muse CLI format."""
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
    # Pass in reverse order
    sorted_ = _topological_sort([c2, c1])
    ids = [c.commit_id for c in sorted_]
    assert ids.index("parent") < ids.index("child")

"""Test factories for MuseHub ORM models.

Provides two layers:
  1. ``*Factory`` classes (factory_boy ``Factory`` subclasses) that generate
     realistic attribute dictionaries without touching the database.
  2. Async ``create_*`` helpers that instantiate the ORM model from the
     factory data, persist it, and return the refreshed ORM object.

Usage in tests::

    from tests.factories import create_repo, create_profile, RepoFactory

    async def test_something(db_session):
        repo = await create_repo(db_session, owner="alice", visibility="public")
        assert repo.owner == "alice"

    # Data-only (no DB) — useful for unit-testing pure functions:
    data = RepoFactory(name="My Jazz EP", owner="charlie")
    assert data["slug"] == "my-jazz-ep"
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone

import factory
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _slugify(name: str) -> str:
    """Convert a human-readable name to a URL-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "repo"


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Attribute factories (no DB access)
# ---------------------------------------------------------------------------

class RepoFactory(factory.Factory):
    """Generate attribute dicts for MusehubRepo."""

    class Meta:
        model = dict

    name: str = factory.Sequence(lambda n: f"Test Repo {n}")
    owner: str = "testuser"
    slug: str = factory.LazyAttribute(lambda o: _slugify(o.name))
    visibility: str = "public"
    owner_user_id: str = factory.LazyFunction(_uid)
    description: str = factory.LazyAttribute(lambda o: f"Description for {o.name}")
    tags: list = factory.LazyFunction(list)
    key_signature: str | None = None
    tempo_bpm: int | None = None


class BranchFactory(factory.Factory):
    class Meta:
        model = dict

    name: str = "main"
    head_commit_id: str | None = None


class CommitFactory(factory.Factory):
    class Meta:
        model = dict

    commit_id: str = factory.LazyFunction(lambda: _sha(str(uuid.uuid4())))
    message: str = factory.Sequence(lambda n: f"feat: commit number {n}")
    author: str = "testuser"
    branch: str = "main"
    parent_ids: list = factory.LazyFunction(list)
    snapshot_id: str | None = None
    timestamp: datetime = factory.LazyFunction(_now)


class ProfileFactory(factory.Factory):
    class Meta:
        model = dict

    user_id: str = factory.LazyFunction(_uid)
    username: str = factory.Sequence(lambda n: f"user{n}")
    display_name: str = factory.LazyAttribute(lambda o: o.username.title())
    bio: str = "A musician who uses Muse VCS."
    avatar_url: str | None = None
    location: str | None = None
    website_url: str | None = None
    twitter_handle: str | None = None
    is_verified: bool = False
    cc_license: str | None = None
    pinned_repo_ids: list = factory.LazyFunction(list)


class IssueFactory(factory.Factory):
    class Meta:
        model = dict

    title: str = factory.Sequence(lambda n: f"Issue #{n}")
    body: str = "Issue body text."
    author: str = "testuser"
    status: str = "open"


class SessionFactory(factory.Factory):
    class Meta:
        model = dict

    session_id: str = factory.LazyFunction(_uid)
    participants: list = factory.LazyFunction(lambda: ["testuser"])
    commits: list = factory.LazyFunction(list)
    notes: str | None = None
    location: str | None = None
    intent: str | None = None


# ---------------------------------------------------------------------------
# Async persistence helpers
# ---------------------------------------------------------------------------

async def create_repo(
    session: AsyncSession,
    **kwargs: object,
) -> db.MusehubRepo:
    """Insert and return a MusehubRepo row using RepoFactory defaults."""
    data = RepoFactory(**kwargs)
    repo = db.MusehubRepo(
        name=data["name"],
        owner=data["owner"],
        slug=data["slug"],
        visibility=data["visibility"],
        owner_user_id=data["owner_user_id"],
        description=data["description"],
        tags=data["tags"],
        key_signature=data.get("key_signature"),
        tempo_bpm=data.get("tempo_bpm"),
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    return repo


async def create_branch(
    session: AsyncSession,
    repo_id: str,
    **kwargs: object,
) -> db.MusehubBranch:
    """Insert and return a MusehubBranch row."""
    data = BranchFactory(**kwargs)
    branch = db.MusehubBranch(
        repo_id=repo_id,
        name=data["name"],
        head_commit_id=data.get("head_commit_id"),
    )
    session.add(branch)
    await session.commit()
    await session.refresh(branch)
    return branch


async def create_commit(
    session: AsyncSession,
    repo_id: str,
    **kwargs: object,
) -> db.MusehubCommit:
    """Insert and return a MusehubCommit row."""
    data = CommitFactory(**kwargs)
    commit = db.MusehubCommit(
        commit_id=data["commit_id"],
        repo_id=repo_id,
        message=data["message"],
        author=data["author"],
        branch=data["branch"],
        parent_ids=data["parent_ids"],
        snapshot_id=data.get("snapshot_id"),
        timestamp=data.get("timestamp") or _now(),
    )
    session.add(commit)
    await session.commit()
    await session.refresh(commit)
    return commit


async def create_profile(
    session: AsyncSession,
    **kwargs: object,
) -> db.MusehubProfile:
    """Insert and return a MusehubProfile row."""
    data = ProfileFactory(**kwargs)
    profile = db.MusehubProfile(
        user_id=data["user_id"],
        username=data["username"],
        display_name=data["display_name"],
        bio=data["bio"],
        avatar_url=data.get("avatar_url"),
        location=data.get("location"),
        website_url=data.get("website_url"),
        twitter_handle=data.get("twitter_handle"),
        is_verified=data["is_verified"],
        cc_license=data.get("cc_license"),
        pinned_repo_ids=data["pinned_repo_ids"],
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def create_repo_with_branch(
    session: AsyncSession,
    **kwargs: object,
) -> tuple[db.MusehubRepo, db.MusehubBranch]:
    """Convenience: create a repo + default 'main' branch atomically."""
    repo = await create_repo(session, **kwargs)
    branch = await create_branch(session, repo_id=str(repo.repo_id), name="main")
    return repo, branch

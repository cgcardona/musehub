"""
Production seed for musehub.ai

Creates gabriel's account + the muse repo only.
Idempotent: safe to re-run (skips existing records).

Run inside the container:
  docker compose exec musehub python3 /app/scripts/seed_production.py
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from musehub.config import settings
from musehub.db.models import User
from musehub.db.musehub_models import (
    MusehubBranch,
    MusehubCommit,
    MusehubIssue,
    MusehubProfile,
    MusehubRelease,
    MusehubRepo,
)
from musehub.auth.tokens import generate_access_code

UTC = timezone.utc


def _now(days: int = 0, hours: int = 0) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days, hours=hours)


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _uid(seed: str) -> str:
    return str(uuid.UUID(bytes=hashlib.md5(seed.encode()).digest()))


GABRIEL_ID = _uid("prod-gabriel-cgcardona")

MUSE_REPO_ID = _uid("prod-repo-muse")

MUSE_REPO = dict(
    repo_id=MUSE_REPO_ID,
    slug="muse",
    name="muse",
    description=(
        "A domain-agnostic version control system for multidimensional state. "
        "Not just code — any state space where a 'change' is a delta across "
        "multiple axes simultaneously: MIDI (21 dims), code (AST), genomics, "
        "3D design, climate simulation."
    ),
    tags=["vcs", "cli", "domain-agnostic", "open-source"],
    domain_meta={"primary_language": "Python", "languages": {"Python": 74, "HTML": 26}},
)

MUSE_COMMITS: list[tuple[str, int]] = [
    ("init: scaffold domain-agnostic object model", 180),
    ("feat: content-addressed object store (SHA-256)", 170),
    ("feat: snapshot and commit layer", 160),
    ("feat: branch and ref pointers", 150),
    ("feat: muse clone over HTTP", 140),
    ("feat: muse push — upload objects + update refs", 130),
    ("feat: muse pull — fetch and merge remote refs", 120),
    ("feat: MIDI domain plugin (21-dimensional state)", 110),
    ("feat: code domain plugin (AST-based diff)", 100),
    ("fix: handle empty repo on first push", 90),
    ("perf: pack objects for transfer efficiency", 80),
    ("feat: muse log — pretty commit history", 70),
    ("feat: muse diff — dimensional delta view", 60),
    ("feat: muse tag — annotated and lightweight", 50),
    ("fix: ref resolution with detached HEAD", 40),
    ("feat: muse stash save/pop", 30),
    ("docs: getting started guide", 20),
    ("chore: release v0.3.0", 10),
]

MUSE_ISSUES: list[tuple[str, str, list[str]]] = [
    ("Support for genomics domain plugin", "open", ["enhancement"]),
    ("muse diff: show only changed dimensions", "open", ["enhancement"]),
    ("muse pull: conflict resolution for parallel edits", "open", ["bug"]),
    ("Add progress bar for large object uploads", "closed", ["enhancement"]),
    ("muse log: add --graph flag for branch visualization", "open", ["enhancement"]),
]

# Slugs of all repos that were seeded in the past but are no longer wanted.
REMOVED_SLUGS = [
    "musehub",
    "agentception",
    "maestro",
    "stori",
    "well-tempered-clavier",
    "moonlight-sonata",
    "neobaroque-sketches",
    "modal-sessions",
    "chopin-nocturnes",
]


async def seed() -> None:
    db_url = settings.database_url or "sqlite+aiosqlite:///./muse.db"
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:

        # ── 1. Remove any previously-seeded repos that are no longer wanted ──
        from sqlalchemy import select, delete
        for slug in REMOVED_SLUGS:
            result = await session.execute(
                select(MusehubRepo).where(
                    MusehubRepo.owner == "gabriel",
                    MusehubRepo.slug == slug,
                )
            )
            repo = result.scalar_one_or_none()
            if repo:
                rid = repo.repo_id
                await session.execute(delete(MusehubCommit).where(MusehubCommit.repo_id == rid))
                await session.execute(delete(MusehubBranch).where(MusehubBranch.repo_id == rid))
                await session.execute(delete(MusehubIssue).where(MusehubIssue.repo_id == rid))
                await session.execute(delete(MusehubRelease).where(MusehubRelease.repo_id == rid))
                await session.delete(repo)
                print(f"[-] Removed gabriel/{slug}")
            else:
                print(f"[=] gabriel/{slug} not present, nothing to remove")

        await session.flush()

        # ── 2. Gabriel's core user record ─────────────────────────────────────
        existing_user = await session.get(User, GABRIEL_ID)
        if existing_user is None:
            session.add(User(id=GABRIEL_ID, created_at=_now(365)))
            print("[+] Created User: gabriel")
        else:
            print("[=] User gabriel already exists, skipping")

        # ── 3. Gabriel's public profile ───────────────────────────────────────
        existing_profile = await session.get(MusehubProfile, GABRIEL_ID)
        if existing_profile is None:
            session.add(MusehubProfile(
                user_id=GABRIEL_ID,
                username="gabriel",
                display_name="Gabriel Cardona",
                bio=(
                    "Building Muse — a domain-agnostic VCS for multidimensional state. "
                    "Code, music, narrative, genomics. If it changes over time, Muse can version it."
                ),
                location="San Francisco, CA",
                website_url="https://musehub.ai",
                twitter_handle="cgcardona",
                is_verified=True,
                pinned_repo_ids=[],
                created_at=_now(365),
            ))
            print("[+] Created Profile: gabriel")
        else:
            print("[=] Profile gabriel already exists, skipping")

        await session.flush()

        # ── 4. Muse repo ──────────────────────────────────────────────────────
        existing = await session.get(MusehubRepo, MUSE_REPO_ID)
        if existing:
            print("[=] Repo gabriel/muse already exists, skipping")
        else:
            session.add(MusehubRepo(
                repo_id=MUSE_REPO_ID,
                owner="gabriel",
                owner_user_id=GABRIEL_ID,
                name=MUSE_REPO["name"],
                slug=MUSE_REPO["slug"],
                description=MUSE_REPO["description"],
                visibility="public",
                tags=MUSE_REPO["tags"],
                domain_meta=MUSE_REPO["domain_meta"],
                settings={"default_branch": "main"},
                created_at=_now(180),
            ))

            session.add(MusehubBranch(
                branch_id=_uid(f"branch-{MUSE_REPO_ID}-main"),
                repo_id=MUSE_REPO_ID,
                name="main",
                head_commit_id=None,
            ))

            prev_sha: str | None = None
            head_sha: str | None = None
            for i, (msg, days_ago) in enumerate(MUSE_COMMITS):
                sha = _sha(f"{MUSE_REPO_ID}-commit-{i}")[:40]
                session.add(MusehubCommit(
                    commit_id=sha,
                    repo_id=MUSE_REPO_ID,
                    branch="main",
                    parent_ids=[prev_sha] if prev_sha else [],
                    message=msg,
                    author="gabriel",
                    timestamp=_now(days_ago),
                    snapshot_id=None,
                    created_at=_now(days_ago),
                ))
                prev_sha = sha
                head_sha = sha

            branch = await session.get(MusehubBranch, _uid(f"branch-{MUSE_REPO_ID}-main"))
            if branch:
                branch.head_commit_id = head_sha

            for j, (title, state, labels) in enumerate(MUSE_ISSUES):
                session.add(MusehubIssue(
                    issue_id=_uid(f"issue-{MUSE_REPO_ID}-{j}"),
                    repo_id=MUSE_REPO_ID,
                    number=j + 1,
                    title=title,
                    body=f"Tracking: {title}",
                    state=state,
                    labels=labels,
                    author="gabriel",
                    created_at=_now(60 - j * 5),
                ))

            session.add(MusehubRelease(
                release_id=_uid(f"release-{MUSE_REPO_ID}-v0"),
                repo_id=MUSE_REPO_ID,
                tag="v0.3.0",
                title="v0.3.0",
                body="First public release.",
                commit_id=head_sha,
                download_urls={},
                author="gabriel",
                is_draft=False,
                is_prerelease=False,
                created_at=_now(10),
            ))

            await session.flush()
            print(f"[+] Repo gabriel/muse ({len(MUSE_COMMITS)} commits, {len(MUSE_ISSUES)} issues)")

        # ── 5. Pin muse on gabriel's profile ──────────────────────────────────
        profile = await session.get(MusehubProfile, GABRIEL_ID)
        if profile:
            profile.pinned_repo_ids = [MUSE_REPO_ID]
            print("[+] Pinned gabriel/muse on profile")

        await session.commit()

    print()
    print("=" * 60)
    print("SEED COMPLETE — only gabriel/muse remains")
    print("=" * 60)
    print()
    print("Mint your admin JWT:")
    print()
    print("  docker compose exec musehub python3 -c \"")
    print("  from musehub.auth.tokens import generate_access_code")
    print(f"  print(generate_access_code(user_id='{GABRIEL_ID}', duration_days=365, is_admin=True))")
    print("  \"")
    print()


if __name__ == "__main__":
    asyncio.run(seed())

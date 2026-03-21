"""
Production seed for musehub.ai

Creates gabriel's account and profile only.
The muse repo is pushed from the actual codebase via `muse push`.

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
from sqlalchemy import select, delete

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

UTC = timezone.utc


def _now(days: int = 0) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days)


def _uid(seed: str) -> str:
    return str(uuid.UUID(bytes=hashlib.md5(seed.encode()).digest()))


GABRIEL_ID = _uid("prod-gabriel-cgcardona")

# Slugs seeded in the past that should be removed if still present.
REMOVED_SLUGS = [
    "muse",
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

        # ── 1. Remove any previously-seeded repos ─────────────────────────────
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

        await session.flush()

        # ── 2. Gabriel's core user record ─────────────────────────────────────
        existing_user = await session.get(User, GABRIEL_ID)
        if existing_user is None:
            session.add(User(id=GABRIEL_ID, created_at=_now(365)))
            print("[+] Created User: gabriel")
        else:
            print("[=] User gabriel already exists")

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
            print("[=] Profile gabriel already exists")

        await session.commit()

    print()
    print("=" * 60)
    print("SEED COMPLETE — push repos via `muse push`")
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

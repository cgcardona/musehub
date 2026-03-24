"""MuseHub wire-tag persistence adapter.

Wire tags are lightweight semantic labels pushed from a Muse CLI client
(e.g. ``emotion:joyful``, ``section:verse``).  They are distinct from
version releases: they carry no semver, no channel, and no changelog.

This module is the ONLY place that touches the ``musehub_wire_tags`` table.

Boundary rules:
- Must NOT import state stores, SSE queues, or LLM clients.
- Must NOT import musehub.core.* modules.
- May import ORM models from musehub.db.musehub_models.
- May import Pydantic request models from musehub.models.musehub.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.musehub import WireTagInput

logger = logging.getLogger(__name__)


async def store_wire_tags(
    session: AsyncSession,
    repo_id: str,
    tags: list[WireTagInput],
) -> int:
    """Upsert a batch of wire tags for a repo.

    Uses a PostgreSQL ``INSERT … ON CONFLICT DO UPDATE`` to make re-pushes
    idempotent: if a tag label already exists for the repo, its ``commit_id``
    is updated to the incoming value and ``created_at`` is refreshed.

    The caller is responsible for committing the session after this call.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo (resolved from the URL — not trusted
            from the payload).
        tags: Parsed ``WireTagInput`` objects from the request body.

    Returns:
        Number of rows actually inserted or updated.
    """
    if not tags:
        return 0

    stored = 0
    for t in tags:
        tag_label = t.tag.strip()
        if not tag_label:
            continue

        # Parse the client-supplied created_at; fall back to server time.
        created_at: datetime
        try:
            created_at = datetime.fromisoformat(t.created_at) if t.created_at else datetime.now(tz=timezone.utc)
        except ValueError:
            created_at = datetime.now(tz=timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        stmt = (
            pg_insert(db.MusehubWireTag)
            .values(
                tag_id=t.tag_id,
                repo_id=repo_id,
                commit_id=t.commit_id,
                tag=tag_label,
                created_at=created_at,
            )
            .on_conflict_do_update(
                constraint="uq_musehub_wire_tags_repo_tag",
                set_={
                    "commit_id": t.commit_id,
                    "created_at": created_at,
                },
            )
        )
        await session.execute(stmt)
        stored += 1

    logger.info("✅ Stored %d wire tag(s) for repo %s", stored, repo_id)
    return stored


async def list_wire_tags(
    session: AsyncSession,
    repo_id: str,
) -> list[db.MusehubWireTag]:
    """Return all wire tags for a repo, ordered by creation time descending.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.

    Returns:
        List of ``MusehubWireTag`` ORM rows.
    """
    stmt = (
        select(db.MusehubWireTag)
        .where(db.MusehubWireTag.repo_id == repo_id)
        .order_by(db.MusehubWireTag.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())

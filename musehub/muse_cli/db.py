"""Minimal DB helpers retained for MuseHub tests.

The full muse_cli.db module was extracted to cgcardona/muse.
Only insert_commit and upsert_snapshot are retained here because
MuseHub test fixtures use them to populate the muse_commits table.

TODO(musehub-extraction): remove when MuseHub is extracted.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.muse_cli_models import MuseCliCommit, MuseCliSnapshot

logger = logging.getLogger(__name__)


async def upsert_snapshot(
    session: AsyncSession, manifest: dict[str, str], snapshot_id: str
) -> MuseCliSnapshot:
    """Insert a MuseCliSnapshot row, ignoring duplicates."""
    existing = await session.get(MuseCliSnapshot, snapshot_id)
    if existing is not None:
        logger.debug("⚠️ Snapshot %s already exists — skipped", snapshot_id[:8])
        return existing
    snap = MuseCliSnapshot(snapshot_id=snapshot_id, manifest=manifest)
    session.add(snap)
    logger.debug("✅ New snapshot %s (%d files)", snapshot_id[:8], len(manifest))
    return snap


async def insert_commit(session: AsyncSession, commit: MuseCliCommit) -> None:
    """Insert a new MuseCliCommit row."""
    session.add(commit)
    logger.debug("✅ New commit %s branch=%r", commit.commit_id[:8], commit.branch)

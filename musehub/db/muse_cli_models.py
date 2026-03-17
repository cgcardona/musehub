"""SQLAlchemy ORM models for the Muse CLI commit tables.

These models are retained in Maestro because MuseHub reads from
muse_commits / muse_snapshots / muse_tags / muse_objects to display
repository history.

TODO(musehub-extraction): move these models into the MuseHub repo
once MuseHub is extracted from Maestro.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from musehub.db.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MuseCliObject(Base):
    """A content-addressed blob: sha256(file_bytes) → bytes on disk."""

    __tablename__ = "muse_objects"

    object_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    def __repr__(self) -> str:
        return f"<MuseCliObject {self.object_id[:8]} size={self.size_bytes}>"


class MuseCliSnapshot(Base):
    """An immutable snapshot manifest: sha256(sorted(path:object_id pairs))."""

    __tablename__ = "muse_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    manifest: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    def __repr__(self) -> str:
        files = len(self.manifest) if self.manifest else 0
        return f"<MuseCliSnapshot {self.snapshot_id[:8]} files={files}>"


class MuseCliCommit(Base):
    """A versioned commit record pointing to a snapshot and its parent."""

    __tablename__ = "muse_commits"

    commit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_commit_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    parent2_commit_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("muse_snapshots.snapshot_id", ondelete="RESTRICT"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    commit_metadata: Mapped[dict[str, object] | None] = mapped_column(
        "metadata", JSON, nullable=True, default=None
    )

    def __repr__(self) -> str:
        return (
            f"<MuseCliCommit {self.commit_id[:8]} branch={self.branch!r}"
            f" msg={self.message[:30]!r}>"
        )


class MuseCliTag(Base):
    """A music-semantic tag attached to a Muse CLI commit."""

    __tablename__ = "muse_tags"

    tag_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repo_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    commit_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("muse_commits.commit_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    def __repr__(self) -> str:
        return f"<MuseCliTag {self.tag!r} commit={self.commit_id[:8]}>"

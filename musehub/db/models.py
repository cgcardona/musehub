"""SQLAlchemy ORM models for MuseHub auth layer.

Tables:
- muse_users: User accounts (id = JWT sub / device UUID)
- muse_access_tokens: JWT token tracking for revocation
"""
from __future__ import annotations


import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from musehub.db.database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


class User(Base):
    """
    User account.

    Single-identifier architecture: id is the JWT sub claim (a UUID).
    The app sends it as user_id in register and as X-Device-ID on asset
    requests; the JWT sub claim should be this same UUID so one identity
    is used everywhere.
    """
    __tablename__ = "muse_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    access_tokens: Mapped[list["AccessToken"]] = relationship(
        "AccessToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User {self.id}>"


class AccessToken(Base):
    """
    Access token tracking for potential revocation.

    Stores a SHA-256 hash of the JWT (not the token itself) for security.
    """
    __tablename__ = "muse_access_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("muse_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="access_tokens")

    def __repr__(self) -> str:
        status = "revoked" if self.revoked else "active"
        return f"<AccessToken {self.id[:8]} user={self.user_id[:8]} {status}>"

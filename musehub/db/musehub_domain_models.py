"""SQLAlchemy ORM models for the Muse domain plugin registry.

A Muse domain plugin defines a unique state space (MIDI, code, genomics, climate
simulation, 3D design, etc.) and the six interfaces Muse uses to version it.
MuseHub hosts a registry of these plugins so that any agent or human can
discover, install, and create repositories for any registered domain.

Namespace scheme: ``@{author_slug}/{slug}`` — mirrors npm scoped packages.
  Examples: ``@cgcardona/midi``, ``@cgcardona/code``, ``@deepmind/climate``

Every domain also carries an immutable content-addressed ``manifest_hash``
(SHA-256 of the capabilities JSON) that agents can use to pin exact versions.

Tables:
- musehub_domains: Domain plugin registry
- musehub_domain_installs: Which users have installed which domains
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from musehub.db.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class MusehubDomain(Base):
    """A registered Muse domain plugin in the MuseHub registry.

    Domain plugins define how Muse versions a particular type of state.
    Two canonical domains ship with MuseHub:
      - ``@cgcardona/midi``  — 21-dimensional MIDI state space
      - ``@cgcardona/code``  — symbol-graph code state space

    Third-party developers register their own domains:
      - ``@alice/genomics``  — CRISPR genome editing sequences
      - ``@deepmind/climate`` — climate simulation parameter grids

    ``author_slug`` + ``slug`` form the scoped identity ``@author_slug/slug``,
    enforced as a unique composite. The ``manifest_hash`` is a SHA-256 of the
    ``capabilities`` JSON blob — agents can use it to pin to a specific version
    of the domain definition.

    ``capabilities`` is a JSON object declaring:
      - ``dimensions``: list of insight dimension specs (name, description, unit)
      - ``viewer_type``: which primary viewer to use (piano_roll, symbol_graph, etc.)
      - ``supported_commands``: list of domain-specific CLI commands
      - ``artifact_types``: MIME types the domain produces (e.g. ["audio/midi"])
      - ``merge_semantics``: "ot" | "crdt" | "three_way"
    """

    __tablename__ = "musehub_domains"
    __table_args__ = (
        UniqueConstraint("author_slug", "slug", name="uq_musehub_domains_author_slug"),
    )

    domain_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    # author_user_id may be None for system-seeded built-in domains
    author_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # URL-safe author handle, e.g. "cgcardona"
    author_slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Domain name slug, e.g. "midi" — unique per author
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Human-readable display name, e.g. "MIDI"
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Short description shown in the domain registry
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Semver string, e.g. "1.0.0"
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    # SHA-256 of the capabilities JSON — immutable fingerprint for pinning
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # JSON capabilities blob — see class docstring for schema
    capabilities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Primary viewer type: "piano_roll" | "symbol_graph" | "sequence_viewer" | "generic"
    viewer_type: Mapped[str] = mapped_column(String(64), nullable=False, default="generic")
    # Number of repos using this domain (denormalised counter, updated async)
    install_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # True for MuseHub-verified built-in domains (@cgcardona/*)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True for deprecated domains that still exist but are no longer recommended
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )

    @property
    def scoped_id(self) -> str:
        """Return the npm-style scoped identifier, e.g. ``@cgcardona/midi``."""
        return f"@{self.author_slug}/{self.slug}"


class MusehubDomainInstall(Base):
    """Records a user's installation/adoption of a domain plugin.

    When a user creates a repository with a particular domain, a domain install
    row is created linking that user to that domain. This enables:
    - Per-domain install_count aggregation
    - User's "installed domains" list on their profile
    - Notifications when a domain is updated or deprecated

    The unique constraint on (user_id, domain_id) means a user is counted once
    per domain regardless of how many repos they create with it.
    """

    __tablename__ = "musehub_domain_installs"
    __table_args__ = (
        UniqueConstraint("user_id", "domain_id", name="uq_musehub_domain_installs"),
    )

    install_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    domain_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

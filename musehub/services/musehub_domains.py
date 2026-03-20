"""Domain plugin registry service — CRUD, manifest hashing, and discovery.

Provides all database operations for the musehub_domains and
musehub_domain_installs tables introduced in the V2 domain-agnostic migration.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_domain_models import MusehubDomain, MusehubDomainInstall
from musehub.db.musehub_models import MusehubRepo


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def compute_manifest_hash(capabilities: dict[str, Any]) -> str:
    """Return the SHA-256 hex digest of a capabilities JSON blob (sorted keys)."""
    blob = json.dumps(capabilities, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ── Response dataclasses ──────────────────────────────────────────────────────


@dataclass
class DomainResponse:
    domain_id: str
    author_slug: str
    slug: str
    scoped_id: str          # "@author/slug"
    display_name: str
    description: str
    version: str
    manifest_hash: str
    capabilities: dict[str, Any]
    viewer_type: str
    install_count: int
    is_verified: bool
    is_deprecated: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class DomainListResponse:
    domains: list[DomainResponse]
    total: int


@dataclass
class DomainReposResponse:
    domain_id: str
    scoped_id: str
    repos: list[dict[str, Any]]
    total: int


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(domain: MusehubDomain) -> DomainResponse:
    return DomainResponse(
        domain_id=domain.domain_id,
        author_slug=domain.author_slug,
        slug=domain.slug,
        scoped_id=f"@{domain.author_slug}/{domain.slug}",
        display_name=domain.display_name,
        description=domain.description,
        version=domain.version,
        manifest_hash=domain.manifest_hash,
        capabilities=dict(domain.capabilities) if domain.capabilities else {},
        viewer_type=domain.viewer_type,
        install_count=domain.install_count,
        is_verified=domain.is_verified,
        is_deprecated=domain.is_deprecated,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
    )


# ── Read operations ───────────────────────────────────────────────────────────


async def list_domains(
    session: AsyncSession,
    *,
    query: str | None = None,
    verified_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> DomainListResponse:
    """List registered domains with optional text search and filtering."""
    stmt = select(MusehubDomain).where(MusehubDomain.is_deprecated.is_(False))

    if verified_only:
        stmt = stmt.where(MusehubDomain.is_verified.is_(True))

    if query:
        q = f"%{query}%"
        stmt = stmt.where(
            MusehubDomain.display_name.ilike(q)
            | MusehubDomain.slug.ilike(q)
            | MusehubDomain.author_slug.ilike(q)
            | MusehubDomain.description.ilike(q)
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(MusehubDomain.install_count.desc(), MusehubDomain.created_at.desc())
    stmt = stmt.offset(offset).limit(page_size)

    result = await session.execute(stmt)
    domains = result.scalars().all()

    return DomainListResponse(
        domains=[_to_response(d) for d in domains],
        total=total,
    )


async def get_domain_by_scoped_id(
    session: AsyncSession,
    author_slug: str,
    slug: str,
) -> DomainResponse | None:
    """Fetch a single domain by its @author/slug identity."""
    stmt = select(MusehubDomain).where(
        MusehubDomain.author_slug == author_slug,
        MusehubDomain.slug == slug,
    )
    result = await session.execute(stmt)
    domain = result.scalar_one_or_none()
    return _to_response(domain) if domain else None


async def get_domain_by_id(
    session: AsyncSession,
    domain_id: str,
) -> DomainResponse | None:
    """Fetch a single domain by its UUID primary key."""
    stmt = select(MusehubDomain).where(MusehubDomain.domain_id == domain_id)
    result = await session.execute(stmt)
    domain = result.scalar_one_or_none()
    return _to_response(domain) if domain else None


async def list_repos_for_domain(
    session: AsyncSession,
    domain_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
) -> DomainReposResponse:
    """Return public repos using a specific domain plugin."""
    domain = await get_domain_by_id(session, domain_id)
    if domain is None:
        return DomainReposResponse(
            domain_id=domain_id, scoped_id="", repos=[], total=0
        )

    stmt = (
        select(MusehubRepo)
        .where(
            MusehubRepo.domain_id == domain_id,
            MusehubRepo.visibility == "public",
            MusehubRepo.deleted_at.is_(None),
        )
        .order_by(MusehubRepo.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(
        select(MusehubRepo).where(
            MusehubRepo.domain_id == domain_id,
            MusehubRepo.visibility == "public",
            MusehubRepo.deleted_at.is_(None),
        ).subquery()
    )

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    result = await session.execute(stmt)
    repos = result.scalars().all()

    return DomainReposResponse(
        domain_id=domain_id,
        scoped_id=domain.scoped_id,
        repos=[
            {
                "repo_id": r.repo_id,
                "owner": r.owner,
                "slug": r.slug,
                "name": r.name,
                "description": r.description,
                "tags": list(r.tags) if r.tags else [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in repos
        ],
        total=total,
    )


# ── Write operations ──────────────────────────────────────────────────────────


async def create_domain(
    session: AsyncSession,
    *,
    author_user_id: str,
    author_slug: str,
    slug: str,
    display_name: str,
    description: str,
    capabilities: dict[str, Any],
    viewer_type: str = "generic",
    version: str = "1.0.0",
) -> DomainResponse:
    """Register a new domain plugin in the MuseHub registry."""
    manifest_hash = compute_manifest_hash(capabilities)
    domain = MusehubDomain(
        domain_id=str(uuid.uuid4()),
        author_user_id=author_user_id,
        author_slug=author_slug,
        slug=slug,
        display_name=display_name,
        description=description,
        version=version,
        manifest_hash=manifest_hash,
        capabilities=capabilities,
        viewer_type=viewer_type,
        install_count=0,
        is_verified=False,
        is_deprecated=False,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    session.add(domain)
    await session.flush()
    return _to_response(domain)


async def record_domain_install(
    session: AsyncSession,
    user_id: str,
    domain_id: str,
) -> None:
    """Record that a user has adopted a domain plugin (idempotent)."""
    # Check if already installed
    existing = await session.execute(
        select(MusehubDomainInstall).where(
            MusehubDomainInstall.user_id == user_id,
            MusehubDomainInstall.domain_id == domain_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    install = MusehubDomainInstall(
        install_id=str(uuid.uuid4()),
        user_id=user_id,
        domain_id=domain_id,
        created_at=_utc_now(),
    )
    session.add(install)

    # Increment install_count on the domain row
    stmt = select(MusehubDomain).where(MusehubDomain.domain_id == domain_id)
    result = await session.execute(stmt)
    domain = result.scalar_one_or_none()
    if domain is not None:
        domain.install_count = (domain.install_count or 0) + 1

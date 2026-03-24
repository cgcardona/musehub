"""MuseHub release persistence adapter — single point of DB access for releases.

This module is the ONLY place that touches the ``musehub_releases`` table.
Route handlers delegate here; no business logic lives in routes.

Releases tie a semver tag (e.g. "v1.2.3") to a commit snapshot and carry
structured metadata: distribution channel, parsed semver components,
AI provenance fields, and an auto-generated changelog.

Boundary rules:
- Must NOT import state stores, SSE queues, or LLM clients.
- Must NOT import musehub.core.* modules.
- May import ORM models from musehub.db.musehub_models.
- May import Pydantic response models from musehub.models.musehub.
- May import the packager to resolve download URLs.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db import musehub_models as db
from musehub.models.musehub import (
    ChangelogEntryResponse,
    ReleaseAssetDownloadCount,
    ReleaseAssetListResponse,
    ReleaseAssetResponse,
    ReleaseDownloadStatsResponse,
    ReleaseDownloadUrls,
    ReleaseListResponse,
    ReleaseResponse,
    SemanticReleaseReportResponse,
)
from musehub.services.musehub_release_packager import build_empty_download_urls

logger = logging.getLogger(__name__)

# Valid distribution channels.
_VALID_CHANNELS: frozenset[str] = frozenset({"stable", "beta", "alpha", "nightly"})


def _urls_from_json(raw: dict[str, str]) -> ReleaseDownloadUrls:
    """Coerce the JSON blob stored in ``download_urls`` to a typed model."""
    return ReleaseDownloadUrls(
        midi_bundle=raw.get("midi_bundle"),
        stems=raw.get("stems"),
        mp3=raw.get("mp3"),
        musicxml=raw.get("musicxml"),
        metadata=raw.get("metadata"),
    )


def _parse_changelog(raw_json: str) -> list[ChangelogEntryResponse]:
    """Parse the ``changelog_json`` column into typed response objects."""
    try:
        entries = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(entries, list):
        return []
    result: list[ChangelogEntryResponse] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        commit_id = item.get("commit_id", "")
        message = item.get("message", "")
        if not isinstance(commit_id, str) or not isinstance(message, str):
            continue
        sem_ver_bump_raw = item.get("sem_ver_bump", "")
        sem_ver_bump = sem_ver_bump_raw if isinstance(sem_ver_bump_raw, str) else ""
        breaking_raw = item.get("breaking_changes", [])
        breaking: list[str] = (
            [str(b) for b in breaking_raw if isinstance(b, str)]
            if isinstance(breaking_raw, list)
            else []
        )
        author_raw = item.get("author", "")
        author = author_raw if isinstance(author_raw, str) else ""
        ts_raw = item.get("timestamp", "")
        timestamp = ts_raw if isinstance(ts_raw, str) else ""
        result.append(
            ChangelogEntryResponse(
                commit_id=commit_id,
                message=message,
                sem_ver_bump=sem_ver_bump,
                breaking_changes=breaking,
                author=author,
                timestamp=timestamp,
            )
        )
    return result


def _parse_semantic_report(raw_json: str) -> SemanticReleaseReportResponse | None:
    """Deserialise the ``semantic_report_json`` column into a typed model."""
    if not raw_json:
        return None
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return SemanticReleaseReportResponse.model_validate(data)
    except Exception:
        logger.warning("⚠️ Failed to parse semantic_report_json; treating as absent.")
        return None


def _to_release_response(row: db.MusehubRelease) -> ReleaseResponse:
    raw_urls: dict[str, str] = row.download_urls if isinstance(row.download_urls, dict) else {}
    semantic_report = _parse_semantic_report(getattr(row, "semantic_report_json", "") or "")
    return ReleaseResponse(
        release_id=row.release_id,
        tag=row.tag,
        title=row.title,
        body=row.body,
        commit_id=row.commit_id,
        snapshot_id=row.snapshot_id,
        channel=row.channel,
        semver_major=row.semver_major,
        semver_minor=row.semver_minor,
        semver_patch=row.semver_patch,
        semver_pre=row.semver_pre,
        semver_build=row.semver_build,
        download_urls=_urls_from_json(raw_urls),
        author=row.author,
        agent_id=row.agent_id,
        model_id=row.model_id,
        changelog=_parse_changelog(row.changelog_json),
        is_draft=row.is_draft,
        gpg_signature=row.gpg_signature,
        semantic_report=semantic_report,
        created_at=row.created_at,
    )


async def _tag_exists(session: AsyncSession, repo_id: str, tag: str) -> bool:
    """Return True if a release with this tag already exists for the repo."""
    stmt = select(db.MusehubRelease.release_id).where(
        db.MusehubRelease.repo_id == repo_id,
        db.MusehubRelease.tag == tag,
    )
    result = (await session.execute(stmt)).scalar_one_or_none()
    return result is not None


async def create_release(
    session: AsyncSession,
    *,
    repo_id: str,
    tag: str,
    title: str = "",
    body: str = "",
    commit_id: str | None,
    snapshot_id: str | None = None,
    channel: str = "stable",
    semver_major: int = 0,
    semver_minor: int = 0,
    semver_patch: int = 0,
    semver_pre: str = "",
    semver_build: str = "",
    download_urls: ReleaseDownloadUrls | None = None,
    author: str = "",
    agent_id: str = "",
    model_id: str = "",
    changelog: list[ChangelogEntryResponse] | None = None,
    is_draft: bool = False,
    gpg_signature: str | None = None,
    semantic_report_json: str = "",
) -> ReleaseResponse:
    """Persist a new release and return its wire representation.

    ``tag`` must be unique per repo. Raises ``ValueError`` if a release with
    the same tag already exists. The caller is responsible for committing the
    session after this call.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.
        tag: Semver tag (e.g. "v1.2.3") — unique per repo.
        title: Human-readable release title.
        body: Markdown release notes.
        commit_id: Optional commit to pin this release to.
        snapshot_id: Optional content-addressed snapshot ID.
        channel: Distribution channel (stable | beta | alpha | nightly).
        semver_major: Major version component.
        semver_minor: Minor version component.
        semver_patch: Patch version component.
        semver_pre: Pre-release label (empty for stable releases).
        semver_build: Build metadata (empty when absent).
        download_urls: Pre-built download URL map; defaults to empty URLs.
        author: Display name or identifier of the user publishing this release.
        agent_id: AI agent that produced the tip commit.
        model_id: AI model used by the agent.
        changelog: Auto-generated changelog entries.
        is_draft: Save as draft — not yet publicly visible.
        gpg_signature: ASCII-armoured GPG signature for the tag object.

    Returns:
        ``ReleaseResponse`` with all fields populated.

    Raises:
        ValueError: If a release with ``tag`` already exists for ``repo_id``.
        ValueError: If ``channel`` is not a recognised distribution channel.
    """
    if await _tag_exists(session, repo_id, tag):
        raise ValueError(f"Release tag '{tag}' already exists for repo {repo_id}")

    if channel not in _VALID_CHANNELS:
        raise ValueError(f"Unknown channel '{channel}'. Choose: {', '.join(sorted(_VALID_CHANNELS))}")

    urls = download_urls or build_empty_download_urls()
    urls_dict: dict[str, str] = {
        k: v
        for k, v in {
            "midi_bundle": urls.midi_bundle,
            "stems": urls.stems,
            "mp3": urls.mp3,
            "musicxml": urls.musicxml,
            "metadata": urls.metadata,
        }.items()
        if v is not None
    }

    changelog_entries = changelog or []
    changelog_json = json.dumps(
        [e.model_dump() for e in changelog_entries], default=str
    )

    release = db.MusehubRelease(
        repo_id=repo_id,
        tag=tag,
        title=title,
        body=body,
        commit_id=commit_id,
        snapshot_id=snapshot_id,
        channel=channel,
        semver_major=semver_major,
        semver_minor=semver_minor,
        semver_patch=semver_patch,
        semver_pre=semver_pre,
        semver_build=semver_build,
        download_urls=urls_dict,
        author=author,
        agent_id=agent_id,
        model_id=model_id,
        changelog_json=changelog_json,
        is_draft=is_draft,
        gpg_signature=gpg_signature,
        semantic_report_json=semantic_report_json,
    )
    session.add(release)
    await session.flush()
    await session.refresh(release)
    logger.info("✅ Created release %s for repo %s (channel=%s)", tag, repo_id, channel)
    return _to_release_response(release)


async def create_release_from_dict(
    session: AsyncSession,
    repo_id: str,
    data: dict[str, object],
) -> ReleaseResponse:
    """Create a release from a raw ``ReleaseDict`` payload sent by the Muse CLI.

    Accepts the wire format emitted by ``ReleaseRecord.to_dict()`` on the CLI
    side and maps it to ``create_release``.  Any unrecognised fields are ignored.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo (resolved from the URL, not from the payload).
        data: Parsed JSON dict matching the CLI ``ReleaseDict`` shape.

    Returns:
        ``ReleaseResponse`` for the newly created release.

    Raises:
        ValueError: If ``tag`` is missing, already exists, or ``channel`` is invalid.
    """
    tag = str(data.get("tag") or "")
    if not tag:
        raise ValueError("Release payload is missing required field 'tag'")

    title = str(data.get("title") or "")
    body = str(data.get("body") or "")
    commit_id_raw = data.get("commit_id")
    commit_id = str(commit_id_raw) if isinstance(commit_id_raw, str) else None
    snapshot_id_raw = data.get("snapshot_id")
    snapshot_id = str(snapshot_id_raw) if isinstance(snapshot_id_raw, str) else None
    channel_raw = data.get("channel")
    channel = str(channel_raw) if isinstance(channel_raw, str) else "stable"
    agent_id = str(data.get("agent_id") or "")
    model_id = str(data.get("model_id") or "")
    is_draft_raw = data.get("is_draft")
    is_draft = bool(is_draft_raw) if is_draft_raw is not None else False
    gpg_raw = data.get("gpg_signature")
    gpg_signature = str(gpg_raw) if isinstance(gpg_raw, str) else None

    # Parse semver components from the nested dict.
    semver_raw = data.get("semver")
    semver_major = 0
    semver_minor = 0
    semver_patch = 0
    semver_pre = ""
    semver_build = ""
    if isinstance(semver_raw, dict):
        maj = semver_raw.get("major")
        semver_major = int(maj) if isinstance(maj, int) else 0
        min_ = semver_raw.get("minor")
        semver_minor = int(min_) if isinstance(min_, int) else 0
        pat = semver_raw.get("patch")
        semver_patch = int(pat) if isinstance(pat, int) else 0
        pre = semver_raw.get("pre")
        semver_pre = str(pre) if isinstance(pre, str) else ""
        bld = semver_raw.get("build")
        semver_build = str(bld) if isinstance(bld, str) else ""

    # Parse changelog entries.
    changelog_raw = data.get("changelog")
    changelog_entries: list[ChangelogEntryResponse] = []
    if isinstance(changelog_raw, list):
        for item in changelog_raw:
            if not isinstance(item, dict):
                continue
            cid = item.get("commit_id", "")
            msg = item.get("message", "")
            if not isinstance(cid, str) or not isinstance(msg, str):
                continue
            bump_raw = item.get("sem_ver_bump", "")
            bump = str(bump_raw) if isinstance(bump_raw, str) else ""
            bc_raw = item.get("breaking_changes", [])
            bc: list[str] = (
                [str(b) for b in bc_raw if isinstance(b, str)]
                if isinstance(bc_raw, list)
                else []
            )
            author_raw = item.get("author", "")
            author = str(author_raw) if isinstance(author_raw, str) else ""
            ts_raw = item.get("timestamp", "")
            timestamp = str(ts_raw) if isinstance(ts_raw, str) else ""
            changelog_entries.append(
                ChangelogEntryResponse(
                    commit_id=cid,
                    message=msg,
                    sem_ver_bump=bump,
                    breaking_changes=bc,
                    author=author,
                    timestamp=timestamp,
                )
            )

    return await create_release(
        session,
        repo_id=repo_id,
        tag=tag,
        title=title,
        body=body,
        commit_id=commit_id,
        snapshot_id=snapshot_id,
        channel=channel,
        semver_major=semver_major,
        semver_minor=semver_minor,
        semver_patch=semver_patch,
        semver_pre=semver_pre,
        semver_build=semver_build,
        author="",
        agent_id=agent_id,
        model_id=model_id,
        changelog=changelog_entries,
        is_draft=is_draft,
        gpg_signature=gpg_signature,
    )


async def list_releases(
    session: AsyncSession,
    repo_id: str,
    *,
    channel: str | None = None,
    include_drafts: bool = False,
) -> list[ReleaseResponse]:
    """Return releases for a repo, newest first.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.
        channel: When given, restrict to this distribution channel.
        include_drafts: When False (default), draft releases are excluded.

    Returns:
        List of ``ReleaseResponse`` objects ordered by ``created_at`` descending.
    """
    stmt = (
        select(db.MusehubRelease)
        .where(db.MusehubRelease.repo_id == repo_id)
        .order_by(db.MusehubRelease.created_at.desc())
    )
    if channel is not None and channel in _VALID_CHANNELS:
        stmt = stmt.where(db.MusehubRelease.channel == channel)
    if not include_drafts:
        stmt = stmt.where(db.MusehubRelease.is_draft.is_(False))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_release_response(r) for r in rows]


async def get_release_by_tag(
    session: AsyncSession,
    repo_id: str,
    tag: str,
) -> ReleaseResponse | None:
    """Return a release by its tag for the given repo, or ``None`` if not found.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.
        tag: Version tag to look up (e.g. "v1.2.3").

    Returns:
        ``ReleaseResponse`` if found, otherwise ``None``.
    """
    stmt = select(db.MusehubRelease).where(
        db.MusehubRelease.repo_id == repo_id,
        db.MusehubRelease.tag == tag,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_release_response(row)


async def get_latest_release(
    session: AsyncSession,
    repo_id: str,
) -> ReleaseResponse | None:
    """Return the most recently created stable release for a repo, or ``None``.

    Used to populate the "Latest release" badge on the repo home page.
    Draft releases and non-stable channels are excluded to avoid
    surfacing unfinished work in the badge.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.

    Returns:
        The newest stable, non-draft ``ReleaseResponse`` or ``None``.
    """
    stmt = (
        select(db.MusehubRelease)
        .where(
            db.MusehubRelease.repo_id == repo_id,
            db.MusehubRelease.channel == "stable",
            db.MusehubRelease.is_draft.is_(False),
        )
        .order_by(db.MusehubRelease.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_release_response(row)


async def get_release_list_response(
    session: AsyncSession,
    repo_id: str,
) -> ReleaseListResponse:
    """Convenience wrapper that returns a ``ReleaseListResponse`` directly.

    Returns stable, non-draft releases only — suitable for the public release
    listing page.

    Args:
        session: Active async DB session.
        repo_id: UUID of the target repo.

    Returns:
        ``ReleaseListResponse`` containing all matching releases newest first.
    """
    releases = await list_releases(session, repo_id, include_drafts=False)
    return ReleaseListResponse(releases=releases)


async def delete_release_by_tag(
    session: AsyncSession,
    repo_id: str,
    tag: str,
) -> bool:
    """Delete a release by its tag for the given repo.

    Removes only the release label row — all commits, snapshots, and objects
    referenced by this release remain intact in the content-addressed store.

    The caller is responsible for committing the session after this call.

    Args:
        session: Active async DB session.
        repo_id: UUID of the owning repo.
        tag: Semver tag of the release to remove (e.g. "v1.2.0").

    Returns:
        ``True`` if the release was found and deleted; ``False`` if not found.
    """
    stmt = select(db.MusehubRelease).where(
        db.MusehubRelease.repo_id == repo_id,
        db.MusehubRelease.tag == tag,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    logger.info("✅ Retracted release %s from repo %s", tag, repo_id)
    return True


# ── Release asset helpers ─────────────────────────────────────────────────────


def _to_asset_response(row: db.MusehubReleaseAsset) -> ReleaseAssetResponse:
    """Convert a ``MusehubReleaseAsset`` ORM row to its wire representation."""
    return ReleaseAssetResponse(
        asset_id=row.asset_id,
        release_id=row.release_id,
        name=row.name,
        label=row.label,
        content_type=row.content_type,
        size=row.size,
        download_url=row.download_url,
        download_count=row.download_count,
        created_at=row.created_at,
    )


async def attach_asset(
    session: AsyncSession,
    *,
    release_id: str,
    repo_id: str,
    name: str,
    label: str = "",
    content_type: str = "",
    size: int = 0,
    download_url: str,
) -> ReleaseAssetResponse:
    """Attach a new downloadable asset to an existing release.

    The caller is responsible for committing the session after this call.

    Args:
        session: Active async DB session.
        release_id: UUID of the release to attach the asset to.
        repo_id: UUID of the owning repo (denormalised for efficient queries).
        name: Filename shown in the UI.
        label: Optional human-readable label (e.g. "MIDI Bundle").
        content_type: MIME type of the artifact.
        size: File size in bytes; 0 when unknown.
        download_url: Direct download URL for the artifact.

    Returns:
        ``ReleaseAssetResponse`` for the newly created asset.
    """
    asset = db.MusehubReleaseAsset(
        release_id=release_id,
        repo_id=repo_id,
        name=name,
        label=label,
        content_type=content_type,
        size=size,
        download_url=download_url,
    )
    session.add(asset)
    await session.flush()
    await session.refresh(asset)
    logger.info("✅ Attached asset %r to release %s", name, release_id)
    return _to_asset_response(asset)


async def get_asset(
    session: AsyncSession,
    asset_id: str,
) -> db.MusehubReleaseAsset | None:
    """Return the ``MusehubReleaseAsset`` row for ``asset_id``, or ``None``.

    Used by route handlers to validate that the asset belongs to the
    expected release before performing mutations.
    """
    stmt = select(db.MusehubReleaseAsset).where(
        db.MusehubReleaseAsset.asset_id == asset_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def remove_asset(
    session: AsyncSession,
    asset_id: str,
) -> bool:
    """Delete a release asset by its ID.

    The caller is responsible for committing the session after this call.

    Args:
        session: Active async DB session.
        asset_id: UUID of the asset to remove.

    Returns:
        ``True`` if the asset was found and deleted; ``False`` if not found.
    """
    row = await get_asset(session, asset_id)
    if row is None:
        return False
    await session.delete(row)
    logger.info("✅ Removed asset %s", asset_id)
    return True


async def get_download_stats(
    session: AsyncSession,
    release_id: str,
    tag: str,
) -> ReleaseDownloadStatsResponse:
    """Return per-asset download counts for a release.

    Args:
        session: Active async DB session.
        release_id: UUID of the release.
        tag: Version tag — echoed back in the response for convenience.

    Returns:
        ``ReleaseDownloadStatsResponse`` with per-asset counts and total.
    """
    stmt = (
        select(db.MusehubReleaseAsset)
        .where(db.MusehubReleaseAsset.release_id == release_id)
        .order_by(db.MusehubReleaseAsset.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    asset_counts = [
        ReleaseAssetDownloadCount(
            asset_id=row.asset_id,
            name=row.name,
            label=row.label,
            download_count=row.download_count,
        )
        for row in rows
    ]
    total = sum(a.download_count for a in asset_counts)
    return ReleaseDownloadStatsResponse(
        release_id=release_id,
        tag=tag,
        assets=asset_counts,
        total_downloads=total,
    )


async def list_release_assets(
    session: AsyncSession,
    release_id: str,
    tag: str,
) -> ReleaseAssetListResponse:
    """Return all assets attached to a release, ordered by creation time.

    Called by the release detail page to populate the Assets panel.
    Each asset exposes its file size, download count, and direct download URL
    so the UI can render the panel without additional API calls.

    Args:
        session: Active async DB session.
        release_id: UUID of the owning release.
        tag: Version tag — echoed back in the response for convenience.

    Returns:
        ``ReleaseAssetListResponse`` with assets ordered oldest-first.
    """
    stmt = (
        select(db.MusehubReleaseAsset)
        .where(db.MusehubReleaseAsset.release_id == release_id)
        .order_by(db.MusehubReleaseAsset.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return ReleaseAssetListResponse(
        release_id=release_id,
        tag=tag,
        assets=[_to_asset_response(r) for r in rows],
    )


async def increment_asset_download_count(
    session: AsyncSession,
    asset_id: str,
) -> bool:
    """Atomically increment the download counter for a release asset.

    Called by the UI download-tracking endpoint each time a user clicks a
    Download button on the release detail page. Uses an UPDATE statement so
    the counter increment is atomic and does not require a SELECT+UPDATE pair.

    Args:
        session: Active async DB session.
        asset_id: UUID of the asset to increment.

    Returns:
        ``True`` if the asset was found and updated; ``False`` otherwise.
    """
    from sqlalchemy import update as sa_update

    stmt = (
        sa_update(db.MusehubReleaseAsset)
        .where(db.MusehubReleaseAsset.asset_id == asset_id)
        .values(download_count=db.MusehubReleaseAsset.download_count + 1)
        .returning(db.MusehubReleaseAsset.asset_id)
    )
    updated_id: str | None = (await session.execute(stmt)).scalar_one_or_none()
    return updated_id is not None

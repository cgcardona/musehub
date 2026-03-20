"""MuseHub release management route handlers.

Endpoint summary:
  POST /repos/{repo_id}/releases — create a release
  GET /repos/{repo_id}/releases — list all releases (newest first)
  GET /repos/{repo_id}/releases/{tag} — get a single release by tag
  GET /repos/{repo_id}/releases/{tag}/assets — list assets for a release
  POST /repos/{repo_id}/releases/{tag}/assets — attach asset to release
  POST /repos/{repo_id}/releases/{tag}/assets/{asset_id}/download — record download event
  DELETE /repos/{repo_id}/releases/{tag}/assets/{asset_id} — remove asset from release
  GET /repos/{repo_id}/releases/{tag}/downloads — per-asset download counts
  GET /repos/{repo_id}/tags — all tags derived from releases (namespace-grouped)

A release ties a version tag (e.g. "v1.0") to a commit snapshot and carries
Markdown release notes plus structured download package URLs. Tags are unique
per repo — POSTing a duplicate tag returns 409 Conflict.

Write endpoints require a valid JWT Bearer token.
Read endpoints use optional auth — visibility is gated by repo visibility.
No business logic lives here — all persistence is delegated to
``musehub.services.musehub_releases``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.dependencies import TokenClaims, optional_token, require_valid_token
from musehub.db import get_db
from musehub.models.musehub import (
    ReleaseAssetCreate,
    ReleaseAssetListResponse,
    ReleaseAssetResponse,
    ReleaseCreate,
    ReleaseDownloadStatsResponse,
    ReleaseListResponse,
    ReleaseResponse,
    TagListResponse,
    TagResponse,
)
from musehub.services import musehub_releases
from musehub.services import musehub_repository

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/repos/{repo_id}/releases",
    response_model=ReleaseResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRelease",
    summary="Create a release for a MuseHub repo",
)
async def create_release(
    repo_id: str,
    body: ReleaseCreate,
    db: AsyncSession = Depends(get_db),
    token: TokenClaims = Depends(require_valid_token),
) -> ReleaseResponse:
    """Create a new release tied to an optional commit snapshot.

    Returns 404 if the repo does not exist. Returns 409 if a release with
    the same ``tag`` already exists for this repo.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

    try:
        release = await musehub_releases.create_release(
            db,
            repo_id=repo_id,
            tag=body.tag,
            title=body.title,
            body=body.body,
            commit_id=body.commit_id,
            author=token.get("sub", ""),
            is_prerelease=body.is_prerelease,
            is_draft=body.is_draft,
            gpg_signature=body.gpg_signature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    return release


@router.get(
    "/repos/{repo_id}/releases",
    response_model=ReleaseListResponse,
    operation_id="listReleases",
    summary="List all releases for a MuseHub repo",
)
async def list_releases(
    repo_id: str,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> ReleaseListResponse:
    """Return all releases for the repo ordered newest first.

    Returns 404 if the repo does not exist.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    if repo.visibility != "public" and claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access private repos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await musehub_releases.get_release_list_response(db, repo_id)


@router.get(
    "/repos/{repo_id}/tags",
    response_model=TagListResponse,
    operation_id="listTags",
    summary="List all tags for a repo (derived from releases)",
)
async def list_tags(
    repo_id: str,
    namespace: str | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> TagListResponse:
    """Return all tags for the repo, grouped by namespace.

    Tags are derived from releases. The ``namespace`` field is extracted from
    the tag name — ``emotion:happy`` → namespace ``emotion``, ``v1.0`` →
    namespace ``version``.

    Query parameters:
    - ``namespace``: filter to a single namespace prefix
    - ``sort``: ``newest`` (default) | ``alpha`` | ``namespace``

    Returns 404 if the repo does not exist.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    if repo.visibility != "public" and claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access private repos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    releases = await musehub_releases.list_releases(db, repo_id)

    all_tags: list[TagResponse] = []
    for release in releases:
        tag_str = release.tag
        ns = tag_str.split(":", 1)[0] if ":" in tag_str else "version"
        all_tags.append(
            TagResponse(
                tag=tag_str,
                namespace=ns,
                commit_id=release.commit_id,
                message=release.title,
                created_at=release.created_at,
            )
        )

    active_sort = sort or "newest"
    if active_sort == "alpha":
        all_tags.sort(key=lambda t: t.tag)
    elif active_sort == "namespace":
        all_tags.sort(key=lambda t: (t.namespace, t.tag))

    filtered = [t for t in all_tags if t.namespace == namespace] if namespace else all_tags
    namespaces = sorted({t.namespace for t in all_tags})
    return TagListResponse(tags=filtered, namespaces=namespaces)


@router.get(
    "/repos/{repo_id}/releases/{tag}",
    response_model=ReleaseResponse,
    operation_id="getRelease",
    summary="Get a single release by tag",
)
async def get_release(
    repo_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> ReleaseResponse:
    """Return the release identified by ``tag`` for the given repo.

    Returns 404 if the repo or the tag does not exist.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    if repo.visibility != "public" and claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access private repos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    release = await musehub_releases.get_release_by_tag(db, repo_id, tag)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{tag}' not found",
        )
    return release


# ── Asset management helpers ──────────────────────────────────────────────────


async def _get_release_or_404(
    db: AsyncSession, repo_id: str, tag: str, claims: TokenClaims | None
) -> ReleaseResponse:
    """Resolve and authorise release access; raises 404 / 401 as appropriate."""
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    if repo.visibility != "public" and claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access private repos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    release = await musehub_releases.get_release_by_tag(db, repo_id, tag)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{tag}' not found",
        )
    return release


# ── Asset list ────────────────────────────────────────────────────────────────


@router.get(
    "/repos/{repo_id}/releases/{tag}/assets",
    response_model=ReleaseAssetListResponse,
    operation_id="listReleaseAssets",
    summary="List downloadable assets for a release",
)
async def list_release_assets(
    repo_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> ReleaseAssetListResponse:
    """Return all assets attached to the release identified by tag.

    The response includes file size and download count for each asset so the
    release detail page can render the Assets panel in a single request.

    Returns 404 when the repo or tag does not exist.
    Returns 401 when the repo is private and no token is supplied.
    """
    release = await _get_release_or_404(db, repo_id, tag, claims)
    return await musehub_releases.list_release_assets(db, release.release_id, tag)


# ── Asset download tracking ───────────────────────────────────────────────────


@router.post(
    "/repos/{repo_id}/releases/{tag}/assets/{asset_id}/download",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="recordAssetDownload",
    summary="Record a download event for a release asset",
)
async def record_asset_download(
    repo_id: str,
    tag: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> None:
    """Increment the download counter for the specified asset.

    Called by the UI when a user clicks the Download button on the release
    detail page. No auth required for public repos — anonymous downloads are
    counted. The counter is updated atomically via a single UPDATE statement.

    Returns 404 when the repo, tag, or asset does not exist.
    Returns 401 when the repo is private and no token is supplied.
    """
    release = await _get_release_or_404(db, repo_id, tag, claims)
    asset_row = await musehub_releases.get_asset(db, asset_id)
    if asset_row is None or asset_row.release_id != release.release_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found on release '{tag}'",
        )
    found = await musehub_releases.increment_asset_download_count(db, asset_id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found",
        )
    await db.commit()


# ── Download stats ────────────────────────────────────────────────────────────


@router.get(
    "/repos/{repo_id}/releases/{tag}/downloads",
    response_model=ReleaseDownloadStatsResponse,
    operation_id="getReleaseDownloadStats",
    summary="Get download counts per asset for a release",
)
async def get_release_download_stats(
    repo_id: str,
    tag: str,
    db: AsyncSession = Depends(get_db),
    claims: TokenClaims | None = Depends(optional_token),
) -> ReleaseDownloadStatsResponse:
    """Return per-asset download counts for the release identified by ``tag``.

    Returns 404 when the repo or tag does not exist.
    Returns 401 when the repo is private and no token is supplied.
    """
    release = await _get_release_or_404(db, repo_id, tag, claims)
    return await musehub_releases.get_download_stats(db, release.release_id, tag)


# ── Asset attach ──────────────────────────────────────────────────────────────


@router.post(
    "/repos/{repo_id}/releases/{tag}/assets",
    response_model=ReleaseAssetResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="attachReleaseAsset",
    summary="Attach a downloadable asset to a release",
)
async def attach_release_asset(
    repo_id: str,
    tag: str,
    body: ReleaseAssetCreate,
    db: AsyncSession = Depends(get_db),
    token: TokenClaims = Depends(require_valid_token),
) -> ReleaseAssetResponse:
    """Attach a new downloadable asset to the release identified by ``tag``.

    Returns 404 when the repo or tag does not exist.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

    release = await musehub_releases.get_release_by_tag(db, repo_id, tag)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{tag}' not found",
        )

    asset = await musehub_releases.attach_asset(
        db,
        release_id=release.release_id,
        repo_id=repo_id,
        name=body.name,
        label=body.label,
        content_type=body.content_type,
        size=body.size,
        download_url=body.download_url,
    )
    await db.commit()
    return asset


# ── Asset remove ──────────────────────────────────────────────────────────────


@router.delete(
    "/repos/{repo_id}/releases/{tag}/assets/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteReleaseAsset",
    summary="Remove an asset from a release",
)
async def delete_release_asset(
    repo_id: str,
    tag: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    token: TokenClaims = Depends(require_valid_token),
) -> None:
    """Remove the asset identified by ``asset_id`` from the given release.

    Returns 404 when the repo, tag, or asset does not exist, or when the
    asset does not belong to the specified release.
    """
    repo = await musehub_repository.get_repo(db, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

    release = await musehub_releases.get_release_by_tag(db, repo_id, tag)
    if release is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Release '{tag}' not found",
        )

    asset_row = await musehub_releases.get_asset(db, asset_id)
    if asset_row is None or asset_row.release_id != release.release_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found on release '{tag}'",
        )

    await musehub_releases.remove_asset(db, asset_id)
    await db.commit()

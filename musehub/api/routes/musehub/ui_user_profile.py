"""Enhanced MuseHub user profile page — .

Replaces the stub profile handler in ui.py with a full-featured profile page:
  - 52×7 GitHub-style contribution heatmap (green intensity by commit count)
  - 8 achievement badges with server-side unlock criteria
  - Up to 6 pinned repo cards (name, description, genre, stars, forks)
  - Activity feed tab with All / Commits / PRs / Issues / Stars filter

Endpoint summary:
  GET /{username}
    HTML (default) → rich profile shell; JavaScript hydrates from ?format=json.
    JSON → EnhancedProfileResponse (badges, heatmap stats, pinned repos,
                      paginated activity feed). Agents use this for machine-readable
                      profile data without navigating a separate /api/v1/... URL.

Why a separate module:
  profile_page() in ui.py was a stub that just passed username to the template.
  The enhanced version needs DB access, several aggregate queries, and its own
  Pydantic response model — enough complexity to warrant its own file, matching
  the pattern of ui_similarity.py, ui_blame.py, etc.
"""
from __future__ import annotations


import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response as StarletteResponse

from musehub.api.routes.musehub._templates import templates
from musehub.db import get_db
from musehub.db import musehub_models as dbm
from musehub.models.base import CamelModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["musehub-ui"])

# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HeatmapDay(CamelModel):
    """One day in the 52×7 contribution heatmap."""

    date: str = Field(..., description="ISO date string (YYYY-MM-DD)")
    count: int = Field(0, ge=0, description="Commit count for this day")
    intensity: int = Field(0, ge=0, le=3, description="0=none 1=light 2=medium 3=dark")
    domain_counts: dict[str, int] = Field(default_factory=dict, description="domain_id → commit count")
    dominant_domain: str | None = Field(None, description="domain_id with most commits this day")


class DomainStat(CamelModel):
    """Per-domain activity summary shown on the profile page."""

    domain_id: str | None = None
    domain_name: str = "Unknown"
    scoped_id: str | None = None
    viewer_type: str = Field("generic", description="symbol_graph | piano_roll | generic")
    repo_count: int = Field(0, ge=0)
    commit_count: int = Field(0, ge=0)


class HeatmapStats(CamelModel):
    """Aggregate stats displayed below the heatmap grid."""

    days: list[HeatmapDay]
    total_contributions: int = Field(0, ge=0)
    longest_streak: int = Field(0, ge=0, description="Longest consecutive-day streak (days)")
    current_streak: int = Field(0, ge=0, description="Current consecutive-day streak (days)")


class Badge(CamelModel):
    """An achievement badge shown on the profile page."""

    id: str
    name: str
    description: str
    icon: str = Field(..., description="Emoji or icon character representing the badge")
    earned: bool
    earned_at: datetime | None = None


class PinnedRepoCard(CamelModel):
    """Compact pinned-repo card (up to 6 per profile)."""

    repo_id: str
    name: str
    slug: str
    owner: str
    description: str
    star_count: int = Field(0, ge=0)
    fork_count: int = Field(0, ge=0)
    commit_count: int = Field(0, ge=0)
    domain_id: str | None = None
    domain_name: str | None = None
    domain_viewer_type: str = Field("generic", description="symbol_graph | piano_roll | generic")
    language: str = Field("", description="Primary language tag derived from repo tags")
    primary_genre: str | None = Field(None, description="First genre tag on the repo, if any")
    tags: list[str] = Field(default_factory=list)


class ActivityEvent(CamelModel):
    """A single entry in the user activity feed."""

    event_id: str
    event_type: str
    description: str
    repo_name: str | None = None
    repo_slug: str | None = None
    repo_owner: str | None = None
    created_at: datetime


class EnhancedProfileResponse(CamelModel):
    """Full structured response for GET /users/{username}?format=json.

    Agents consume this to inspect a user's contribution history, badges, and
    recent activity without navigating the HTML profile page.

    CC attribution fields (``is_verified``, ``cc_license``) were added to surface Public Domain / Creative Commons status inline so
    the frontend can render the CC badge without a secondary API call.
    """

    username: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    location: str | None = None
    website_url: str | None = None
    twitter_handle: str | None = None
    # True for Public Domain / CC licensed archive artists (e.g. bach, chopin, kevin_macleod)
    is_verified: bool = False
    # CC attribution string such as "Public Domain" or "CC BY 4.0"; None = all rights reserved
    cc_license: str | None = None
    heatmap: HeatmapStats
    domain_stats: list[DomainStat] = Field(default_factory=list)
    badges: list[Badge]
    pinned_repos: list[PinnedRepoCard]
    activity: list[ActivityEvent]
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1)
    total_events: int = Field(0, ge=0)
    activity_filter: str = Field("all")


# ---------------------------------------------------------------------------
# Heatmap helpers
# ---------------------------------------------------------------------------

_HEATMAP_WEEKS = 52


def _intensity(count: int) -> int:
    """Map a commit count to a 0–3 intensity bucket."""
    if count == 0:
        return 0
    if count <= 3:
        return 1
    if count <= 6:
        return 2
    return 3


def _compute_streaks(days: list[HeatmapDay]) -> tuple[int, int]:
    """Return (longest_streak, current_streak) from an ordered list of HeatmapDay."""
    longest = 0
    current = 0
    for day in days:
        if day.count > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest, current


async def _build_heatmap(session: AsyncSession, user_id: str) -> HeatmapStats:
    """Compute the 52-week contribution heatmap for ``user_id``, with per-domain breakdown."""
    today = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today - timedelta(weeks=_HEATMAP_WEEKS)

    # All repos owned by this user (public + private)
    repo_result = await session.execute(
        select(dbm.MusehubRepo.repo_id).where(
            dbm.MusehubRepo.owner_user_id == user_id,
            dbm.MusehubRepo.deleted_at.is_(None),
        )
    )
    repo_ids = [row[0] for row in repo_result]

    # Per-day total counts
    counts: dict[str, int] = {}
    # Per-day per-domain counts: {date: {domain_id: count}}
    domain_counts: dict[str, dict[str, int]] = {}

    if repo_ids:
        # Total counts per day
        daily_result = await session.execute(
            select(
                func.date(dbm.MusehubCommit.timestamp).label("day"),
                func.count(dbm.MusehubCommit.commit_id).label("cnt"),
            )
            .where(
                dbm.MusehubCommit.repo_id.in_(repo_ids),
                dbm.MusehubCommit.timestamp >= cutoff,
            )
            .group_by(func.date(dbm.MusehubCommit.timestamp))
        )
        counts = {str(row.day): int(row.cnt) for row in daily_result}

        # Domain-broken-down counts per day (join with repos to get domain_id)
        domain_daily_result = await session.execute(
            select(
                func.date(dbm.MusehubCommit.timestamp).label("day"),
                dbm.MusehubRepo.domain_id.label("domain_id"),
                func.count(dbm.MusehubCommit.commit_id).label("cnt"),
            )
            .join(dbm.MusehubRepo, dbm.MusehubCommit.repo_id == dbm.MusehubRepo.repo_id)
            .where(
                dbm.MusehubCommit.repo_id.in_(repo_ids),
                dbm.MusehubCommit.timestamp >= cutoff,
            )
            .group_by(func.date(dbm.MusehubCommit.timestamp), dbm.MusehubRepo.domain_id)
        )
        for row in domain_daily_result:
            date_str = str(row.day)
            did = str(row.domain_id) if row.domain_id else "unknown"
            if date_str not in domain_counts:
                domain_counts[date_str] = {}
            domain_counts[date_str][did] = int(row.cnt)

    days: list[HeatmapDay] = []
    cursor = cutoff
    while cursor <= today:
        iso = cursor.strftime("%Y-%m-%d")
        c = counts.get(iso, 0)
        dc = domain_counts.get(iso, {})
        dominant = max(dc, key=lambda k: dc[k]) if dc else None
        days.append(HeatmapDay(
            date=iso, count=c, intensity=_intensity(c),
            domain_counts=dc, dominant_domain=dominant,
        ))
        cursor += timedelta(days=1)

    total = sum(d.count for d in days)
    longest, current = _compute_streaks(days)
    return HeatmapStats(
        days=days,
        total_contributions=total,
        longest_streak=longest,
        current_streak=current,
    )


async def _compute_domain_stats(session: AsyncSession, user_id: str) -> list[DomainStat]:
    """Compute per-domain repo/commit counts for a user's repos."""
    # Get all repos with their domain_id
    repo_result = await session.execute(
        select(dbm.MusehubRepo.repo_id, dbm.MusehubRepo.domain_id).where(
            dbm.MusehubRepo.owner_user_id == user_id,
            dbm.MusehubRepo.deleted_at.is_(None),
        )
    )
    repo_rows = list(repo_result)
    if not repo_rows:
        return []

    repo_ids = [r[0] for r in repo_rows]
    domain_repo_count: dict[str | None, int] = {}
    for _, did in repo_rows:
        domain_repo_count[did] = domain_repo_count.get(did, 0) + 1

    # Commit counts grouped by domain_id
    commit_result = await session.execute(
        select(
            dbm.MusehubRepo.domain_id.label("domain_id"),
            func.count(dbm.MusehubCommit.commit_id).label("cnt"),
        )
        .join(dbm.MusehubRepo, dbm.MusehubCommit.repo_id == dbm.MusehubRepo.repo_id)
        .where(dbm.MusehubCommit.repo_id.in_(repo_ids))
        .group_by(dbm.MusehubRepo.domain_id)
    )
    domain_commit_count: dict[str | None, int] = {
        row.domain_id: int(row.cnt) for row in commit_result
    }

    # Resolve domain metadata from the domains table (raw SQL — no ORM model for this table)
    all_domain_ids = [did for did in domain_repo_count.keys() if did is not None]
    domain_meta: dict[str, tuple[str, str | None, str]] = {}  # id → (name, scoped_id, viewer_type)
    if all_domain_ids:
        from sqlalchemy import text as sa_text
        placeholders = ", ".join(f":did_{i}" for i in range(len(all_domain_ids)))
        params = {f"did_{i}": did for i, did in enumerate(all_domain_ids)}
        domain_rows = await session.execute(
            sa_text(
                f"SELECT domain_id, display_name, author_slug, slug, viewer_type "
                f"FROM musehub_domains WHERE domain_id IN ({placeholders})"
            ),
            params,
        )
        for row in domain_rows:
            scoped = f"@{row.author_slug}/{row.slug}" if row.author_slug else row.slug
            domain_meta[row.domain_id] = (row.display_name or "Unknown", scoped, row.viewer_type or "generic")

    stats: list[DomainStat] = []
    # Sort by commit count descending
    for did, repo_count in sorted(domain_repo_count.items(), key=lambda x: domain_commit_count.get(x[0], 0), reverse=True):
        meta = domain_meta.get(did or "", ("Unknown", None, "generic")) if did else ("Unknown", None, "generic")
        stats.append(DomainStat(
            domain_id=did,
            domain_name=meta[0],
            scoped_id=meta[1],
            viewer_type=meta[2],
            repo_count=repo_count,
            commit_count=domain_commit_count.get(did, 0),
        ))
    return stats


# ---------------------------------------------------------------------------
# Badge helpers
# ---------------------------------------------------------------------------

_BADGE_DEFS: list[tuple[str, str, str, str]] = [
    ("first_commit",      "First Commit",      "Made your first Muse commit",                         "◎"),
    ("century",           "Century",            "Reached 100 cumulative commits — serious dedication", "💯"),
    ("domain_explorer",   "Domain Explorer",    "Worked across 2+ distinct domains",                  "⬡"),
    ("polymath",          "Polymath",           "Active in 3+ distinct domains",                      "◈"),
    ("collaborator",      "Collaborator",       "Contributed to 3+ repos you don't own",              "⑂"),
    ("pioneer",           "Pioneer",            "Explored 5+ distinct tags across your repos",        "🔭"),
    ("release_engineer",  "Release Engineer",   "Published 3+ official releases",                     "⬆"),
    ("community_star",    "Community Star",     "Received 100+ reactions across your repos",          "★"),
]


async def _compute_badges(
    session: AsyncSession,
    username: str,
    user_id: str,
) -> list[Badge]:
    """Derive achievement badges from DB state for a user."""

    # ── Fetch all repos owned by user ────────────────────────────────────────
    repo_result = await session.execute(
        select(dbm.MusehubRepo).where(
            dbm.MusehubRepo.owner_user_id == user_id,
            dbm.MusehubRepo.deleted_at.is_(None),
        )
    )
    user_repos = list(repo_result.scalars())
    user_repo_ids = [r.repo_id for r in user_repos]

    # ── Aggregate queries ─────────────────────────────────────────────────────

    # Total commit count across owned repos
    total_commits = 0
    if user_repo_ids:
        commit_result = await session.execute(
            select(func.count(dbm.MusehubCommit.commit_id)).where(
                dbm.MusehubCommit.repo_id.in_(user_repo_ids)
            )
        )
        total_commits = int(commit_result.scalar() or 0)

    # Distinct genres: all tags across all repos (tags are free-form, include genre/key/instrument)
    all_tags: set[str] = set()
    for repo in user_repos:
        for tag in (repo.tags or []):
            all_tags.add(tag.lower())

    # Repos this user committed to that they don't own (collaborator badge)
    collab_repos = 0
    if username:
        collab_query = select(func.count(func.distinct(dbm.MusehubCommit.repo_id))).where(
            dbm.MusehubCommit.author == username,
        )
        if user_repo_ids:
            collab_query = collab_query.where(
                dbm.MusehubCommit.repo_id.not_in(user_repo_ids)
            )
        collab_result = await session.execute(collab_query)
        collab_repos = int(collab_result.scalar() or 0)

    # Forks of user's repos
    fork_count = 0
    if user_repo_ids:
        fork_result = await session.execute(
            select(func.count(dbm.MusehubFork.fork_id)).where(
                dbm.MusehubFork.source_repo_id.in_(user_repo_ids)
            )
        )
        fork_count = int(fork_result.scalar() or 0)

    # Total releases across owned repos
    release_count = 0
    if user_repo_ids:
        release_result = await session.execute(
            select(func.count(dbm.MusehubRelease.release_id)).where(
                dbm.MusehubRelease.repo_id.in_(user_repo_ids)
            )
        )
        release_count = int(release_result.scalar() or 0)

    # Total reactions on repos owned by user
    reaction_count = 0
    if user_repo_ids:
        reaction_result = await session.execute(
            select(func.count(dbm.MusehubReaction.reaction_id)).where(
                dbm.MusehubReaction.repo_id.in_(user_repo_ids)
            )
        )
        reaction_count = int(reaction_result.scalar() or 0)

    # Domain diversity: count distinct domain_ids across user's repos
    distinct_domains: set[str] = set()
    for repo in user_repos:
        if repo.domain_id:
            distinct_domains.add(repo.domain_id)

    # ── Map criteria to earned/not-earned ────────────────────────────────────
    criteria: dict[str, bool] = {
        "first_commit":    total_commits >= 1,
        "century":         total_commits >= 100,
        "domain_explorer": len(distinct_domains) >= 2,
        "polymath":        len(distinct_domains) >= 3,
        "collaborator":    collab_repos >= 3,
        "pioneer":         len(all_tags) >= 5,
        "release_engineer": release_count >= 3,
        "community_star":  reaction_count >= 100,
    }

    return [
        Badge(id=bid, name=name, description=desc, icon=icon, earned=criteria.get(bid, False))
        for bid, name, desc, icon in _BADGE_DEFS
    ]


# ---------------------------------------------------------------------------
# Pinned repo helpers
# ---------------------------------------------------------------------------

_KNOWN_GENRE_KEYWORDS = frozenset(
    {
        "jazz", "blues", "rock", "pop", "classical", "electronic", "hip-hop", "r&b",
        "soul", "funk", "reggae", "country", "folk", "metal", "punk", "indie",
        "ambient", "experimental", "neo-soul", "bossa-nova", "afrobeats",
    }
)


def _extract_genre(tags: list[str]) -> str | None:
    """Return the first genre-looking tag from a repo's tag list."""
    for tag in tags:
        if tag.lower() in _KNOWN_GENRE_KEYWORDS or "genre:" in tag.lower():
            return tag
    return None


async def _build_pinned_repos(
    session: AsyncSession,
    pinned_repo_ids: list[str],
) -> list[PinnedRepoCard]:
    """Fetch up to 6 pinned repos with star and fork counts."""
    if not pinned_repo_ids:
        return []

    repo_result = await session.execute(
        select(dbm.MusehubRepo).where(
            dbm.MusehubRepo.repo_id.in_(pinned_repo_ids),
            dbm.MusehubRepo.deleted_at.is_(None),
        )
    )
    repos = list(repo_result.scalars())

    # Preserve pinned order
    repo_map = {r.repo_id: r for r in repos}
    ordered = [repo_map[rid] for rid in pinned_repo_ids if rid in repo_map][:6]

    if not ordered:
        return []

    ordered_ids = [r.repo_id for r in ordered]

    # Star counts
    star_result = await session.execute(
        select(
            dbm.MusehubStar.repo_id,
            func.count(dbm.MusehubStar.star_id).label("cnt"),
        )
        .where(dbm.MusehubStar.repo_id.in_(ordered_ids))
        .group_by(dbm.MusehubStar.repo_id)
    )
    star_counts = {row.repo_id: int(row.cnt) for row in star_result}

    # Fork counts (repos forked FROM these repos)
    fork_result = await session.execute(
        select(
            dbm.MusehubFork.source_repo_id,
            func.count(dbm.MusehubFork.fork_id).label("cnt"),
        )
        .where(dbm.MusehubFork.source_repo_id.in_(ordered_ids))
        .group_by(dbm.MusehubFork.source_repo_id)
    )
    fork_counts = {row.source_repo_id: int(row.cnt) for row in fork_result}

    # Commit counts per pinned repo
    commit_counts: dict[str, int] = {}
    if ordered_ids:
        commit_result = await session.execute(
            select(
                dbm.MusehubCommit.repo_id,
                func.count(dbm.MusehubCommit.commit_id).label("cnt"),
            )
            .where(dbm.MusehubCommit.repo_id.in_(ordered_ids))
            .group_by(dbm.MusehubCommit.repo_id)
        )
        commit_counts = {row.repo_id: int(row.cnt) for row in commit_result}

    # Domain metadata for pinned repos (raw SQL — no ORM model for musehub_domains)
    domain_ids = list({r.domain_id for r in ordered if r.domain_id})
    domain_info: dict[str, tuple[str, str]] = {}  # domain_id → (name, viewer_type)
    if domain_ids:
        from sqlalchemy import text as sa_text
        placeholders = ", ".join(f":did_{i}" for i in range(len(domain_ids)))
        params = {f"did_{i}": did for i, did in enumerate(domain_ids)}
        domain_rows = await session.execute(
            sa_text(
                f"SELECT domain_id, display_name, viewer_type "
                f"FROM musehub_domains WHERE domain_id IN ({placeholders})"
            ),
            params,
        )
        for row in domain_rows:
            domain_info[row.domain_id] = (row.display_name or "Unknown", row.viewer_type or "generic")

    return [
        PinnedRepoCard(
            repo_id=r.repo_id,
            name=r.name,
            slug=r.slug,
            owner=r.owner,
            description=r.description or "",
            star_count=star_counts.get(r.repo_id, 0),
            fork_count=fork_counts.get(r.repo_id, 0),
            commit_count=commit_counts.get(r.repo_id, 0),
            domain_id=r.domain_id,
            domain_name=domain_info.get(r.domain_id or "", ("Unknown", "generic"))[0] if r.domain_id else None,
            domain_viewer_type=domain_info.get(r.domain_id or "", ("Unknown", "generic"))[1] if r.domain_id else "generic",
            language=next((t for t in (r.tags or []) if "lang:" in t.lower()), ""),
            primary_genre=_extract_genre(r.tags or []),
            tags=list(r.tags or [])[:8],
        )
        for r in ordered
    ]


# ---------------------------------------------------------------------------
# Activity feed helpers
# ---------------------------------------------------------------------------

_ACTIVITY_EVENT_TYPES = frozenset(
    {
        "commit_pushed", "pr_opened", "pr_merged", "pr_closed",
        "issue_opened", "issue_closed", "branch_created", "branch_deleted",
        "tag_pushed", "session_started", "session_ended",
    }
)

# Maps filter tab → set of event_type values to include
_FILTER_MAP: dict[str, frozenset[str]] = {
    "all": _ACTIVITY_EVENT_TYPES,
    "commits": frozenset({"commit_pushed"}),
    "prs": frozenset({"pr_opened", "pr_merged", "pr_closed"}),
    "issues": frozenset({"issue_opened", "issue_closed"}),
    "stars": frozenset({"tag_pushed"}), # re-using tag_pushed; stars are tracked separately
}


async def _build_activity(
    session: AsyncSession,
    user_id: str,
    username: str,
    activity_filter: str,
    page: int,
    per_page: int,
) -> tuple[list[ActivityEvent], int]:
    """Fetch paginated activity events for repos owned by ``user_id``."""

    repo_result = await session.execute(
        select(dbm.MusehubRepo.repo_id, dbm.MusehubRepo.name, dbm.MusehubRepo.slug, dbm.MusehubRepo.owner).where(
            dbm.MusehubRepo.owner_user_id == user_id,
            dbm.MusehubRepo.deleted_at.is_(None),
        )
    )
    repo_rows = list(repo_result)
    repo_ids = [row[0] for row in repo_rows]
    repo_meta: dict[str, tuple[str, str, str]] = {
        row[0]: (row[1], row[2], row[3]) for row in repo_rows
    }

    if not repo_ids:
        return [], 0

    allowed_types = _FILTER_MAP.get(activity_filter, _ACTIVITY_EVENT_TYPES)

    base_filter = [
        dbm.MusehubEvent.repo_id.in_(repo_ids),
        dbm.MusehubEvent.event_type.in_(list(allowed_types)),
    ]

    total_result = await session.execute(
        select(func.count(dbm.MusehubEvent.event_id)).where(*base_filter)
    )
    total = int(total_result.scalar() or 0)

    offset = (page - 1) * per_page
    events_result = await session.execute(
        select(dbm.MusehubEvent)
        .where(*base_filter)
        .order_by(desc(dbm.MusehubEvent.created_at))
        .limit(per_page)
        .offset(offset)
    )
    events = list(events_result.scalars())

    activity: list[ActivityEvent] = []
    for ev in events:
        meta = repo_meta.get(ev.repo_id)
        activity.append(
            ActivityEvent(
                event_id=ev.event_id,
                event_type=ev.event_type,
                description=ev.description,
                repo_name=meta[0] if meta else None,
                repo_slug=meta[1] if meta else None,
                repo_owner=meta[2] if meta else None,
                created_at=ev.created_at,
            )
        )

    return activity, total


# ---------------------------------------------------------------------------
# Full JSON payload assembly
# ---------------------------------------------------------------------------


async def _build_enhanced_profile(
    session: AsyncSession,
    username: str,
    activity_filter: str,
    page: int,
    per_page: int,
) -> EnhancedProfileResponse:
    """Assemble the full EnhancedProfileResponse from DB.

    Raises HTTP 404 when the username has no registered profile.
    """
    from musehub.services import musehub_profile as profile_svc # local import avoids circular

    profile = await profile_svc.get_profile_by_username(session, username)
    if profile is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No profile found for username '{username}'",
        )

    heatmap, domain_stats, badges, pinned_repos, (activity, total_events) = (
        await _build_heatmap(session, profile.user_id),
        await _compute_domain_stats(session, profile.user_id),
        await _compute_badges(session, username, profile.user_id),
        await _build_pinned_repos(session, list(profile.pinned_repo_ids or [])),
        await _build_activity(session, profile.user_id, username, activity_filter, page, per_page),
    )

    return EnhancedProfileResponse(
        username=profile.username,
        display_name=profile.display_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        location=profile.location,
        website_url=profile.website_url,
        twitter_handle=profile.twitter_handle,
        is_verified=profile.is_verified,
        cc_license=profile.cc_license,
        heatmap=heatmap,
        domain_stats=domain_stats,
        badges=badges,
        pinned_repos=pinned_repos,
        activity=activity,
        page=page,
        per_page=per_page,
        total_events=total_events,
        activity_filter=activity_filter,
    )


# ---------------------------------------------------------------------------
# Inline HTML shell (rendered for human browsers)
# ---------------------------------------------------------------------------

_EVENT_ICONS: dict[str, str] = {
    "commit_pushed": "📦",
    "pr_opened": "🔀",
    "pr_merged": "✅",
    "pr_closed": "❌",
    "issue_opened": "🐛",
    "issue_closed": "✔️",
    "branch_created": "🌿",
    "branch_deleted": "🗑️",
    "tag_pushed": "🏷️",
    "session_started": "▶️",
    "session_ended": "⏹️",
}




# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------


@router.get(
    "/{username}",
    summary="Enhanced MuseHub user profile — heatmap, badges, pinned repos, activity feed",
)
async def profile_page(
    request: Request,
    username: str,
    format: str | None = Query(None, description="Set to 'json' for structured data"),
    tab: str = Query("all", description="Activity filter: all | commits | prs | issues | stars"),
    page: int = Query(1, ge=1, description="Activity page (1-indexed)"),
    per_page: int = Query(20, ge=1, le=100, description="Activity events per page"),
    db: AsyncSession = Depends(get_db),
) -> StarletteResponse:
    """Render the enhanced MuseHub user profile page or return structured JSON.

    HTML (default):
        Returns a self-contained HTML shell. Client-side JavaScript fetches
        profile data, contribution heatmap, badges, pinned repos, and activity
        from ``/api/v1/users/{username}`` and from the ``?format=json``
        alternate of this same URL.

    JSON (``Accept: application/json`` or ``?format=json``):
        Returns ``EnhancedProfileResponse`` with:
        - ``heatmap`` — 52×7 contribution grid with per-day commit counts and
          intensity buckets (0=none, 1=light, 2=medium, 3=dark) plus streak stats.
        - ``badges`` — 8 achievement badges with ``earned`` flag.
        - ``pinnedRepos`` — up to 6 pinned repo cards with star/fork counts,
          primary genre, and description.
        - ``activity`` — paginated activity feed filtered by ``?tab``.

    No JWT required — profile pages are publicly accessible.
    Returns 404 when the username has no registered MuseHub profile.
    """
    # Determine if the caller wants JSON
    accept = request.headers.get("accept", "")
    wants_json = format == "json" or "application/json" in accept

    if wants_json:
        data = await _build_enhanced_profile(db, username, tab, page, per_page)
        return JSONResponse(content=data.model_dump(by_alias=True, mode="json"))

    # HTML path — lightweight shell, JS hydrates from ?format=json
    from musehub.api.routes.musehub.json_alternate import add_json_available_header
    resp = templates.TemplateResponse(
        request,
        "musehub/pages/profile.html",
        {"username": username},
    )
    return add_json_available_header(
        resp, request, api_link=f"/api/v1/users/{username}"
    )

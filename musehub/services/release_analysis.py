"""Server-side semantic release analysis for MuseHub.

After a release is pushed, MuseHub runs this analysis against its own stored
graph — the same data the CLI would have used locally, but already persisted:

- ``musehub_snapshots.manifest``  — {path: object_id} for the release snapshot
- ``StorageBackend.get()``        — raw file bytes for AST parsing
- ``musehub_commits.commit_meta`` — structured_delta, provenance, sem_ver_bump

The heavy CPU work (symbol extraction, language classification, AST parsing)
is delegated to the muse code-domain plugin, which is available via the
``/muse`` volume mount and ``PYTHONPATH=/muse:/app`` set in the override.

All I/O is async; CPU-bound symbol extraction runs in ``asyncio.to_thread``
to avoid blocking the event loop.  The result is written back to
``musehub_releases.semantic_report_json`` as a single JSON blob.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_models import MusehubCommit, MusehubRelease, MusehubSnapshot
from musehub.storage import get_backend

logger = logging.getLogger(__name__)

_MAX_SEMANTIC_FILES = 800


# ---------------------------------------------------------------------------
# MuseHub-native I/O helpers
# ---------------------------------------------------------------------------


async def _get_snapshot_manifest(
    session: AsyncSession,
    repo_id: str,
    snapshot_id: str,
) -> dict[str, str]:
    """Read {path: object_id} from musehub_snapshots."""
    result = await session.execute(
        select(MusehubSnapshot).where(
            MusehubSnapshot.snapshot_id == snapshot_id,
            MusehubSnapshot.repo_id == repo_id,
        )
    )
    row = result.scalar_one_or_none()
    return dict(row.manifest) if row else {}


async def _fetch_semantic_bytes(
    repo_id: str,
    manifest: dict[str, str],
) -> dict[str, bytes]:
    """Fetch raw bytes for all semantic files concurrently via StorageBackend."""
    try:
        from muse.plugins.code._query import is_semantic
    except ImportError:
        logger.warning("⚠️ muse not importable — cannot fetch semantic bytes")
        return {}

    backend = get_backend()
    semantic: dict[str, str] = {
        path: oid for path, oid in manifest.items() if is_semantic(path)
    }
    if len(semantic) > _MAX_SEMANTIC_FILES:
        semantic = dict(list(semantic.items())[:_MAX_SEMANTIC_FILES])

    async def _fetch(path: str, oid: str) -> tuple[str, bytes | None]:
        raw = await backend.get(repo_id, oid)
        return path, raw

    results = await asyncio.gather(*[_fetch(p, oid) for p, oid in semantic.items()])
    return {p: raw for p, raw in results if raw is not None}


async def _walk_commits(
    session: AsyncSession,
    repo_id: str,
    commit_id: str,
    max_commits: int = 500,
) -> list[dict[str, Any]]:
    """Walk the parent chain from *commit_id*, returning lightweight commit dicts."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = commit_id

    while current and len(rows) < max_commits and current not in seen:
        seen.add(current)
        result = await session.execute(
            select(MusehubCommit).where(
                MusehubCommit.commit_id == current,
                MusehubCommit.repo_id == repo_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            break
        meta: dict[str, Any] = dict(row.commit_meta or {})
        rows.append(
            {
                "commit_id": row.commit_id,
                "message": row.message,
                "author": row.author,
                "parent_ids": list(row.parent_ids or []),
                "structured_delta": meta.get("structured_delta") or {},
                "agent_id": meta.get("agent_id", ""),
                "model_id": meta.get("model_id", ""),
                "breaking_changes": list(meta.get("breaking_changes") or []),
                "reviewed_by": list(meta.get("reviewed_by") or []),
            }
        )
        parents: list[str] = list(row.parent_ids or [])
        current = parents[0] if parents else None

    return rows


# ---------------------------------------------------------------------------
# Synchronous computation helpers (run in asyncio.to_thread)
# ---------------------------------------------------------------------------


def _build_symbol_map(file_bytes: dict[str, bytes]) -> dict[str, Any]:
    """Parse AST symbols from pre-fetched file bytes. Runs in a thread."""
    try:
        from muse.plugins.code.ast_parser import parse_symbols
    except ImportError:
        return {}

    result: dict[str, Any] = {}
    for file_path, raw in file_bytes.items():
        tree = parse_symbols(raw, file_path)
        if tree:
            result[file_path] = tree
    return result


# Languages that have a meaningful public API surface.
# Documentation formats (Markdown, RST, plain text) are excluded — their
# "symbols" are headings, not callable code, and create noise in API diffs.
_CODE_API_LANGUAGES: frozenset[str] = frozenset({
    "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java", "C#",
    "C", "C++", "Ruby", "Kotlin", "Swift", "CSS", "SCSS",
})


def _is_public_symbol(name: str, kind: str) -> bool:
    if kind in ("import", "section", "rule", "variable"):
        return False
    if name.startswith("__") and name.endswith("__"):
        return name in ("__init__", "__call__", "__new__")
    return not name.startswith("_")


def _api_surface(symbol_map: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    try:
        from muse.plugins.code._query import language_of
    except ImportError:
        return {}

    surface: dict[str, tuple[str, Any]] = {}
    for file_path, tree in symbol_map.items():
        lang = language_of(file_path)
        if lang not in _CODE_API_LANGUAGES:
            continue
        for address, rec in tree.items():
            if _is_public_symbol(rec["name"], rec["kind"]):
                surface[address] = (lang, rec)
    return surface


def _sync_compute_report(
    manifest: dict[str, str],
    file_bytes: dict[str, bytes],
    prev_file_bytes: dict[str, bytes],
    commits: list[dict[str, Any]],
    changelog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Pure CPU-bound report computation. Runs in a thread pool."""
    try:
        from muse.plugins.code._query import flat_symbol_ops, language_of, touched_files
    except ImportError:
        logger.warning("⚠️ muse plugin not importable — returning empty report")
        return _empty_report()

    # Symbol maps
    sym_map = _build_symbol_map(file_bytes)
    prev_sym_map = _build_symbol_map(prev_file_bytes) if prev_file_bytes else {}

    total_files = len(manifest)
    total_symbols = sum(len(tree) for tree in sym_map.values())

    # Language stats
    lang_files: dict[str, int] = {}
    lang_symbols: dict[str, int] = {}
    for path in manifest:
        lang = language_of(path)
        lang_files[lang] = lang_files.get(lang, 0) + 1
    for path, tree in sym_map.items():
        lang = language_of(path)
        lang_symbols[lang] = lang_symbols.get(lang, 0) + len(tree)
    languages = [
        {"language": lang, "files": lang_files[lang], "symbols": lang_symbols.get(lang, 0)}
        for lang in sorted(lang_files, key=lambda l: lang_files[l], reverse=True)
    ]

    # Symbol kind counts
    kind_counts: dict[str, int] = {}
    for tree in sym_map.values():
        for rec in tree.values():
            k = rec["kind"]
            kind_counts[k] = kind_counts.get(k, 0) + 1
    symbols_by_kind = [
        {"kind": k, "count": kind_counts[k]}
        for k in sorted(kind_counts, key=lambda k: kind_counts[k], reverse=True)
    ]

    # Semantic file count
    semantic_files = len(sym_map)

    # API surface diff
    curr_surface = _api_surface(sym_map)
    prev_surface = _api_surface(prev_sym_map)

    all_addresses = set(curr_surface) | set(prev_surface)
    api_added: list[dict[str, str]] = []
    api_removed: list[dict[str, str]] = []
    api_modified: list[dict[str, str]] = []
    for address in sorted(all_addresses):
        if address not in prev_surface:
            lang, rec = curr_surface[address]
            api_added.append({"address": address, "language": lang, "kind": rec["kind"], "change": "added"})
        elif address not in curr_surface:
            lang, rec = prev_surface[address]
            api_removed.append({"address": address, "language": lang, "kind": rec["kind"], "change": "removed"})
        else:
            prev_rec = prev_surface[address][1]
            curr_rec = curr_surface[address][1]
            if prev_rec["content_id"] != curr_rec["content_id"]:
                lang = curr_surface[address][0]
                api_modified.append({"address": address, "language": lang, "kind": curr_rec["kind"], "change": "modified"})

    max_changes = 200
    api_added = api_added[:max_changes]
    api_removed = api_removed[:max_changes]
    api_modified = api_modified[:max_changes]

    # File hotspots from structured_deltas
    churn: dict[str, int] = {}
    for commit in commits:
        delta = commit.get("structured_delta") or {}
        ops = delta.get("ops") or []
        for file_path in touched_files(ops):
            churn[file_path] = churn.get(file_path, 0) + 1
        for op in ops:
            if op.get("op") != "patch":
                addr = op.get("address", "")
                if addr:
                    churn[addr] = churn.get(addr, 0) + 1

    top_files = sorted(churn, key=lambda p: churn[p], reverse=True)[:10]
    file_hotspots = [
        {"file_path": p, "change_count": churn[p], "language": language_of(p)}
        for p in top_files
    ]

    # Refactor events
    refactor_events: list[dict[str, str]] = []
    for commit in commits:
        cid = commit["commit_id"][:8]
        delta = commit.get("structured_delta") or {}
        ops = delta.get("ops") or []
        for op in ops:
            op_type = op.get("op", "")
            addr = op.get("address", "")
            if op_type == "patch" and op.get("from_address"):
                refactor_events.append({"kind": "move", "address": addr, "detail": f"moved from {op['from_address']}", "commit_id": cid})
            elif op_type == "insert" and "/" in addr:
                refactor_events.append({"kind": "add", "address": addr, "detail": op.get("content_summary", ""), "commit_id": cid})
            elif op_type == "delete" and "/" in addr:
                refactor_events.append({"kind": "delete", "address": addr, "detail": op.get("content_summary", ""), "commit_id": cid})
        for sym_op in flat_symbol_ops(ops):
            if sym_op.get("op") == "insert":
                refactor_events.append({"kind": "add", "address": sym_op.get("address", ""), "detail": sym_op.get("content_summary", ""), "commit_id": cid})
            elif sym_op.get("op") == "delete":
                refactor_events.append({"kind": "delete", "address": sym_op.get("address", ""), "detail": sym_op.get("content_summary", ""), "commit_id": cid})
        if len(refactor_events) >= 50:
            break
    refactor_events = refactor_events[:50]

    # Files changed
    files_changed = len({
        p
        for commit in commits
        for p in touched_files((commit.get("structured_delta") or {}).get("ops") or [])
    })

    # Provenance
    breaking: list[str] = []
    seen_bc: set[str] = set()
    human_commits = 0
    agent_commits = 0
    agents: set[str] = set()
    models: set[str] = set()
    reviewers: set[str] = set()

    for commit in commits:
        for bc in commit.get("breaking_changes") or []:
            if bc not in seen_bc:
                seen_bc.add(bc)
                breaking.append(bc)
        aid = commit.get("agent_id", "")
        mid = commit.get("model_id", "")
        if aid:
            agent_commits += 1
            agents.add(aid)
        else:
            human_commits += 1
        if mid:
            models.add(mid)
        for reviewer in commit.get("reviewed_by") or []:
            reviewers.add(reviewer)

    return {
        "languages": languages,
        "total_files": total_files,
        "semantic_files": semantic_files,
        "total_symbols": total_symbols,
        "symbols_by_kind": symbols_by_kind,
        "files_changed": files_changed,
        "api_added": api_added,
        "api_removed": api_removed,
        "api_modified": api_modified,
        "file_hotspots": file_hotspots,
        "refactor_events": refactor_events,
        "breaking_changes": breaking,
        "human_commits": human_commits,
        "agent_commits": agent_commits,
        "unique_agents": sorted(agents),
        "unique_models": sorted(models),
        "reviewers": sorted(reviewers),
    }


def _empty_report() -> dict[str, Any]:
    return {
        "languages": [],
        "total_files": 0,
        "semantic_files": 0,
        "total_symbols": 0,
        "symbols_by_kind": [],
        "files_changed": 0,
        "api_added": [],
        "api_removed": [],
        "api_modified": [],
        "file_hotspots": [],
        "refactor_events": [],
        "breaking_changes": [],
        "human_commits": 0,
        "agent_commits": 0,
        "unique_agents": [],
        "unique_models": [],
        "reviewers": [],
    }


# ---------------------------------------------------------------------------
# Background task entry point
# ---------------------------------------------------------------------------


async def analyse_release_background(repo_id: str, release_id: str) -> None:
    """Compute semantic analysis for a release and persist the result.

    Designed to run as a FastAPI ``BackgroundTask`` after a successful release
    push.  Opens its own DB session so it is independent of the request
    lifecycle.  Any error is logged and swallowed — a failed analysis never
    breaks a release.
    """
    from musehub.db.database import AsyncSessionLocal

    logger.info("🔍 Starting semantic analysis for release %s", release_id)
    async with AsyncSessionLocal() as session:
        try:
            await _run_analysis(session, repo_id, release_id)
            await session.commit()
            logger.info("✅ Semantic analysis complete for release %s", release_id)
        except Exception:
            logger.warning(
                "⚠️ Semantic analysis failed for release %s",
                release_id,
                exc_info=True,
            )


async def _run_analysis(
    session: AsyncSession,
    repo_id: str,
    release_id: str,
) -> None:
    """Core analysis logic — reads from DB/storage, writes result back."""
    # Load release
    result = await session.execute(
        select(MusehubRelease).where(MusehubRelease.release_id == release_id)
    )
    release = result.scalar_one_or_none()
    if release is None or not release.snapshot_id or not release.commit_id:
        logger.warning("Release %s missing snapshot/commit — skipping", release_id)
        return

    # Load current snapshot manifest
    manifest = await _get_snapshot_manifest(session, repo_id, release.snapshot_id)
    if not manifest:
        logger.warning("No manifest found for snapshot %s", release.snapshot_id[:8])
        return

    # Find previous release to diff API surface against
    prev_snapshot_id: str | None = None
    prev_result = await session.execute(
        select(MusehubRelease)
        .where(
            MusehubRelease.repo_id == repo_id,
            MusehubRelease.release_id != release_id,
            MusehubRelease.is_draft.is_(False),
        )
        .order_by(MusehubRelease.created_at.desc())
        .limit(1)
    )
    prev_release = prev_result.scalar_one_or_none()
    if prev_release and prev_release.snapshot_id:
        prev_snapshot_id = prev_release.snapshot_id

    # Fetch all file bytes concurrently
    if prev_snapshot_id:
        prev_manifest = await _get_snapshot_manifest(session, repo_id, prev_snapshot_id)
    else:
        prev_manifest = {}

    file_bytes, prev_file_bytes = await asyncio.gather(
        _fetch_semantic_bytes(repo_id, manifest),
        _fetch_semantic_bytes(repo_id, prev_manifest),
    )

    # Walk commit chain
    commits = await _walk_commits(session, repo_id, release.commit_id)

    # Parse changelog for compatibility (structured_delta already in commits)
    try:
        changelog: list[dict[str, Any]] = json.loads(release.changelog_json or "[]")
    except (json.JSONDecodeError, TypeError):
        changelog = []

    # CPU-bound computation in thread pool
    report = await asyncio.to_thread(
        _sync_compute_report,
        manifest,
        file_bytes,
        prev_file_bytes,
        commits,
        changelog,
    )

    lang_summary = ", ".join(
        f"{s['language']} ({s['files']}f)" for s in report["languages"][:3]
    )
    logger.info(
        "✓ %s symbols · %s (release %s)",
        report["total_symbols"],
        lang_summary,
        release_id,
    )

    # Persist
    await session.execute(
        update(MusehubRelease)
        .where(MusehubRelease.release_id == release_id)
        .values(semantic_report_json=json.dumps(report))
    )

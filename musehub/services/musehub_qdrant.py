"""Qdrant semantic search pipeline for MuseHub.

Three collections mirror the three levels of the Muse data model:

    mh_repos    — one vector per repo (description, domain, topics, readme)
    mh_commits  — one vector per commit (message, structured_delta summary)
    mh_objects  — one vector per file-level object (content, path)

Point payloads carry the IDs needed to resolve back to Postgres rows so
clients can fetch full metadata after a semantic search.

Usage (called from the wire push handler after ingestion)::

    from musehub.services.musehub_qdrant import get_qdrant, embed_commit

    qdrant = get_qdrant()
    if qdrant is not None:
        await embed_commit(qdrant, commit, repo)

The service degrades gracefully — if ``QDRANT_URL`` is not set the module
returns ``None`` from ``get_qdrant()`` and all callers skip embedding.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

COLLECTION_REPOS = "mh_repos"
COLLECTION_COMMITS = "mh_commits"
COLLECTION_OBJECTS = "mh_objects"

VECTOR_DIM = 1536  # text-embedding-3-small output dimension

_qdrant_client: object | None = None


def get_qdrant() -> Any | None:
    """Return a cached Qdrant async client, or None if not configured."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client
    url = os.environ.get("QDRANT_URL") or ""
    if not url:
        return None
    try:
        from qdrant_client import AsyncQdrantClient
        api_key = os.environ.get("QDRANT_API_KEY") or None
        _qdrant_client = AsyncQdrantClient(url=url, api_key=api_key)
        return _qdrant_client
    except ImportError:
        logger.warning("qdrant_client not installed — semantic search disabled")
        return None
    except Exception as exc:
        logger.error("Qdrant init error: %s", exc)
        return None


async def _embed_text(text: str) -> list[float] | None:
    """Call OpenAI text-embedding-3-small and return a float vector.

    Returns None if embedding fails so callers can skip gracefully.
    """
    api_key = os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        return None
    try:
        import httpx
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": "text-embedding-3-small", "input": text[:8000]},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            result: list[float] = data["data"][0]["embedding"]
            return result
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


def _sha_to_uint64(sha: str) -> int:
    """Convert a hex SHA string to a uint64 point ID for Qdrant."""
    digest = hashlib.sha256(sha.encode()).digest()[:8]
    return int.from_bytes(digest, "big") & 0x7FFFFFFFFFFFFFFF


async def ensure_collections(qdrant: Any) -> None:
    """Idempotently create the three MuseHub Qdrant collections.

    Safe to call on every startup — existing collections are left unchanged.
    """
    try:
        from qdrant_client.models import Distance, VectorParams
        existing = {c.name for c in (await qdrant.get_collections()).collections}
        for name in (COLLECTION_REPOS, COLLECTION_COMMITS, COLLECTION_OBJECTS):
            if name not in existing:
                await qdrant.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
                )
                logger.info("Created Qdrant collection: %s", name)
    except Exception as exc:
        logger.error("Qdrant collection setup failed: %s", exc)


async def embed_repo(qdrant: Any, repo: Any) -> None:
    """Upsert a repo embedding into ``mh_repos``."""
    try:
        from qdrant_client.models import PointStruct
        text_parts = [
            repo.slug or "",
            repo.description or "",
            (repo.domain_meta or {}).get("topics_str", "") if isinstance(repo.domain_meta, dict) else "",
        ]
        text = " ".join(p for p in text_parts if p).strip()
        if not text:
            return
        vector = await _embed_text(text)
        if vector is None:
            return
        point_id = _sha_to_uint64(repo.repo_id)
        await qdrant.upsert(
            collection_name=COLLECTION_REPOS,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "repo_id": repo.repo_id,
                    "owner": repo.owner,
                    "slug": repo.slug,
                    "domain": (repo.domain_meta or {}).get("domain") if isinstance(repo.domain_meta, dict) else None,
                    "description": repo.description or "",
                },
            )],
        )
    except Exception as exc:
        logger.warning("embed_repo failed for %s: %s", getattr(repo, "repo_id", "?"), exc)


async def embed_commit(qdrant: Any, commit: Any) -> None:
    """Upsert a commit embedding into ``mh_commits``."""
    try:
        from qdrant_client.models import PointStruct
        text = commit.message or ""
        meta = commit.commit_meta or {}
        if isinstance(meta, dict):
            breaking = " ".join(meta.get("breaking_changes") or [])
            if breaking:
                text = f"{text} BREAKING: {breaking}"
        if not text.strip():
            return
        vector = await _embed_text(text)
        if vector is None:
            return
        point_id = _sha_to_uint64(commit.commit_id)
        await qdrant.upsert(
            collection_name=COLLECTION_COMMITS,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "commit_id": commit.commit_id,
                    "repo_id": commit.repo_id,
                    "branch": commit.branch or "",
                    "author": commit.author or "",
                    "message": commit.message or "",
                },
            )],
        )
    except Exception as exc:
        logger.warning("embed_commit failed for %s: %s", getattr(commit, "commit_id", "?"), exc)


async def embed_object(qdrant: Any, obj: Any, path: str = "") -> None:
    """Upsert a file-object embedding into ``mh_objects``.

    Only text/code objects are embedded (binary blobs are skipped).
    """
    try:
        from qdrant_client.models import PointStruct
        text = f"{path} {getattr(obj, 'object_id', '')}".strip()
        if not text:
            return
        vector = await _embed_text(text)
        if vector is None:
            return
        point_id = _sha_to_uint64(obj.object_id)
        await qdrant.upsert(
            collection_name=COLLECTION_OBJECTS,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "object_id": obj.object_id,
                    "repo_id": obj.repo_id,
                    "path": path,
                },
            )],
        )
    except Exception as exc:
        logger.warning("embed_object failed for %s: %s", getattr(obj, "object_id", "?"), exc)


async def semantic_search_repos(
    qdrant: Any,
    query: str,
    limit: int = 10,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    """Search repos by natural-language query.

    Returns a list of payload dicts with ``repo_id``, ``owner``, ``slug``.
    """
    try:
        vector = await _embed_text(query)
        if vector is None:
            return []
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        query_filter = None
        if domain:
            query_filter = Filter(
                must=[FieldCondition(key="domain", match=MatchValue(value=domain))]
            )
        results = await qdrant.search(
            collection_name=COLLECTION_REPOS,
            query_vector=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        return [r.payload for r in results]
    except Exception as exc:
        logger.warning("semantic_search_repos failed: %s", exc)
        return []


async def semantic_search_commits(
    qdrant: Any,
    query: str,
    repo_id: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search commits by natural-language query."""
    try:
        vector = await _embed_text(query)
        if vector is None:
            return []
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        query_filter = None
        if repo_id:
            query_filter = Filter(
                must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
            )
        results = await qdrant.search(
            collection_name=COLLECTION_COMMITS,
            query_vector=vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True,
        )
        return [r.payload for r in results]
    except Exception as exc:
        logger.warning("semantic_search_commits failed: %s", exc)
        return []

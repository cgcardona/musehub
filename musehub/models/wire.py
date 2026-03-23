"""Wire protocol Pydantic models — Muse CLI native format.

These models match the Muse CLI ``HttpTransport`` wire format exactly.
All fields are snake_case to match Muse's internal CommitDict/SnapshotDict/
ObjectPayload TypedDicts.

The wire protocol is intentionally separate from the REST API's CamelModel:
    Wire protocol  /wire/repos/{repo_id}/   ← Muse CLI speaks here
    REST API       /api/repos/{id}/          ← agents and integrations speak here
    MCP            /mcp                      ← agents speak here too

Denial-of-Service limits
------------------------
All list fields that arrive over the network are capped so a single large
request cannot exhaust memory or DB connections:

  MAX_COMMITS_PER_PUSH  = 1 000   — one push should carry at most 1k commits
  MAX_OBJECTS_PER_PUSH  = 1 000   — ditto for binary blobs
  MAX_SNAPSHOTS_PER_PUSH = 1 000  — ditto for snapshot manifests
  MAX_WANT_PER_FETCH    = 1 000   — fetch want/have lists
  MAX_B64_SIZE          = 52_000_000 — ~38 MB decoded (base64 overhead ≈1.37×)
                                     single-object cap; 100 MB objects must
                                     use direct S3/R2 upload instead.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Per-request DoS limits (enforced via Pydantic max_length) ───────────────
#
# Objects are the large-payload risk: each blob can be up to ~38 MB decoded
# (MAX_B64_SIZE).  Keeping MAX_OBJECTS_PER_PUSH at 1 000 bounds a single
# push to ≤ 38 GB in the worst case; the client chunks large pushes and
# pre-uploads blobs via POST /push/objects before the final commit push.
#
# Commits and snapshots are inherently small (< 2 KB each after JSON
# serialisation). A full 10 000-commit history is typically < 20 MB total —
# well within a single request.  Setting a 1 000-item cap here would block
# legitimate large initial pushes without any real security benefit, so we
# allow up to 10 000 items and rely on the HTTP body-size cap (uvicorn's
# max_request_body_size, default 1 GiB) for DoS protection.
MAX_COMMITS_PER_PUSH: int = 10_000
MAX_OBJECTS_PER_PUSH: int = 1_000
MAX_SNAPSHOTS_PER_PUSH: int = 10_000
MAX_WANT_PER_FETCH: int = 1_000
# Base64 string length limit — base64 expands by ~1.37×, so 52 MB b64 ≈ 38 MB raw.
MAX_B64_SIZE: int = 52_000_000


class WireCommit(BaseModel):
    """Muse native commit record — mirrors CommitDict from muse.core.store."""

    commit_id: str
    repo_id: str = ""
    branch: str = ""
    snapshot_id: str | None = None
    message: str = ""
    committed_at: str = ""               # ISO-8601 UTC string
    parent_commit_id: str | None = None  # first parent (linear history)
    parent2_commit_id: str | None = None # second parent (merge commits)
    author: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)
    structured_delta: Any = None         # domain-specific delta blob
    sem_ver_bump: str = "none"           # "none" | "patch" | "minor" | "major"
    breaking_changes: list[str] = Field(default_factory=list)
    agent_id: str = ""
    model_id: str = ""
    toolchain_id: str = ""
    prompt_hash: str = ""
    signature: str = ""
    signer_key_id: str = ""
    format_version: int = 1
    reviewed_by: list[str] = Field(default_factory=list)
    test_runs: int = 0

    model_config = {"extra": "ignore"}   # tolerate future Muse fields gracefully


class WireSnapshot(BaseModel):
    """Muse native snapshot — mirrors SnapshotDict from muse.core.store.

    The manifest maps file paths to content-addressed object IDs,
    e.g. ``{"muse/core/pack.py": "sha256:abc123..."}``.
    """

    snapshot_id: str
    # max_length caps the number of manifest entries — a 10 000-file snapshot
    # would already be pathologically large; prevent unbounded dict parsing.
    manifest: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    created_at: str = ""

    model_config = {"extra": "ignore"}


class WireObject(BaseModel):
    """Content-addressed object payload — mirrors ObjectPayload from muse.core.pack."""

    object_id: str
    content_b64: str = Field(max_length=MAX_B64_SIZE)
    # path is not in the Muse CLI ObjectPayload TypedDict but we accept it when present
    path: str = Field(default="", max_length=4096)

    model_config = {"extra": "ignore"}

    @field_validator("content_b64")
    @classmethod
    def _check_b64_size(cls, v: str) -> str:
        """Reject oversized objects before attempting base64 decode.

        Checking ``len(v)`` is O(1) on CPython (str stores its length) and
        prevents the memory spike that would occur when decoding a multi-GB
        string into bytes.
        """
        if len(v) > MAX_B64_SIZE:
            raise ValueError(
                f"content_b64 exceeds maximum size ({MAX_B64_SIZE} chars). "
                "Upload large objects directly to S3/R2 instead."
            )
        return v


class WireBundle(BaseModel):
    """A pack bundle sent in a push request.

    Mirrors PackBundle from muse.core.pack.  All fields are optional because
    a minimal push may only contain commits (no new objects).

    List lengths are capped to prevent DoS via an oversized single request.
    See the module-level ``MAX_*`` constants for the exact limits.
    """

    commits: list[WireCommit] = Field(default_factory=list, max_length=MAX_COMMITS_PER_PUSH)
    snapshots: list[WireSnapshot] = Field(default_factory=list, max_length=MAX_SNAPSHOTS_PER_PUSH)
    objects: list[WireObject] = Field(default_factory=list, max_length=MAX_OBJECTS_PER_PUSH)
    branch_heads: dict[str, str] = Field(default_factory=dict)


class WirePushRequest(BaseModel):
    """Body for ``POST /wire/repos/{repo_id}/push``.

    Matches the payload built by HttpTransport.push_pack():
        ``{"bundle": {...}, "branch": "main", "force": false}``
    """

    bundle: WireBundle
    branch: str
    force: bool = False


class WireFetchRequest(BaseModel):
    """Body for ``POST /wire/repos/{repo_id}/fetch``.

    Matches HttpTransport.fetch_pack() payload:
        ``{"want": [...sha...], "have": [...sha...]}``

    ``want`` — commit SHAs the client wants.
    ``have`` — commit SHAs the client already has (exclusion list).
    """

    want: list[str] = Field(default_factory=list, max_length=MAX_WANT_PER_FETCH)
    have: list[str] = Field(default_factory=list, max_length=MAX_WANT_PER_FETCH)


class WireRefsResponse(BaseModel):
    """Response for ``GET /wire/repos/{repo_id}/refs``.

    Parsed by HttpTransport._parse_remote_info() into RemoteInfo.
    """

    repo_id: str
    domain: str
    default_branch: str
    branch_heads: dict[str, str]


class WirePushResponse(BaseModel):
    """Response for ``POST /wire/repos/{repo_id}/push``.

    Parsed by HttpTransport._parse_push_result() into PushResult.
    ``branch_heads`` is what the Muse CLI reads; ``remote_head`` is bonus
    information for MCP consumers.
    """

    ok: bool
    message: str
    branch_heads: dict[str, str]
    remote_head: str = ""


class WireFetchResponse(BaseModel):
    """Response for ``POST /wire/repos/{repo_id}/fetch``.

    Parsed by HttpTransport._parse_bundle() into PackBundle.
    """

    commits: list[WireCommit] = Field(default_factory=list)
    snapshots: list[WireSnapshot] = Field(default_factory=list)
    objects: list[WireObject] = Field(default_factory=list)
    branch_heads: dict[str, str] = Field(default_factory=dict)


class WireObjectsRequest(BaseModel):
    """Body for ``POST /{owner}/{slug}/push/objects`` — chunked object pre-upload.

    Clients split large pushes into multiple calls to this endpoint before
    calling ``POST /{owner}/{slug}/push`` with an empty objects list.
    Objects are content-addressed (SHA-256) so uploading the same object
    twice is always safe — the server skips objects it already holds.
    """

    objects: list[WireObject] = Field(default_factory=list, max_length=MAX_OBJECTS_PER_PUSH)


class WireObjectsResponse(BaseModel):
    """Response for ``POST /{owner}/{slug}/push/objects``."""

    stored: int   # objects written to storage this call
    skipped: int  # objects already present (idempotent no-op)

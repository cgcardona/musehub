"""Wire protocol Pydantic models — Muse CLI native format (MWP — Muse Wire Protocol).

These models match the Muse CLI ``HttpTransport`` wire format exactly.
All fields are snake_case to match Muse's internal CommitDict/SnapshotDict/
ObjectPayload TypedDicts.

The wire protocol is intentionally separate from the REST API's CamelModel:
    Wire protocol  /wire/repos/{repo_id}/   ← Muse CLI speaks here (MWP, msgpack)
    REST API       /api/repos/{id}/          ← agents and integrations speak here
    MCP            /mcp                      ← agents speak here too

Encoding
--------
All wire endpoints accept and return ``application/x-msgpack`` binary.
Objects are transported as raw ``bytes`` under the ``content`` key — no
base64 encoding overhead.

Denial-of-Service limits
------------------------
All list fields that arrive over the network are capped so a single large
request cannot exhaust memory or DB connections:

  MAX_COMMITS_PER_PUSH   = 10 000  — one push should carry at most 10k commits
  MAX_OBJECTS_PER_PUSH   =  1 000  — ditto for binary blobs per chunk
  MAX_SNAPSHOTS_PER_PUSH = 10 000  — ditto for snapshot manifests
  MAX_WANT_PER_FETCH     =  1 000  — fetch want/have lists
  MAX_OBJECT_BYTES       = 38_000_000 — ~38 MB raw; larger objects use presigned URLs
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Per-request DoS limits ────────────────────────────────────────────────────
MAX_COMMITS_PER_PUSH: int = 10_000
MAX_OBJECTS_PER_PUSH: int = 1_000
MAX_SNAPSHOTS_PER_PUSH: int = 10_000
MAX_WANT_PER_FETCH: int = 1_000
# Raw bytes limit per object — objects above this must use presigned URL upload.
MAX_OBJECT_BYTES: int = 38_000_000


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
    """Content-addressed object payload — mirrors ObjectPayload from muse.core.pack.

    MWP encodes ``content`` as raw bytes (msgpack bin type) — no base64 overhead.
    """

    object_id: str
    content: bytes = Field(max_length=MAX_OBJECT_BYTES)
    path: str = Field(default="", max_length=4096)

    model_config = {"extra": "ignore"}

    @field_validator("content")
    @classmethod
    def _check_content_size(cls, v: bytes) -> bytes:
        if len(v) > MAX_OBJECT_BYTES:
            raise ValueError(
                f"content exceeds maximum size ({MAX_OBJECT_BYTES} bytes). "
                "Upload large objects directly via presigned URL instead."
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


# ── MWP/2 — Phase 1: object-level deduplication ──────────────────────────────


class WireFilterRequest(BaseModel):
    """Body for ``POST /{owner}/{slug}/filter-objects``.

    Client sends the full list of object IDs it intends to push; server
    responds with only the subset the remote does NOT already hold.
    The client then uploads only the missing objects, skipping anything
    the server already has (by prior push, shared history, etc.).

    This is the single highest-impact change in MWP/2: an incremental push
    that changes two files in a 10 000-object repo sends two objects, not
    10 000.
    """

    object_ids: list[str] = Field(default_factory=list, max_length=50_000)


class WireFilterResponse(BaseModel):
    """Response for ``POST /{owner}/{slug}/filter-objects``."""

    missing: list[str]   # subset of object_ids the remote does NOT have


# ── MWP/2 — Phase 3: presigned object storage URLs ───────────────────────────


class WirePresignRequest(BaseModel):
    """Body for ``POST /{owner}/{slug}/presign``.

    For large objects (> 64 KB), the client requests presigned PUT URLs and
    uploads directly to object storage, bypassing the API server entirely.
    For the local ``local://`` backend the server returns an empty
    ``presigned`` dict and lists all IDs in ``inline`` — the client then
    sends those through the normal pack flow.

    ``direction`` — ``"put"`` for push, ``"get"`` for pull/fetch.
    ``ttl_seconds`` — URL lifetime; capped at 3 600 s (1 hour).
    """

    object_ids: list[str] = Field(default_factory=list, max_length=10_000)
    direction: str = "put"   # "put" | "get"
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class WirePresignResponse(BaseModel):
    """Response for ``POST /{owner}/{slug}/presign``."""

    presigned: dict[str, str] = Field(default_factory=dict)
    # object_ids whose backend does not support presigned URLs (local://);
    # client must include these in the normal pack body instead.
    inline: list[str] = Field(default_factory=list)


# ── MWP/2 — Phase 5: depth-limited commit negotiation ────────────────────────


class WireNegotiateRequest(BaseModel):
    """Body for ``POST /{owner}/{slug}/negotiate``.

    Multi-round ACK/NAK protocol (analogous to Git pack-protocol v2).  The
    client sends the branch tips it *wants* and a depth-limited list of
    commits it already *has* (≤ 256 per round).  The server responds with
    which ``have`` commits it recognises (``ack``) and whether it has enough
    information to compute the delta (``ready``).

    When ``ready`` is False the client walks back another ``NEGOTIATE_DEPTH``
    ancestors and calls this endpoint again, narrowing toward the common base
    without ever sending the full commit history.
    """

    want: list[str] = Field(default_factory=list, max_length=256)
    have: list[str] = Field(default_factory=list, max_length=256)


class WireNegotiateResponse(BaseModel):
    """Response for ``POST /{owner}/{slug}/negotiate``."""

    ack: list[str]              # have-IDs the server recognises
    common_base: str | None     # deepest shared ancestor found, if any
    ready: bool                 # True → client has enough info to build pack

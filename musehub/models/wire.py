"""Wire protocol Pydantic models — Muse CLI native format.

These models match the Muse CLI ``HttpTransport`` wire format exactly.
All fields are snake_case to match Muse's internal CommitDict/SnapshotDict/
ObjectPayload TypedDicts.

The wire protocol is intentionally separate from the REST API's CamelModel:
    Wire protocol  /wire/repos/{repo_id}/   ← Muse CLI speaks here
    REST API       /api/repos/{id}/          ← agents and integrations speak here
    MCP            /mcp                      ← agents speak here too
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    manifest: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""

    model_config = {"extra": "ignore"}


class WireObject(BaseModel):
    """Content-addressed object payload — mirrors ObjectPayload from muse.core.pack."""

    object_id: str
    content_b64: str
    # path is not in the Muse CLI ObjectPayload TypedDict but we accept it when present
    path: str = ""

    model_config = {"extra": "ignore"}


class WireBundle(BaseModel):
    """A pack bundle sent in a push request.

    Mirrors PackBundle from muse.core.pack.  All fields are optional because
    a minimal push may only contain commits (no new objects).
    """

    commits: list[WireCommit] = Field(default_factory=list)
    snapshots: list[WireSnapshot] = Field(default_factory=list)
    objects: list[WireObject] = Field(default_factory=list)
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

    want: list[str] = Field(default_factory=list)
    have: list[str] = Field(default_factory=list)


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

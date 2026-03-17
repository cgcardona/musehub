# Muse Hub — Type Contracts Reference

> Updated: 2026-03-17 | Covers every named entity in the Muse Hub surface:
> MIDI type aliases, JSON wire types, MCP protocol types, Pydantic API models,
> auth tokens, SSE event hierarchy, SQLAlchemy ORM models.
> `Any` and bare `list` / `dict` (without type arguments) do not appear in any
> production file. Every type boundary is named. The mypy strict ratchet
> enforces zero violations on every CI run across 111 source files.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [MIDI Type Aliases (`contracts/midi_types.py`)](#midi-type-aliases)
3. [JSON Type Aliases (`contracts/json_types.py`)](#json-type-aliases)
4. [JSON Wire TypedDicts (`contracts/json_types.py`)](#json-wire-typeddicts)
5. [MCP Protocol Types (`contracts/mcp_types.py`)](#mcp-protocol-types)
6. [Pydantic Base Types (`contracts/pydantic_types.py`, `models/base.py`)](#pydantic-base-types)
7. [Auth Types (`auth/tokens.py`)](#auth-types)
8. [Protocol Events (`protocol/events.py`)](#protocol-events)
9. [Protocol HTTP Responses (`protocol/responses.py`)](#protocol-http-responses)
10. [API Models (`models/musehub.py`)](#api-models)
11. [Database ORM Models (`db/`)](#database-orm-models)
12. [Entity Hierarchy](#entity-hierarchy)
13. [Entity Graphs (Mermaid)](#entity-graphs-mermaid)

---

## Design Philosophy

Every entity in this codebase follows five rules:

1. **No `Any`. No bare `object`. Ever.** Both collapse type safety for downstream
   callers. Every boundary is typed with a concrete named entity — `TypedDict`,
   `dataclass`, Pydantic model, or a specific union. The CI mypy strict ratchet
   enforces zero violations.

2. **No covariance in collection aliases.** `dict[str, str]` and `list[str]`
   are used directly. If a return mixes value types, a `TypedDict` names that
   shape instead of a `dict[str, str | int]`.

3. **Boundaries own coercion.** When external data arrives (JSON over HTTP,
   bytes from the database, MIDI off the wire), the boundary module coerces to
   the canonical internal type. Downstream code always sees clean types.

4. **Wire-format TypedDicts for JSON serialisation, Pydantic models for HTTP.**
   `TokenClaims`, `NoteDict`, `MCPRequest` etc. are JSON-serialisable and
   used at IO boundaries. Pydantic `CamelModel` subclasses are used for all
   FastAPI route return types and request bodies.

5. **No `# type: ignore`. Fix the underlying error instead.** The one designated
   exception is the `json_list()` coercion boundary — a single
   `type: ignore[arg-type]` inside the implementation body of that helper.

### Banned → Use instead

| Banned | Use instead |
|--------|-------------|
| `Any` | `TypedDict`, `dataclass`, specific union |
| `object` | The actual type or a constrained union |
| `list` (bare) | `list[X]` with concrete element type |
| `dict` (bare) | `dict[K, V]` with concrete key/value types |
| `dict[str, X]` with known keys | `TypedDict` — name the keys |
| `Optional[X]` | `X \| None` |
| Legacy `List`, `Dict`, `Set`, `Tuple` | Lowercase builtins |
| `Union[A, B]` | `A \| B` |
| `Type[X]` | `type[X]` |
| `cast(T, x)` | Fix the callee to return `T` |
| `# type: ignore` | Fix the underlying type error |

---

## MIDI Type Aliases

**Path:** `musehub/contracts/midi_types.py`

Constrained `int` and `float` aliases via `Annotated[int, Field(...)]`.
Every MIDI boundary uses these instead of bare `int` so that range constraints
are part of the type signature and enforced by Pydantic at validation time.

| Alias | Base | Constraint | Description |
|-------|------|------------|-------------|
| `MidiPitch` | `int` | 0–127 | MIDI note number (C-1=0, Middle C=60, G9=127) |
| `MidiVelocity` | `int` | 0–127 | Note velocity; 0=note-off, 1–127=audible |
| `MidiChannel` | `int` | 0–15 | Zero-indexed MIDI channel; drums=9 |
| `MidiCC` | `int` | 0–127 | MIDI Control Change controller number |
| `MidiCCValue` | `int` | 0–127 | MIDI Control Change value |
| `MidiAftertouchValue` | `int` | 0–127 | Channel or poly aftertouch pressure |
| `MidiGMProgram` | `int` | 0–127 | General MIDI program / patch number (0-indexed) |
| `MidiPitchBend` | `int` | −8192–8191 | 14-bit signed pitch bend; 0=centre |
| `MidiBPM` | `int` | 20–300 | Tempo in beats per minute (always integer) |
| `BeatPosition` | `float` | ≥ 0.0 | Absolute beat position; fractional allowed |
| `BeatDuration` | `float` | > 0.0 | Duration in beats; must be strictly positive |
| `ArrangementBeat` | `int` | ≥ 0 | Bar-aligned beat offset for section-level timing |
| `ArrangementDuration` | `int` | ≥ 1 | Section duration in beats (bars × numerator) |
| `Bars` | `int` | ≥ 1 | Bar count; always a positive integer |

---

## JSON Type Aliases

**Path:** `musehub/contracts/json_types.py`

Type aliases for recursive and domain-specific JSON shapes.

| Alias | Definition | Description |
|-------|-----------|-------------|
| `JSONScalar` | `str \| int \| float \| bool \| None` | A JSON leaf value with no recursive structure |
| `JSONValue` | `str \| int \| float \| bool \| None \| list["JSONValue"] \| dict[str, "JSONValue"]` | Recursive JSON value — use sparingly, never in Pydantic models |
| `JSONObject` | `dict[str, JSONValue]` | A JSON object with an unknown key set |
| `InternalNoteDict` | `NoteDict` | Alias for `NoteDict` on the snake_case storage path |
| `RegionNotesMap` | `dict[str, list[NoteDict]]` | Maps `region_id` → ordered list of MIDI notes |
| `RegionCCMap` | `dict[str, list[CCEventDict]]` | Maps `region_id` → ordered list of MIDI CC events |
| `RegionPitchBendMap` | `dict[str, list[PitchBendDict]]` | Maps `region_id` → ordered list of MIDI pitch bend events |
| `RegionAftertouchMap` | `dict[str, list[AftertouchDict]]` | Maps `region_id` → ordered list of MIDI aftertouch events |
| `EventJsonSchema` | `dict[str, JSONValue]` | JSON Schema dict for a single event type, as produced by `model_json_schema()` |
| `EventSchemaMap` | `dict[str, EventJsonSchema]` | Maps `event_type` → its JSON Schema; returned by `/protocol/events.json` |

---

## JSON Wire TypedDicts

**Path:** `musehub/contracts/json_types.py`

These are the MIDI note and event shapes exchanged across service boundaries.
All use `total=False` where the producer may omit fields, and `Required[T]`
to mark fields that must always be present.

### `NoteDict`

`TypedDict (total=False)` — A single MIDI note. Accepts both camelCase (wire
format) and snake_case (internal storage) to avoid a transform boundary.

| Field | Type | Description |
|-------|------|-------------|
| `pitch` | `MidiPitch` | MIDI pitch number |
| `velocity` | `MidiVelocity` | Note velocity |
| `channel` | `MidiChannel` | MIDI channel |
| `startBeat` | `BeatPosition` | Onset beat (camelCase wire) |
| `durationBeats` | `BeatDuration` | Duration in beats (camelCase wire) |
| `noteId` | `str` | Note UUID (camelCase wire) |
| `trackId` | `str` | Parent track UUID (camelCase wire) |
| `regionId` | `str` | Parent region UUID (camelCase wire) |
| `start_beat` | `BeatPosition` | Onset beat (snake_case storage) |
| `duration_beats` | `BeatDuration` | Duration in beats (snake_case storage) |
| `note_id` | `str` | Note UUID (snake_case storage) |
| `track_id` | `str` | Parent track UUID (snake_case storage) |
| `region_id` | `str` | Parent region UUID (snake_case storage) |
| `layer` | `str` | Optional layer grouping (e.g. `"melody"`) |

### `CCEventDict`

`TypedDict` — A single MIDI Control Change event.

| Field | Type |
|-------|------|
| `cc` | `MidiCC` |
| `beat` | `BeatPosition` |
| `value` | `MidiCCValue` |

### `PitchBendDict`

`TypedDict` — A single MIDI pitch bend event.

| Field | Type |
|-------|------|
| `beat` | `BeatPosition` |
| `value` | `MidiPitchBend` |

### `AftertouchDict`

`TypedDict (total=False)` — MIDI aftertouch (channel or poly).

| Field | Type | Required |
|-------|------|----------|
| `beat` | `BeatPosition` | Yes |
| `value` | `MidiAftertouchValue` | Yes |
| `pitch` | `MidiPitch` | No (poly only) |

### `SectionDict`

`TypedDict (total=False)` — A composition section (verse, chorus, bridge, etc.).
Used by the analysis service to describe structural section metadata.

| Field | Type |
|-------|------|
| `name` | `str` |
| `start_beat` | `float` |
| `length_beats` | `float` |
| `description` | `str` |
| `per_track_description` | `dict[str, str]` |

### Conversion helpers

| Function | Signature | Description |
|----------|-----------|-------------|
| `is_note_dict(v)` | `(JSONValue) -> TypeGuard[NoteDict]` | Narrows `JSONValue` to `NoteDict` in list comprehensions |
| `jfloat(v, default)` | `(JSONValue, float) -> float` | Safe float extraction from `JSONValue` |
| `jint(v, default)` | `(JSONValue, int) -> int` | Safe int extraction from `JSONValue` |
| `json_list(items)` | overloaded | Coerces a `list[TypedDict]` to `list[JSONValue]` at insertion boundaries |

---

## MCP Protocol Types

**Path:** `musehub/contracts/mcp_types.py`

Typed shapes for the Model Context Protocol JSON-RPC 2.0 interface. TypedDicts
cover the wire format; Pydantic models (`MCPToolDefWire` etc.) are used for
FastAPI response serialisation.

### Type Aliases

| Alias | Definition |
|-------|-----------|
| `MCPResponse` | `MCPSuccessResponse \| MCPErrorResponse` |
| `MCPMethodResponse` | `MCPInitializeResponse \| MCPToolsListResponse \| MCPCallResponse \| MCPSuccessResponse \| MCPErrorResponse` |

### Request / Response TypedDicts

| Name | Kind | Description |
|------|------|-------------|
| `MCPRequest` | `total=False` | Incoming JSON-RPC 2.0 message from an MCP client |
| `MCPSuccessResponse` | required | JSON-RPC 2.0 success response |
| `MCPErrorDetail` | `total=False` | The `error` object inside a JSON-RPC error response |
| `MCPErrorResponse` | required | JSON-RPC 2.0 error response |
| `MCPInitializeParams` | `total=False` | Params for the `initialize` method |
| `MCPInitializeResult` | required | Result body for `initialize` |
| `MCPInitializeResponse` | required | Full response for `initialize` |
| `MCPToolsListResult` | required | Result body for `tools/list` |
| `MCPToolsListResponse` | required | Full response for `tools/list` |
| `MCPCallResult` | `total=False` | Result body for `tools/call` |
| `MCPCallResponse` | required | Full response for `tools/call` |

### Tool Definition TypedDicts

| Name | Kind | Description |
|------|------|-------------|
| `MCPPropertyDef` | `total=False` | JSON Schema definition for a single tool property |
| `MCPInputSchema` | `total=False` | JSON Schema for a tool's accepted arguments |
| `MCPToolDef` | `total=False` | Complete definition of an MCP tool |
| `MCPContentBlock` | required | Content block in a tool result (`type`, `text`) |

### Capability TypedDicts

| Name | Kind | Description |
|------|------|-------------|
| `MCPToolsCapability` | `total=False` | `tools` entry in `MCPCapabilities` |
| `MCPResourcesCapability` | `total=False` | `resources` entry in `MCPCapabilities` |
| `MCPCapabilities` | `total=False` | Server capabilities advertised during `initialize` |
| `MCPServerInfo` | required | Server info returned in `initialize` responses |
| `MCPCapabilitiesResult` | required | Capability block in `initialize` result |
| `MCPToolCallParams` | required | Params for `tools/call` |

### DAW ↔ MCP Bridge TypedDicts

| Name | Kind | Description |
|------|------|-------------|
| `DAWToolCallMessage` | required | Message sent from MCP server to a DAW client over WebSocket |
| `DAWToolResponse` | `total=False` | Response sent from the DAW back after tool execution |

### Pydantic Wire Models (FastAPI)

| Name | Description |
|------|-------------|
| `MCPPropertyDefWire` | Pydantic-safe JSON Schema property for FastAPI responses |
| `MCPInputSchemaWire` | Pydantic-safe tool input schema for FastAPI responses |
| `MCPToolDefWire` | Pydantic-safe tool definition for FastAPI route return types |

---

## Pydantic Base Types

**Path:** `musehub/contracts/pydantic_types.py`, `musehub/models/base.py`

### `PydanticJson`

`RootModel[str | int | float | bool | None | list["PydanticJson"] | dict[str, "PydanticJson"]]`

The only safe recursive JSON field type for Pydantic models. Used wherever
a model field accepts an arbitrary JSON value (e.g. tool call parameters or
protocol introspection schemas). Replaces `dict[str, Any]` at every Pydantic
boundary.

**Helpers:**

| Function | Description |
|----------|-------------|
| `wrap(v: JSONValue) -> PydanticJson` | Convert a `JSONValue` to a `PydanticJson` instance |
| `unwrap(p: PydanticJson) -> JSONValue` | Convert a `PydanticJson` back to a `JSONValue` |
| `wrap_dict(d: dict[str, JSONValue]) -> dict[str, PydanticJson]` | Wrap each value in a dict |

### `CamelModel`

`BaseModel` subclass. All Pydantic API models (request bodies and response
types) inherit from this. Configures:

- `alias_generator = to_camel` — fields are serialised to camelCase on the wire.
- `populate_by_name = True` — allows snake_case names in Python code.
- `extra = "ignore"` — unknown fields from clients are silently dropped.

---

## Auth Types

**Path:** `musehub/auth/tokens.py`

### `TokenClaims`

`TypedDict (total=False)` — Decoded JWT payload returned by `validate_access_code`.
`type`, `iat`, and `exp` are always present (`Required`); `sub` and `role` are
optional claims added by the issuer.

| Field | Type | Required |
|-------|------|----------|
| `type` | `str` | Yes |
| `iat` | `int` | Yes |
| `exp` | `int` | Yes |
| `sub` | `str` | No |
| `role` | `str` | No |

---

## Protocol Events

**Path:** `musehub/protocol/events.py`

Protocol events are Pydantic `CamelModel` subclasses of `MuseEvent`, which
provides `type`, `seq`, and `protocol_version` on every payload. Muse Hub
defines two concrete event types — both in the MCP relay path.

### Base Class

| Name | Kind | Description |
|------|------|-------------|
| `MuseEvent` | Pydantic (CamelModel) | Base class: `type: str`, `seq: int = -1`, `protocol_version: str` |

### Concrete Event Types

| Event | `type` Literal | Description |
|-------|---------------|-------------|
| `MCPMessageEvent` | `"mcp.message"` | MCP tool-call message relayed over SSE; `payload: dict[str, object]` |
| `MCPPingEvent` | `"mcp.ping"` | MCP SSE keepalive heartbeat |

The event registry (`protocol/registry.py`) maps these two type strings to
their model classes and is frozen at import time.

---

## Protocol HTTP Responses

**Path:** `musehub/protocol/responses.py`

Pydantic response models for the four protocol introspection endpoints.
Fields use camelCase by declaration to match the wire format.

| Name | Route | Description |
|------|-------|-------------|
| `ProtocolInfoResponse` | `GET /protocol` | Version, hash, and registered event type list |
| `ProtocolEventsResponse` | `GET /protocol/events.json` | JSON Schema per event type |
| `ProtocolToolsResponse` | `GET /protocol/tools.json` | All registered MCP tool definitions |
| `ProtocolSchemaResponse` | `GET /protocol/schema.json` | Unified snapshot — version + hash + events + tools |

The protocol hash (`protocol/hash.py`) is a SHA-256 over the serialised event
schemas and tool schemas, computed deterministically at request time.

---

## API Models

**Path:** `musehub/models/musehub.py`

All are Pydantic `CamelModel` subclasses. Organized by domain feature.

### Git / VCS

| Name | Description |
|------|-------------|
| `CommitInput` | A single commit in a push payload |
| `ObjectInput` | A binary object in a push payload |
| `PushRequest` | Body for `POST /repos/{id}/push` |
| `PushResponse` | Push confirmation with new branch head |
| `PullRequest` | Body for `POST /repos/{id}/pull` |
| `ObjectResponse` | Binary object returned in a pull response |
| `PullResponse` | Pull response — missing commits and objects |

### Repositories

| Name | Description |
|------|-------------|
| `CreateRepoRequest` | Repository creation wizard body |
| `RepoResponse` | Wire representation of a Muse Hub repo |
| `TransferOwnershipRequest` | Transfer repo to another user |
| `RepoListResponse` | Paginated list of repos |
| `RepoStatsResponse` | Aggregated commit / branch / release counts |

### Branches

| Name | Description |
|------|-------------|
| `BranchResponse` | Branch name and head commit pointer |
| `BranchListResponse` | Paginated list of branches |
| `BranchDivergenceScores` | Five-dimensional musical divergence scores |
| `BranchDetailResponse` | Branch with ahead/behind counts and divergence |
| `BranchDetailListResponse` | List of branches with detail |

### Commits and Tags

| Name | Description |
|------|-------------|
| `CommitResponse` | Wire representation of a pushed commit |
| `CommitListResponse` | Paginated list of commits |
| `TagResponse` | A single tag entry |
| `TagListResponse` | All tags grouped by namespace |

### Issues

| Name | Description |
|------|-------------|
| `IssueCreate` | Create issue body |
| `IssueUpdate` | Partial update body |
| `IssueResponse` | Wire representation of an issue |
| `IssueListResponse` | Paginated list of issues |
| `MusicalRef` | Parsed musical context reference (e.g. `track:bass`) |
| `IssueCommentCreate` | Create comment body |
| `IssueCommentResponse` | Wire representation of a comment |
| `IssueCommentListResponse` | Threaded discussion on an issue |
| `IssueAssignRequest` | Assign or unassign a user |
| `IssueLabelAssignRequest` | Replace the label list on an issue |

### Milestones

| Name | Description |
|------|-------------|
| `MilestoneCreate` | Create milestone body |
| `MilestoneResponse` | Wire representation of a milestone |
| `MilestoneListResponse` | List of milestones |

### Pull Requests

| Name | Description |
|------|-------------|
| `PRCreate` | Create PR body |
| `PRResponse` | Wire representation of a pull request |
| `PRListResponse` | Paginated list of pull requests |
| `PRMergeRequest` | Merge strategy selection body |
| `PRMergeResponse` | Merge confirmation |
| `PRDiffDimensionScore` | Per-dimension musical change score |
| `PRDiffResponse` | Musical diff between PR branches |
| `PRCommentCreate` | PR review comment body (supports four targeting granularities) |
| `PRCommentResponse` | Wire representation of a PR review comment |
| `PRCommentListResponse` | Threaded list of PR comments |
| `PRReviewerRequest` | Request reviewers |
| `PRReviewCreate` | Submit a formal review (approve / request_changes / comment) |
| `PRReviewResponse` | Wire representation of a review |
| `PRReviewListResponse` | List of reviews for a PR |

### Releases

| Name | Description |
|------|-------------|
| `ReleaseCreate` | Create release body |
| `ReleaseDownloadUrls` | Structured download package URLs |
| `ReleaseResponse` | Wire representation of a release |
| `ReleaseListResponse` | List of releases |
| `ReleaseAssetCreate` | Attach asset to release |
| `ReleaseAssetResponse` | Wire representation of an asset |
| `ReleaseAssetListResponse` | Assets for a release |
| `ReleaseAssetDownloadCount` | Per-asset download count |
| `ReleaseDownloadStatsResponse` | Download counts for all assets |

### Profile and Social

| Name | Description |
|------|-------------|
| `ProfileUpdateRequest` | Update profile body |
| `ProfileRepoSummary` | Compact repo summary on a profile page |
| `ProfileResponse` | Full wire representation of a user profile |
| `ContributorCredits` | Single contributor's credit record |
| `CreditsResponse` | Full credits roll for a repo |
| `StarResponse` | Star added / removed confirmation |
| `ContributionDay` | One day in the contribution heatmap |

### Discovery and Search

| Name | Description |
|------|-------------|
| `ExploreRepoResult` | Public repo card on the explore page |
| `ExploreResponse` | Paginated discover response |
| `SearchCommitMatch` | Single commit returned by an in-repo search |
| `SearchResponse` | Response for all four in-repo search modes |
| `GlobalSearchCommitMatch` | Commit match in a cross-repo search |
| `GlobalSearchRepoGroup` | All matches for one repo in a cross-repo search |
| `GlobalSearchResult` | Top-level cross-repo search response |

### Timeline, DAG, and Analytics

| Name | Description |
|------|-------------|
| `TimelineCommitEvent` | A commit plotted on the timeline |
| `TimelineEmotionEvent` | Emotion-vector data point on the timeline |
| `TimelineSectionEvent` | Detected section change marker |
| `TimelineTrackEvent` | Track addition or removal event |
| `TimelineResponse` | Chronological musical evolution timeline |
| `DivergenceDimensionResponse` | Per-dimension divergence score |
| `DivergenceResponse` | Full musical divergence report between two branches |
| `CommitDiffDimensionScore` | Per-dimension change score vs parent |
| `CommitDiffSummaryResponse` | Multi-dimensional diff summary |
| `DagNode` | Single commit node in the DAG |
| `DagEdge` | Directed edge in the commit DAG |
| `DagGraphResponse` | Topologically sorted commit graph |

### Webhooks

| Name | Description |
|------|-------------|
| `WebhookCreate` | Create webhook body |
| `WebhookResponse` | Wire representation of a webhook |
| `WebhookListResponse` | List of webhooks |
| `WebhookDeliveryResponse` | Single delivery attempt |
| `WebhookDeliveryListResponse` | Delivery history |
| `WebhookRedeliverResponse` | Redeliver confirmation |
| `PushEventPayload` | TypedDict — push event webhook payload |
| `IssueEventPayload` | TypedDict — issue event webhook payload |
| `PullRequestEventPayload` | TypedDict (total=False) — PR event webhook payload |
| `WebhookEventPayload` | TypeAlias — `PushEventPayload \| IssueEventPayload \| PullRequestEventPayload` |

### Context

| Name | Description |
|------|-------------|
| `MuseHubContextCommitInfo` | Minimal commit metadata in a context document |
| `MuseHubContextHistoryEntry` | Ancestor commit in evolutionary history |
| `MuseHubContextMusicalState` | Musical state at the target commit |
| `MuseHubContextResponse` | Full context document for a commit |

### Objects

| Name | Description |
|------|-------------|
| `ObjectMetaResponse` | Artifact metadata (no content) |
| `ObjectMetaListResponse` | List of artifact metadata |

---

## Database ORM Models

**Path:** `musehub/db/`

All are SQLAlchemy ORM subclasses of a declarative `Base`.

### `db/models.py` — Auth

| Model | Table | Description |
|-------|-------|-------------|
| `User` | `muse_users` | User account; `id` = JWT `sub` claim |
| `AccessToken` | `muse_access_tokens` | JWT token tracking — stores SHA-256 hash, never the raw token |

### `db/muse_cli_models.py` — Muse CLI VCS

| Model | Table | Description |
|-------|-------|-------------|
| `MuseCliObject` | `muse_objects` | Content-addressed blob |
| `MuseCliSnapshot` | `muse_snapshots` | Immutable snapshot manifest |
| `MuseCliCommit` | `muse_commits` | Versioned commit pointing to a snapshot |
| `MuseCliTag` | `muse_tags` | Music-semantic tag on a CLI commit |

### `db/musehub_models.py` — Muse Hub Core

| Model | Table | Description |
|-------|-------|-------------|
| `MusehubRepo` | `musehub_repos` | Remote repository with music-semantic metadata |
| `MusehubBranch` | `musehub_branches` | Named branch pointer |
| `MusehubCommit` | `musehub_commits` | Commit pushed to Muse Hub |
| `MusehubObject` | `musehub_objects` | Content-addressed binary artifact |
| `MusehubMilestone` | `musehub_milestones` | Milestone grouping issues |
| `MusehubIssueMilestone` | `musehub_issue_milestones` | Issue ↔ Milestone join table |
| `MusehubIssue` | `musehub_issues` | Issue opened against a repo |
| `MusehubIssueComment` | `musehub_issue_comments` | Threaded issue comment |
| `MusehubPullRequest` | `musehub_pull_requests` | Pull request |
| `MusehubPRReview` | `musehub_pr_reviews` | Formal PR review submission |
| `MusehubPRComment` | `musehub_pr_comments` | Inline musical diff comment on a PR |
| `MusehubRelease` | `musehub_releases` | Published version release |
| `MusehubReleaseAsset` | `musehub_release_assets` | Downloadable file attachment |
| `MusehubProfile` | `musehub_profiles` | Public user musical portfolio |
| `MusehubWebhook` | `musehub_webhooks` | Registered webhook subscription |
| `MusehubWebhookDelivery` | `musehub_webhook_deliveries` | Single webhook delivery attempt |
| `MusehubStar` | `musehub_stars` | User star on a public repo |
| `MusehubSession` | `musehub_sessions` | Recording session record pushed from the CLI |
| `MusehubComment` | `musehub_comments` | Threaded comment on any repo object |
| `MusehubReaction` | `musehub_reactions` | Emoji reaction on a comment or target |
| `MusehubFollow` | `musehub_follows` | User follows user — social graph |
| `MusehubWatch` | `musehub_watches` | User watches a repo for notifications |
| `MusehubNotification` | `musehub_notifications` | Notification delivered to a user |
| `MusehubFork` | `musehub_forks` | Fork relationship between two repos |
| `MusehubViewEvent` | `musehub_view_events` | Debounced repo view (one row per visitor per day) |
| `MusehubDownloadEvent` | `musehub_download_events` | Artifact export download event |
| `MusehubRenderJob` | `musehub_render_jobs` | Async MP3/piano-roll render job tracking |
| `MusehubEvent` | `musehub_events` | Append-only repo activity event stream |

### `db/musehub_collaborator_models.py`

| Model | Table | Description |
|-------|-------|-------------|
| `MusehubCollaborator` | `musehub_collaborators` | Explicit push/admin access grant for a user on a repo |

### `db/musehub_label_models.py`

| Model | Table | Description |
|-------|-------|-------------|
| `MusehubLabel` | `musehub_labels` | Coloured label tag scoped to a repo |
| `MusehubIssueLabel` | `musehub_issue_labels` | Issue ↔ Label join table |
| `MusehubPRLabel` | `musehub_pr_labels` | PR ↔ Label join table |

### `db/musehub_stash_models.py`

| Model | Table | Description |
|-------|-------|-------------|
| `MusehubStash` | `musehub_stash` | Named save point for uncommitted changes |
| `MusehubStashEntry` | `musehub_stash_entries` | Single MIDI file snapshot within a stash |

---

## Entity Hierarchy

```
Muse Hub
│
├── MIDI Type Aliases (contracts/midi_types.py)
│   ├── MidiPitch, MidiVelocity, MidiChannel, MidiCC, MidiCCValue
│   ├── MidiAftertouchValue, MidiGMProgram, MidiPitchBend, MidiBPM
│   └── BeatPosition, BeatDuration, ArrangementBeat, ArrangementDuration, Bars
│
├── JSON Types (contracts/json_types.py)
│   ├── Primitives: JSONScalar, JSONValue, JSONObject
│   ├── Region maps: RegionNotesMap, RegionCCMap, RegionPitchBendMap, RegionAftertouchMap
│   ├── Protocol aliases: EventJsonSchema, EventSchemaMap
│   └── TypedDicts: NoteDict, CCEventDict, PitchBendDict, AftertouchDict, SectionDict
│
├── MCP Protocol (contracts/mcp_types.py)
│   ├── MCPRequest                  — TypedDict (total=False)
│   ├── MCPResponse                 — MCPSuccessResponse | MCPErrorResponse
│   ├── MCPMethodResponse           — 5-way union of concrete response types
│   ├── MCPToolDef                  — TypedDict (total=False)
│   ├── DAWToolCallMessage          — TypedDict
│   ├── DAWToolResponse             — TypedDict (total=False)
│   └── MCPToolDefWire              — Pydantic (FastAPI serialisation)
│
├── Pydantic Base (contracts/pydantic_types.py, models/base.py)
│   ├── PydanticJson                — RootModel: recursive JSON, safe for Pydantic fields
│   └── CamelModel                  — BaseModel: camelCase alias, populate_by_name, extra=ignore
│
├── Auth (auth/tokens.py)
│   └── TokenClaims                 — TypedDict (total=False): decoded JWT payload
│
├── Protocol Events (protocol/events.py)
│   ├── MuseEvent                   — Pydantic base: type + seq + protocol_version
│   ├── MCPMessageEvent             — type: "mcp.message"; payload: dict[str, object]
│   └── MCPPingEvent                — type: "mcp.ping" (keepalive)
│
├── Protocol Introspection (protocol/)
│   ├── EVENT_REGISTRY              — dict[str, type[MuseEvent]] (2 entries)
│   ├── compute_protocol_hash()     — SHA-256 over events + tools schemas
│   ├── ProtocolInfoResponse        — GET /protocol
│   ├── ProtocolEventsResponse      — GET /protocol/events.json
│   ├── ProtocolToolsResponse       — GET /protocol/tools.json
│   └── ProtocolSchemaResponse      — GET /protocol/schema.json
│
├── MCP Tools (mcp/)
│   ├── MUSEHUB_TOOLS               — 7 read-only browsing tool definitions
│   ├── MUSEHUB_TOOL_NAMES          — frozenset of tool name strings
│   ├── MCP_TOOLS                   — combined list of all registered tools
│   ├── TOOL_CATEGORIES             — dict[str, str] tool → category
│   ├── MuseMCPServer               — routes musehub_* calls to executor
│   └── ToolCallResult              — server routing result (success, is_error, content)
│
├── API Models (models/musehub.py)            ~98 Pydantic models
│   ├── VCS: PushRequest, PullResponse, …
│   ├── Repos: CreateRepoRequest, RepoResponse, …
│   ├── Issues: IssueCreate, IssueResponse, IssueCommentResponse, …
│   ├── Pull Requests: PRCreate, PRResponse, PRDiffResponse, …
│   ├── Releases: ReleaseCreate, ReleaseResponse, ReleaseAssetResponse, …
│   ├── Profile + Social: ProfileResponse, StarResponse, …
│   ├── Discovery: ExploreResponse, SearchResponse, GlobalSearchResult, …
│   ├── Timeline + DAG: TimelineResponse, DagGraphResponse, …
│   └── Webhooks: WebhookCreate, WebhookDeliveryResponse, …
│
└── Database ORM (db/)                        37 SQLAlchemy models
    ├── Auth: User, AccessToken
    ├── CLI VCS: MuseCliObject, MuseCliSnapshot, MuseCliCommit, MuseCliTag
    ├── Hub Core: MusehubRepo, MusehubBranch, MusehubCommit, MusehubObject, …
    ├── Social: MusehubStar, MusehubFollow, MusehubWatch, MusehubNotification, …
    ├── Labels: MusehubLabel, MusehubIssueLabel, MusehubPRLabel
    └── Stash: MusehubStash, MusehubStashEntry
```

---

## Entity Graphs (Mermaid)

Arrow conventions:
- `*--` composition (owns, lifecycle-coupled)
- `-->` association (references)
- `..>` dependency (uses / produces)
- `..|>` implements / extends

---

### Diagram 1 — MIDI Note and Event Wire Types

The core typed shapes for MIDI data. `NoteDict` is dual-keyed (camelCase wire
+ snake_case storage). The region maps alias these into domain containers.

```mermaid
classDiagram
    class NoteDict {
        <<TypedDict total=False>>
        pitch : MidiPitch
        velocity : MidiVelocity
        channel : MidiChannel
        startBeat : BeatPosition
        durationBeats : BeatDuration
        noteId : str
        trackId : str
        regionId : str
        start_beat : BeatPosition
        duration_beats : BeatDuration
        note_id : str
        track_id : str
        region_id : str
        layer : str
    }
    class CCEventDict {
        <<TypedDict>>
        cc : MidiCC
        beat : BeatPosition
        value : MidiCCValue
    }
    class PitchBendDict {
        <<TypedDict>>
        beat : BeatPosition
        value : MidiPitchBend
    }
    class AftertouchDict {
        <<TypedDict total=False>>
        beat : BeatPosition (Required)
        value : MidiAftertouchValue (Required)
        pitch : MidiPitch
    }
    class SectionDict {
        <<TypedDict total=False>>
        name : str
        start_beat : float
        length_beats : float
        description : str
        per_track_description : dict~str, str~
    }
    class RegionNotesMap {
        <<TypeAlias>>
        dict~str, list~NoteDict~~
    }
    class RegionCCMap {
        <<TypeAlias>>
        dict~str, list~CCEventDict~~
    }
    class RegionPitchBendMap {
        <<TypeAlias>>
        dict~str, list~PitchBendDict~~
    }
    class RegionAftertouchMap {
        <<TypeAlias>>
        dict~str, list~AftertouchDict~~
    }

    RegionNotesMap ..> NoteDict : list element
    RegionCCMap ..> CCEventDict : list element
    RegionPitchBendMap ..> PitchBendDict : list element
    RegionAftertouchMap ..> AftertouchDict : list element
```

---

### Diagram 2 — MCP Protocol Event Types

The two concrete events Muse Hub relays over SSE — both in the MCP path.
`MuseEvent` is the typed base; the event registry maps type strings to
model classes.

```mermaid
classDiagram
    class MuseEvent {
        <<Pydantic CamelModel>>
        +type : str
        +seq : int = -1
        +protocol_version : str
        extra = "forbid"
    }
    class MCPMessageEvent {
        <<Pydantic CamelModel>>
        +type : Literal~"mcp.message"~
        +payload : dict~str, object~
    }
    class MCPPingEvent {
        <<Pydantic CamelModel>>
        +type : Literal~"mcp.ping"~
    }
    class EVENT_REGISTRY {
        <<dict frozen at import>>
        "mcp.message" : MCPMessageEvent
        "mcp.ping" : MCPPingEvent
    }

    MCPMessageEvent --|> MuseEvent
    MCPPingEvent --|> MuseEvent
    EVENT_REGISTRY ..> MCPMessageEvent : registers
    EVENT_REGISTRY ..> MCPPingEvent : registers
```

---

### Diagram 3 — Protocol Introspection

The hash computation pipeline and the four HTTP response types it drives.

```mermaid
classDiagram
    class ProtocolInfoResponse {
        <<Pydantic BaseModel>>
        +protocolVersion : str
        +protocolHash : str
        +eventTypes : list~str~
        +eventCount : int
    }
    class ProtocolEventsResponse {
        <<Pydantic BaseModel>>
        +protocolVersion : str
        +events : dict~str, PydanticJson~
    }
    class ProtocolToolsResponse {
        <<Pydantic BaseModel>>
        +protocolVersion : str
        +tools : list~MCPToolDefWire~
        +toolCount : int
    }
    class ProtocolSchemaResponse {
        <<Pydantic BaseModel>>
        +protocolVersion : str
        +protocolHash : str
        +events : dict~str, PydanticJson~
        +tools : list~MCPToolDefWire~
        +toolCount : int
        +eventCount : int
    }
    class MCPToolDefWire {
        <<Pydantic BaseModel>>
        +name : str
        +description : str
        +inputSchema : MCPInputSchemaWire
    }

    ProtocolSchemaResponse ..> MCPToolDefWire : tools list
    ProtocolToolsResponse ..> MCPToolDefWire : tools list
    ProtocolSchemaResponse ..> ProtocolEventsResponse : events subset
    ProtocolSchemaResponse ..> ProtocolToolsResponse : tools subset
```

---

### Diagram 4 — MCP Tool Routing

How a tool name flows from an incoming request through the server routing layer
to the executor and back as a `ToolCallResult`.

```mermaid
classDiagram
    class MuseMCPServer {
        +call_tool(name: str, params: dict) ToolCallResult
        -_execute_musehub_tool(name, params) MusehubToolResult
        -_build_result(result: MusehubToolResult) ToolCallResult
    }
    class ToolCallResult {
        <<dataclass>>
        +success : bool
        +is_error : bool
        +bad_request : bool
        +content : list~dict~str, str~~
    }
    class MusehubToolResult {
        <<dataclass frozen>>
        +ok : bool
        +data : dict~str, JSONValue~
        +error_code : MusehubErrorCode | None
        +error_message : str | None
    }
    class MusehubErrorCode {
        <<Literal>>
        "not_found"
        "invalid_dimension"
        "invalid_mode"
        "db_unavailable"
    }
    class MUSEHUB_TOOLS {
        <<list of MCPToolDef>>
        musehub_browse_repo
        musehub_list_branches
        musehub_list_commits
        musehub_read_file
        musehub_get_analysis
        musehub_search
        musehub_get_context
    }

    MuseMCPServer --> ToolCallResult : returns
    MuseMCPServer ..> MusehubToolResult : executor produces
    MusehubToolResult --> MusehubErrorCode : error_code
    MuseMCPServer ..> MUSEHUB_TOOLS : routes via MUSEHUB_TOOL_NAMES
```

---

### Diagram 5 — MCP JSON-RPC Wire Types

The full JSON-RPC 2.0 type hierarchy used by the MCP HTTP adapter.

```mermaid
classDiagram
    class MCPRequest {
        <<TypedDict total=False>>
        +jsonrpc : str
        +id : str | int | None
        +method : str
        +params : dict~str, object~
    }
    class MCPSuccessResponse {
        <<TypedDict>>
        +jsonrpc : str
        +id : str | int | None
        +result : object
    }
    class MCPErrorDetail {
        <<TypedDict total=False>>
        +code : int
        +message : str
        +data : object
    }
    class MCPErrorResponse {
        <<TypedDict>>
        +jsonrpc : str
        +id : str | int | None
        +error : MCPErrorDetail
    }
    class MCPToolDef {
        <<TypedDict total=False>>
        +name : str
        +description : str
        +inputSchema : MCPInputSchema
        +server_side : bool
    }
    class MCPContentBlock {
        <<TypedDict>>
        +type : str
        +text : str
    }
    class MCPCallResult {
        <<TypedDict total=False>>
        +content : list~MCPContentBlock~
        +isError : bool
    }

    MCPErrorResponse *-- MCPErrorDetail : error
    MCPCallResult *-- MCPContentBlock : content
    MCPToolDef ..> MCPContentBlock : tools/call returns
```

---

### Diagram 6 — Auth and JWT

Token lifecycle from issuance through validation to the decoded `TokenClaims`.

```mermaid
classDiagram
    class TokenClaims {
        <<TypedDict total=False>>
        +type : str (Required)
        +iat : int (Required)
        +exp : int (Required)
        +sub : str
        +role : str
    }
    class AccessToken {
        <<SQLAlchemy ORM>>
        +id : int
        +token_hash : str
        +user_id : str
        +created_at : datetime
        +expires_at : datetime
        +revoked : bool
    }
    class User {
        <<SQLAlchemy ORM>>
        +id : str (JWT sub)
        +username : str
        +email : str
        +created_at : datetime
    }

    AccessToken --> User : user_id FK
    TokenClaims ..> User : sub maps to User.id
    TokenClaims ..> AccessToken : validated against token_hash
```

---

### Diagram 7 — Muse Hub Repository Object Graph

The core VCS entity relationships in the database.

```mermaid
classDiagram
    class MusehubRepo {
        <<SQLAlchemy ORM>>
        +id : str
        +name : str
        +owner_id : str
        +description : str
        +is_public : bool
        +created_at : datetime
    }
    class MusehubBranch {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +name : str
        +head_commit_id : str
    }
    class MusehubCommit {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +branch_id : str (FK)
        +snapshot_id : str
        +message : str
        +committed_at : datetime
    }
    class MusehubObject {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +commit_id : str (FK)
        +path : str
        +content_hash : str
        +mime_type : str
    }
    class MusehubIssue {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +title : str
        +state : str
        +created_at : datetime
    }
    class MusehubPullRequest {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +source_branch : str
        +target_branch : str
        +state : str
    }
    class MusehubRelease {
        <<SQLAlchemy ORM>>
        +id : str
        +repo_id : str (FK)
        +tag : str
        +title : str
        +created_at : datetime
    }

    MusehubRepo *-- MusehubBranch : branches
    MusehubRepo *-- MusehubCommit : commits
    MusehubRepo *-- MusehubObject : objects
    MusehubRepo *-- MusehubIssue : issues
    MusehubRepo *-- MusehubPullRequest : pull requests
    MusehubRepo *-- MusehubRelease : releases
    MusehubBranch --> MusehubCommit : head_commit_id
    MusehubCommit --> MusehubObject : objects
```

---

### Diagram 8 — Social and Discovery Graph

User-to-user and user-to-repo relationships powering the social feed and
discovery pages.

```mermaid
classDiagram
    class User {
        <<SQLAlchemy ORM>>
        +id : str
        +username : str
    }
    class MusehubProfile {
        <<SQLAlchemy ORM>>
        +user_id : str (FK)
        +display_name : str
        +bio : str
    }
    class MusehubStar {
        <<SQLAlchemy ORM>>
        +user_id : str (FK)
        +repo_id : str (FK)
        +starred_at : datetime
    }
    class MusehubFollow {
        <<SQLAlchemy ORM>>
        +follower_id : str (FK)
        +followee_id : str (FK)
        +created_at : datetime
    }
    class MusehubWatch {
        <<SQLAlchemy ORM>>
        +user_id : str (FK)
        +repo_id : str (FK)
    }
    class MusehubNotification {
        <<SQLAlchemy ORM>>
        +id : str
        +user_id : str (FK)
        +event_type : str
        +read : bool
    }
    class MusehubRepo {
        <<SQLAlchemy ORM>>
        +id : str
        +name : str
    }

    User *-- MusehubProfile : profile
    User ..> MusehubStar : stars
    User ..> MusehubFollow : follows / followed_by
    User ..> MusehubWatch : watches
    User ..> MusehubNotification : receives
    MusehubStar --> MusehubRepo : repo_id
    MusehubWatch --> MusehubRepo : repo_id
```

---

### Diagram 9 — Full Entity Overview

All named layers and the dependency flow between them.

```mermaid
classDiagram
    class MIDIAliases {
        <<contracts/midi_types.py>>
        MidiPitch · MidiVelocity · BeatPosition · BeatDuration · …
    }
    class JSONTypes {
        <<contracts/json_types.py>>
        NoteDict · CCEventDict · PitchBendDict · AftertouchDict · SectionDict
        JSONValue · JSONObject · RegionNotesMap · EventJsonSchema
    }
    class MCPTypes {
        <<contracts/mcp_types.py>>
        MCPRequest · MCPResponse · MCPToolDef · DAWToolCallMessage
        MCPToolDefWire (Pydantic)
    }
    class PydanticBase {
        <<contracts/pydantic_types.py + models/base.py>>
        PydanticJson (RootModel)
        CamelModel (BaseModel)
    }
    class AuthTypes {
        <<auth/tokens.py>>
        TokenClaims (TypedDict)
    }
    class ProtocolEvents {
        <<protocol/events.py>>
        MuseEvent (base)
        MCPMessageEvent · MCPPingEvent
    }
    class ProtocolResponses {
        <<protocol/responses.py>>
        ProtocolInfoResponse
        ProtocolEventsResponse
        ProtocolToolsResponse
        ProtocolSchemaResponse
    }
    class MCPTools {
        <<mcp/>>
        MUSEHUB_TOOLS (7 tools)
        MuseMCPServer · ToolCallResult
        MusehubToolResult
    }
    class APIModels {
        <<models/musehub.py>>
        ~98 Pydantic CamelModel subclasses
        VCS · Repos · Issues · PRs · Releases · Social · Search
    }
    class DatabaseORM {
        <<db/>>
        37 SQLAlchemy models
        User · AccessToken · MusehubRepo · MusehubBranch · MusehubCommit · …
    }

    JSONTypes ..> MIDIAliases : constrained int/float aliases
    MCPTypes ..> PydanticBase : MCPToolDefWire extends CamelModel
    ProtocolEvents ..> PydanticBase : MuseEvent extends CamelModel
    ProtocolResponses ..> PydanticBase : all extend BaseModel
    ProtocolResponses ..> MCPTypes : MCPToolDefWire in tools fields
    MCPTools ..> MCPTypes : MUSEHUB_TOOLS match MCPToolDef shape
    MCPTools ..> JSONTypes : MusehubToolResult.data uses JSONValue
    APIModels ..> PydanticBase : all extend CamelModel
    AuthTypes ..> DatabaseORM : TokenClaims.sub → User.id
```

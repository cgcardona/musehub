"""MuseHub MCP tool definitions — 40 tools for AI agents (MCP 2025-11-25).

Covers the full MuseHub surface: reads (20), writes (15), and elicitation-powered
interactive tools (5).

Elicitation-powered tools use the ToolCallContext to collect user preferences
mid-call via the MCP 2025-11-25 elicitation protocol. They require an active
session (``Mcp-Session-Id``) and degrade gracefully without one.

Reads give agents complete browsing power — repos, branches, commits, files,
domain insights, issues, PRs, releases, and global discovery.

Writes give agents full contribution capability — create repos, open and
manage issues and PRs, merge, publish releases, and build social graphs.

Naming convention:
  ``musehub_<verb>_<noun>`` — hub API tools.
  ``muse_<verb>`` — Muse CLI-analogous tools (push, pull, remote, config).

Addressing: all repo-scoped tools accept either ``repo_id`` (UUID) or both
``owner`` + ``slug`` (e.g. ``owner='gabriel'``, ``slug='jazz-standards'``).
The dispatcher resolves ``owner``+``slug`` to ``repo_id`` transparently.

All tools carry ``server_side: True`` so the dispatcher routes them to the
executor layer rather than forwarding to a connected DAW.
"""

from musehub.contracts.mcp_types import MCPPropertyDef, MCPToolDef


# ── Shared schema fragments ───────────────────────────────────────────────────

_REPO_ID_PROP: dict[str, MCPPropertyDef] = {
    "repo_id": {
        "type": "string",
        "description": (
            "UUID of the MuseHub repository. "
            "Alternatively, provide 'owner' + 'slug' to identify by URL path."
        ),
    },
    "owner": {
        "type": "string",
        "description": (
            "Repository owner username (e.g. 'gabriel'). "
            "Use with 'slug' as an alternative to 'repo_id'."
        ),
    },
    "slug": {
        "type": "string",
        "description": (
            "Repository slug — the URL-safe name (e.g. 'jazz-standards'). "
            "Use with 'owner' as an alternative to 'repo_id'."
        ),
    },
}


# ── Read tools ────────────────────────────────────────────────────────────────


MUSEHUB_READ_TOOLS: list[MCPToolDef] = [
    {
        "name": "musehub_get_context",
        "server_side": True,
        "description": (
            "Start here. Get the full AI context document for a MuseHub repository: "
            "domain plugin (scoped_id, dimensions, capabilities), branches, recent commits, "
            "and artifact inventory — in a single call. "
            "This is the primary oracle for any agent: always call it before creating "
            "or modifying state to ensure coherence with the existing multidimensional content. "
            "For computed analytics (per-dimension scores), follow up with musehub_get_domain_insights. "
            "For the full viewer payload (dimension slices, navigation strip), follow up with musehub_get_view. "
            "Repo identifier required: provide repo_id OR both owner+slug. "
            "Example: musehub_get_context(repo_id='a3f2-...') "
            "or musehub_get_context(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _REPO_ID_PROP,
            "required": [],
        },
    },
    {
        "name": "musehub_list_branches",
        "server_side": True,
        "description": (
            "List all branches in a MuseHub repository with their head commit IDs. "
            "Call before musehub_list_commits to identify the target branch ref. "
            "Example: musehub_list_branches(repo_id='a3f2-...') "
            "or musehub_list_branches(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _REPO_ID_PROP,
            "required": [],
        },
    },
    {
        "name": "musehub_list_commits",
        "server_side": True,
        "description": (
            "List commits on a MuseHub repository (newest first). "
            "Optionally filter by branch name and cap the result count. "
            "Example: musehub_list_commits(repo_id='a3f2-...', branch='main', limit=10) "
            "or musehub_list_commits(owner='gabriel', slug='jazz-standards', branch='main')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "branch": {
                    "type": "string",
                    "description": "Branch name filter (e.g. 'main'). Omit to list across all branches.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum commits to return (default: 20, max: 100).",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_read_file",
        "server_side": True,
        "description": (
            "Read the metadata for a stored artifact (MIDI, MP3, WebP piano roll) "
            "in a MuseHub repo. Returns path, size_bytes, mime_type, and object_id. "
            "Binary content is not returned — discover object IDs via musehub_get_context first. "
            "Example: musehub_read_file(repo_id='a3f2-...', object_id='sha256:abc...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "object_id": {
                    "type": "string",
                    "description": "Content-addressed object ID (e.g. 'sha256:abc...').",
                },
            },
            "required": ["object_id"],
        },
    },
    {
        "name": "musehub_search",
        "server_side": True,
        "description": (
            "Search within a MuseHub repository by substring query. "
            "Mode 'path' matches artifact file paths (e.g. 'tracks/jazz'); "
            "mode 'commit' searches commit messages (e.g. 'add bass'). "
            "Returns matching items with their metadata. "
            "Example: musehub_search(repo_id='a3f2-...', query='bass', mode='path') "
            "or musehub_search(owner='gabriel', slug='jazz-standards', query='bass')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "query": {
                    "type": "string",
                    "description": "Substring query string (case-insensitive).",
                },
                "mode": {
                    "type": "string",
                    "description": "Search mode: 'path' searches object paths; 'commit' searches commit messages.",
                    "enum": ["path", "commit"],
                    "default": "path",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "musehub_get_commit",
        "server_side": True,
        "description": (
            "Get detailed information about a single commit, including its message, "
            "author, timestamp, parent IDs, and the full list of artifact paths "
            "at that snapshot. Use to inspect what changed at a specific point in history. "
            "Example: musehub_get_commit(repo_id='a3f2-...', commit_id='sha256:abc...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "commit_id": {
                    "type": "string",
                    "description": "Commit ID (SHA or short ID).",
                },
            },
            "required": ["commit_id"],
        },
    },
    {
        "name": "musehub_compare",
        "server_side": True,
        "description": (
            "Compare two refs (branches or commit IDs) in a MuseHub repository. "
            "Returns a multidimensional state diff: which artifacts were added, removed, or modified, "
            "and per-dimension change scores sourced from the repo's domain plugin capabilities. "
            "Example: musehub_compare(repo_id='a3f2-...', base_ref='main', head_ref='feature/new-section') "
            "or musehub_compare(owner='gabriel', slug='jazz-standards', base_ref='main', head_ref='feature/bridge')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "base_ref": {
                    "type": "string",
                    "description": "Base branch name or commit ID.",
                },
                "head_ref": {
                    "type": "string",
                    "description": "Head branch name or commit ID to compare against base.",
                },
            },
            "required": ["base_ref", "head_ref"],
        },
    },
    {
        "name": "musehub_list_issues",
        "server_side": True,
        "description": (
            "List issues for a MuseHub repository. "
            "Filter by state (open/closed/all) or label string. "
            "Returns issue summaries (title, state, labels) — "
            "call musehub_get_issue with the number to get the full body and comment thread. "
            "Example: musehub_list_issues(repo_id='a3f2-...', state='open', label='bug') "
            "or musehub_list_issues(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "state": {
                    "type": "string",
                    "description": "Filter by state: 'open', 'closed', or 'all'.",
                    "enum": ["open", "closed", "all"],
                    "default": "open",
                },
                "label": {
                    "type": "string",
                    "description": "Filter to issues with this label string.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_get_issue",
        "server_side": True,
        "description": (
            "Get a single issue by its per-repo number, including the full body and comment thread. "
            "Use musehub_list_issues to discover issue numbers, then this tool to read the detail. "
            "Example: musehub_get_issue(repo_id='a3f2-...', issue_number=42) "
            "or musehub_get_issue(owner='gabriel', slug='jazz-standards', issue_number=42)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "issue_number": {
                    "type": "integer",
                    "description": "Per-repo issue number.",
                },
            },
            "required": ["issue_number"],
        },
    },
    {
        "name": "musehub_list_prs",
        "server_side": True,
        "description": (
            "List pull requests for a MuseHub repository. "
            "Filter by state (open/merged/closed/all). "
            "Returns PR summaries — call musehub_get_pr with the pr_id to get reviews and inline comments. "
            "Example: musehub_list_prs(repo_id='a3f2-...', state='open') "
            "or musehub_list_prs(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "state": {
                    "type": "string",
                    "description": "Filter by state: 'open', 'merged', 'closed', or 'all'.",
                    "enum": ["open", "merged", "closed", "all"],
                    "default": "all",
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_get_pr",
        "server_side": True,
        "description": (
            "Get a single pull request by ID, including all reviews and inline dimension-anchored comments. "
            "Use musehub_list_prs to discover pr_ids, then this tool to read the full detail. "
            "Example: musehub_get_pr(repo_id='a3f2-...', pr_id='b5e8-...') "
            "or musehub_get_pr(owner='gabriel', slug='jazz-standards', pr_id='b5e8-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request.",
                },
            },
            "required": ["pr_id"],
        },
    },
    {
        "name": "musehub_list_releases",
        "server_side": True,
        "description": (
            "List all releases for a MuseHub repository, ordered newest first. "
            "Each release includes tag, title, release notes summary, and asset counts. "
            "Example: musehub_list_releases(repo_id='a3f2-...') "
            "or musehub_list_releases(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _REPO_ID_PROP,
            "required": [],
        },
    },
    {
        "name": "musehub_search_repos",
        "server_side": True,
        "description": (
            "Discover public MuseHub repositories across all domains by text query, "
            "domain plugin, or free-text tags. "
            "Filter by domain scoped ID (e.g. '@gabriel/midi') to browse repos of a specific type. "
            "Returns repos sorted by relevance including repo_id, owner, and slug for each result. "
            "Example: musehub_search_repos(query='jazz', domain='@gabriel/midi')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text query matched against repo names and descriptions.",
                },
                "domain": {
                    "type": "string",
                    "description": "Filter by domain scoped ID, e.g. '@gabriel/midi' or '@gabriel/code'.",
                },
                "tags": {
                    "type": "array",
                    "description": "Filter repos that have all of these tags.",
                    "items": {"type": "string"},
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20, max: 100).",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_list_domains",
        "server_side": True,
        "description": (
            "List and search all registered Muse domain plugins. "
            "Domains are the extensibility layer that give Muse its domain-agnostic power — "
            "each domain defines its own dimensions, viewer, merge semantics, CLI commands, "
            "and artifact types. "
            "Filter by query string, viewer_type, or verified status. "
            "Returns scoped_id (@author/slug), display_name, description, capabilities, "
            "repo_count, and install_count for each domain. "
            "Example: musehub_list_domains(query='genomics', verified=true)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Full-text search across name and description.",
                },
                "viewer_type": {
                    "type": "string",
                    "description": "Filter by viewer type (e.g. 'piano_roll', 'code_graph', 'generic').",
                },
                "verified": {
                    "type": "boolean",
                    "description": "When true, return only officially-verified domains.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20, max 100).",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset.",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_get_domain",
        "server_side": True,
        "description": (
            "Fetch the full manifest for a specific Muse domain plugin by its scoped ID. "
            "Returns all capabilities: dimensions list, viewer_type, merge_semantics, "
            "cli_commands, artifact_types, manifest_hash (content-addressed, immutable), "
            "version, repo_count, and install_count. "
            "Call this after musehub_get_context to understand the domain a repo uses, "
            "or before creating a repo to verify domain capabilities. "
            "Example: musehub_get_domain(scoped_id='@gabriel/midi')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scoped_id": {
                    "type": "string",
                    "description": "Domain scoped identifier in '@author/slug' format.",
                },
            },
            "required": ["scoped_id"],
        },
    },
    {
        "name": "musehub_get_domain_insights",
        "server_side": True,
        "description": (
            "Get computed analytics for a MuseHub repository across any of its domain's dimensions. "
            "Returns numeric scores and structured metrics — e.g. harmonic tension score, "
            "rhythmic complexity, melodic contour for MIDI; symbol hotspots, coupling metrics for Code. "
            "The available dimensions are defined by the repo's domain plugin — call "
            "musehub_get_domain first to learn the dimension names. "
            "dimension='overview' always returns cross-domain stats (commits, objects, collaborators). "
            "Prefer musehub_get_context for structural understanding; use this tool when you need "
            "quantitative analysis of a specific dimension. "
            "For the viewer-ready state payload, use musehub_get_view instead. "
            "Example: musehub_get_domain_insights(repo_id='a3f2-...', dimension='harmonic')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "dimension": {
                    "type": "string",
                    "description": (
                        "Insight dimension to fetch. 'overview' is always available; "
                        "other values depend on the repo's domain plugin."
                    ),
                    "default": "overview",
                },
                "ref": {
                    "type": "string",
                    "description": "Branch name, tag, or commit SHA to scope the insights to. Defaults to HEAD.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_get_view",
        "server_side": True,
        "description": (
            "Fetch the universal viewer payload for a repo at a given ref. "
            "Returns the structured representation of multidimensional state as rendered by the "
            "domain's viewer — dimension slices, navigation strip entries, and domain-specific "
            "viewer metadata. This is the MCP equivalent of the /{owner}/{repo}/view/{ref} page. "
            "Use when you need the full state payload for reasoning or rendering. "
            "For quantitative analytics (scores, metrics), use musehub_get_domain_insights instead. "
            "For repo identity and inventory, use musehub_get_context instead. "
            "Example: musehub_get_view(repo_id='a3f2-...', ref='main') "
            "or musehub_get_view(owner='gabriel', slug='jazz-standards', ref='main')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "ref": {
                    "type": "string",
                    "description": "Branch name, tag, or commit SHA. Defaults to HEAD of default branch.",
                },
                "dimension": {
                    "type": "string",
                    "description": (
                        "Optional: restrict the view payload to a single dimension slice. "
                        "Omit to get the full multi-dimensional view."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_whoami",
        "server_side": True,
        "description": (
            "Return identity information for the currently authenticated caller. "
            "Call this first to confirm authentication before any write operations. "
            "Works for both human users and AI agent tokens. "
            "Authenticated response includes: user_id (UUID), username (handle), "
            "display_name, repo_count, is_admin, and token_type ('human' or 'agent'). "
            "Returns {authenticated: false} when called without a Bearer token — never errors. "
            "Example: musehub_whoami()."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "muse_pull",
        "server_side": True,
        "description": (
            "Fetch missing commits and objects from a MuseHub repository. "
            "Equivalent to 'muse pull' — returns new commits and object metadata "
            "since the given commit ID. Use since_commit_id to fetch incrementally. "
            "Pass object_ids to download specific binary objects — their content is returned "
            "as base64-encoded strings in the 'content_b64' field of each object entry; "
            "decode with base64.b64decode() before writing to disk. "
            "Example: muse_pull(repo_id='a3f2-...', branch='main', since_commit_id='abc123') "
            "or muse_pull(owner='gabriel', slug='jazz-standards', branch='main')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "branch": {
                    "type": "string",
                    "description": "Branch to pull from. Defaults to the default branch.",
                },
                "since_commit_id": {
                    "type": "string",
                    "description": "Only return commits newer than this commit ID.",
                },
                "object_ids": {
                    "type": "array",
                    "description": "Specific object IDs to fetch (content-addressed).",
                    "items": {"type": "string"},
                },
            },
            "required": [],
        },
    },
    {
        "name": "muse_remote",
        "server_side": True,
        "description": (
            "Return the remote URL, push/pull API endpoints, and clone command for a MuseHub repository. "
            "Covers both 'muse remote -v' and 'muse clone' use cases in a single call. "
            "Returns: origin URL, push endpoint, pull endpoint, clone command (with optional ref), "
            "and the 'muse remote add origin' command. "
            "Use this when setting up a local repo to push to MuseHub, or to get the clone URL. "
            "Example: muse_remote(owner='gabriel', slug='neo-soul-experiment') "
            "or muse_remote(owner='gabriel', slug='neo-soul-experiment', ref='feat/jazz-bridge')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Repository owner username.",
                },
                "slug": {
                    "type": "string",
                    "description": "Repository slug (URL-safe name).",
                },
                "ref": {
                    "type": "string",
                    "description": "Optional branch or tag to target (used in the clone command).",
                },
            },
                "required": ["owner", "slug"],
        },
    },
    {
        "name": "musehub_get_prompt",
        "server_side": True,
        "description": (
            "Return the fully assembled content of a named MuseHub MCP prompt. "
            "This is a tool-layer shim over the MCP prompts/get primitive, enabling "
            "agents whose client only supports tools/call to access prompt content "
            "programmatically — identical output to prompts/get, callable as a tool. "
            "Use musehub_list_prompts() (prompts/list) to discover available prompt names. "
            "The ten available prompts are: musehub/orientation, musehub/contribute, "
            "musehub/create, musehub/review_pr, musehub/issue_triage, musehub/release_prep, "
            "musehub/onboard, musehub/release_to_world, musehub/domain-discovery, "
            "musehub/domain-authoring. "
            "Pass caller_type='agent' to musehub/orientation for agent-specific guidance. "
            "Example: musehub_get_prompt(name='musehub/orientation', "
            "arguments={'caller_type': 'agent'})."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Prompt name to fetch, e.g. 'musehub/orientation' or "
                        "'musehub/contribute'. Must be one of the ten musehub/* prompts."
                    ),
                    "enum": [
                        "musehub/orientation",
                        "musehub/contribute",
                        "musehub/create",
                        "musehub/review_pr",
                        "musehub/issue_triage",
                        "musehub/release_prep",
                        "musehub/onboard",
                        "musehub/release_to_world",
                        "musehub/domain-discovery",
                        "musehub/domain-authoring",
                    ],
                },
                "arguments": {
                    "type": "object",
                    "description": (
                        "Optional prompt arguments as string key-value pairs. "
                        "E.g. {'caller_type': 'agent'} for musehub/orientation, "
                        "{'repo_id': '<uuid>'} for musehub/contribute, "
                        "{'use_case': 'genomics'} for musehub/domain-discovery."
                    ),
                },
            },
            "required": ["name"],
        },
    },
]


# ── Write tools ───────────────────────────────────────────────────────────────


MUSEHUB_WRITE_TOOLS: list[MCPToolDef] = [
    {
        "name": "musehub_create_repo",
        "server_side": True,
        "description": (
            "Create a new MuseHub repository for any Muse domain. "
            "The slug is auto-generated from the name. "
            "Specify a domain scoped ID (e.g. '@gabriel/midi') to associate the repo with "
            "a domain plugin — this unlocks domain-specific viewers, insights, and CLI commands. "
            "Call musehub_list_domains first to discover available domains. "
            "Set initialize=true (default) to get an initial commit and default branch. "
            "Example: musehub_create_repo(name='Genome Edit Session', "
            "domain='@alice/genomics', visibility='public')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable repository name (slug auto-generated).",
                },
                "description": {
                    "type": "string",
                    "description": "Optional markdown description of the repository.",
                },
                "visibility": {
                    "type": "string",
                    "description": "Repository visibility: 'public' or 'private'.",
                    "enum": ["public", "private"],
                    "default": "public",
                },
                "domain": {
                    "type": "string",
                    "description": (
                        "Domain plugin scoped ID (e.g. '@gabriel/midi', '@gabriel/code'). "
                        "Call musehub_list_domains first to discover available domains."
                    ),
                },
                "domain_meta": {
                    "type": "object",
                    "description": (
                        "Domain-specific metadata dict declared by the domain plugin "
                        "(e.g. {\"key_signature\": \"F# minor\", \"tempo_bpm\": 120} for MIDI)."
                    ),
                },
                "tags": {
                    "type": "array",
                    "description": "Free-form tags for discovery (e.g. ['jazz', 'trio']).",
                    "items": {"type": "string"},
                },
                "initialize": {
                    "type": "boolean",
                    "description": "When true (default), creates an initial commit and default branch.",
                    "default": True,
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "musehub_create_issue",
        "server_side": True,
        "description": (
            "Open a new issue in a MuseHub repository. "
            "Use issues to track problems, feature requests, or collaboration needs. "
            "Example: musehub_create_issue(repo_id='a3f2-...', title='Bass too muddy in bars 8-16') "
            "or musehub_create_issue(owner='gabriel', slug='jazz-standards', title='Harmony conflict in bridge')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "title": {
                    "type": "string",
                    "description": "Issue title.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional markdown description.",
                },
                "labels": {
                    "type": "array",
                    "description": "Label strings to apply on creation.",
                    "items": {"type": "string"},
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "musehub_update_issue",
        "server_side": True,
        "description": (
            "Update an existing issue's title, body, labels, state, or assignee. "
            "Only provided fields are modified. "
            "Set state='closed' to close the issue, state='open' to reopen it. "
            "Example: musehub_update_issue(repo_id='a3f2-...', issue_number=42, state='closed')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "issue_number": {
                    "type": "integer",
                    "description": "Per-repo issue number.",
                },
                "title": {
                    "type": "string",
                    "description": "New title (optional).",
                },
                "body": {
                    "type": "string",
                    "description": "New markdown body (optional).",
                },
                "labels": {
                    "type": "array",
                    "description": "Replacement label list (replaces existing labels).",
                    "items": {"type": "string"},
                },
                "state": {
                    "type": "string",
                    "description": "New state: 'open' or 'closed'.",
                    "enum": ["open", "closed"],
                },
                "assignee": {
                    "type": "string",
                    "description": "Username to assign, or empty string to unassign.",
                },
            },
            "required": ["issue_number"],
        },
    },
    {
        "name": "musehub_create_issue_comment",
        "server_side": True,
        "description": (
            "Add a comment to an existing issue. "
            "Example: musehub_create_issue_comment(repo_id='a3f2-...', issue_number=42, "
            "body='Fixed in commit abc...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "issue_number": {
                    "type": "integer",
                    "description": "Per-repo issue number.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown comment body.",
                },
            },
            "required": ["issue_number", "body"],
        },
    },
    {
        "name": "musehub_create_pr",
        "server_side": True,
        "description": (
            "Open a new pull request proposing to merge from_branch into to_branch. "
            "Call musehub_list_branches first to confirm both branches exist. "
            "Example: musehub_create_pr(repo_id='a3f2-...', title='Add jazz bridge', "
            "from_branch='feature/jazz-bridge', to_branch='main')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "title": {
                    "type": "string",
                    "description": "Pull request title.",
                },
                "from_branch": {
                    "type": "string",
                    "description": "Source branch name to merge from.",
                },
                "to_branch": {
                    "type": "string",
                    "description": "Target branch name to merge into.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional markdown description.",
                },
            },
            "required": ["title", "from_branch", "to_branch"],
        },
    },
    {
        "name": "musehub_merge_pr",
        "server_side": True,
        "description": (
            "Merge an open pull request. Creates a merge commit on the target branch. "
            "The PR must be in 'open' state. Obtain pr_id from musehub_list_prs. "
            "Example: musehub_merge_pr(repo_id='a3f2-...', pr_id='b5e8-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request to merge.",
                },
                "merge_strategy": {
                    "type": "string",
                    "description": "Merge strategy: 'merge_commit' (default), 'squash', or 'rebase'.",
                    "enum": ["merge_commit", "squash", "rebase"],
                    "default": "merge_commit",
                },
            },
            "required": ["pr_id"],
        },
    },
    {
        "name": "musehub_create_pr_comment",
        "server_side": True,
        "description": (
            "Post a comment on a pull request, optionally anchored to a specific dimension reference. "
            "Pass a dimension_ref object to pinpoint exactly where in the multidimensional state "
            "the comment applies — the shape of this object is defined by the repo's domain plugin. "
            "For MIDI: {\"dimension\": \"rhythmic\", \"track\": \"Drums\", \"beat_start\": 8.0, \"beat_end\": 12.0}. "
            "For Code: {\"dimension\": \"syntax\", \"file\": \"src/main.py\", \"line_start\": 42, \"line_end\": 55}. "
            "Omit dimension_ref for a general (PR-level) comment. "
            "Example: musehub_create_pr_comment(repo_id='a3f2-...', pr_id='b5e8-...', "
            "body='Unexpected state divergence here', "
            "dimension_ref={\"dimension\": \"structural\", \"node\": \"bridge\"})."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown comment body.",
                },
                "dimension_ref": {
                    "type": "object",
                    "description": (
                        "Optional domain-specific anchor identifying where in the "
                        "multidimensional state this comment applies. "
                        "Schema is defined by the repo's domain plugin."
                    ),
                },
            },
            "required": ["pr_id", "body"],
        },
    },
    {
        "name": "musehub_submit_pr_review",
        "server_side": True,
        "description": (
            "Submit a formal review on a pull request. "
            "event='approve' approves the PR; event='request_changes' blocks merge; "
            "event='comment' adds a neutral review comment. "
            "Example: musehub_submit_pr_review(repo_id='a3f2-...', pr_id='b5e8-...', "
            "event='approve', body='Sounds great! The bridge lands perfectly.')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request.",
                },
                "event": {
                    "type": "string",
                    "description": "Review verdict: 'approve', 'request_changes', or 'comment'.",
                    "enum": ["approve", "request_changes", "comment"],
                },
                "body": {
                    "type": "string",
                    "description": "Optional review summary.",
                },
            },
            "required": ["pr_id", "event"],
        },
    },
    {
        "name": "musehub_create_release",
        "server_side": True,
        "description": (
            "Publish a new release for a MuseHub repository. "
            "A release pins a version tag to a commit and packages the state snapshot. "
            "Tags must be unique per repo (e.g. 'v1.0', 'final-mix'). "
            "For an interactive release flow with elicitation, use musehub_create_release_interactive. "
            "Example: musehub_create_release(repo_id='a3f2-...', tag='v1.0', title='First Release', "
            "body='Initial session recording.')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "tag": {
                    "type": "string",
                    "description": "Version tag string (e.g. 'v1.0'). Must be unique per repo.",
                },
                "title": {
                    "type": "string",
                    "description": "Human-readable release title.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown release notes.",
                },
                "commit_id": {
                    "type": "string",
                    "description": "Optional commit SHA to pin this release to. Defaults to HEAD of the default branch.",
                },
                "channel": {
                    "type": "string",
                    "description": "Distribution channel: stable | beta | alpha | nightly. Defaults to 'stable'.",
                    "default": "stable",
                },
            },
            "required": ["tag", "title"],
        },
    },
    {
        "name": "musehub_star_repo",
        "server_side": True,
        "description": (
            "Star a MuseHub repository to show appreciation and follow its activity. "
            "Starred repos appear in the user's starred list. Idempotent. "
            "Repo identifier required: provide repo_id OR both owner+slug. "
            "Example: musehub_star_repo(repo_id='a3f2-...') "
            "or musehub_star_repo(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _REPO_ID_PROP,
            "required": [],
        },
    },
    {
        "name": "musehub_fork_repo",
        "server_side": True,
        "description": (
            "Fork a public MuseHub repository under the authenticated user's account. "
            "Creates a new repo with all branches and establishes fork lineage. "
            "Only public repos can be forked. "
            "Repo identifier required: provide repo_id OR both owner+slug. "
            "Example: musehub_fork_repo(repo_id='a3f2-...') "
            "or musehub_fork_repo(owner='gabriel', slug='jazz-standards')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _REPO_ID_PROP,
            "required": [],
        },
    },
    {
        "name": "musehub_create_label",
        "server_side": True,
        "description": (
            "Create a repo-scoped label with a name and hex colour. "
            "Labels can be applied to issues and PRs for categorisation. "
            "Label names must be unique within the repository. "
            "Example: musehub_create_label(repo_id='a3f2-...', name='harmonic-issue', color='e11d48')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "name": {
                    "type": "string",
                    "description": "Label name (must be unique per repo).",
                },
                "color": {
                    "type": "string",
                    "description": "6-character hex colour without '#' (e.g. 'e11d48').",
                },
                "description": {
                    "type": "string",
                    "description": "Optional label description.",
                },
            },
            "required": ["name", "color"],
        },
    },
    {
        "name": "musehub_create_agent_token",
        "server_side": True,
        "description": (
            "Mint a long-lived JWT agent token for programmatic MuseHub access. "
            "Agent tokens have higher rate limits than user tokens and appear "
            "with an 'agent' badge in the MuseHub activity feed. "
            "The response includes the token value and the exact command to store it: "
            "write it to ~/.muse/identity.toml under your hub hostname, or run "
            "'muse auth login --token <token> --hub https://musehub.ai'. "
            "Requires an authenticated session (the token is issued for the calling user). "
            "Example: musehub_create_agent_token(agent_name='my-composer-bot/1.0', expires_in_days=90)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": (
                        "Human-readable agent identifier, e.g. 'my-bot/1.0'. "
                        "Appears in the activity feed alongside agent actions."
                    ),
                },
                "expires_in_days": {
                    "type": "integer",
                    "description": "Token validity in days (default: 90, max: 365).",
                    "default": 90,
                    "minimum": 1,
                    "maximum": 365,
                },
            },
            "required": ["agent_name"],
        },
    },
    {
        "name": "muse_push",
        "server_side": True,
        "description": (
            "Push commits, snapshots, and binary objects to a MuseHub repository. "
            "Equivalent to 'muse push' — uploads new commits, their snapshot manifests, "
            "and base64-encoded binary objects in a single atomic batch. "
            "Enforces fast-forward semantics unless force=true. "
            "All three arrays are optional — a push with only commits and no new file content "
            "is valid (e.g. a merge commit that modifies no files). "
            "Authentication required: call musehub_create_agent_token first. "
            "Example: muse_push(repo_id='a3f2-...', branch='main', head_commit_id='abc123', "
            "commits=[{commit_id, parent_ids, message, snapshot_id, ...}], "
            "snapshots=[{snapshot_id, manifest:{path: object_id}}], "
            "objects=[{object_id, path, content_b64}])."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "branch": {
                    "type": "string",
                    "description": "Target branch name (e.g. 'main').",
                },
                "head_commit_id": {
                    "type": "string",
                    "description": "SHA of the new HEAD commit after this push.",
                },
                "commits": {
                    "type": "array",
                    "description": (
                        "List of CommitInput objects to push. Each has: "
                        "commit_id (str), parent_ids (list[str]), message (str), "
                        "author (str), timestamp (ISO-8601 str), snapshot_id (str)."
                    ),
                    "items": {"type": "object"},
                },
                "snapshots": {
                    "type": "array",
                    "description": (
                        "Snapshot manifests for the pushed commits. Each has: "
                        "snapshot_id (str, SHA-256 of sorted path:oid pairs), "
                        "manifest (dict[str, str] mapping path → object_id), "
                        "created_at (ISO-8601 str, optional). "
                        "Snapshots are idempotent — already-stored snapshots are skipped. "
                        "Include one snapshot per commit that introduces file changes."
                    ),
                    "items": {"type": "object"},
                },
                "objects": {
                    "type": "array",
                    "description": (
                        "List of ObjectInput objects to upload. Each has: "
                        "object_id (str, e.g. 'sha256:abc...'), "
                        "path (str, e.g. 'tracks/bass.mid'), "
                        "content_b64 (str, base64-encoded bytes)."
                    ),
                    "items": {"type": "object"},
                },
                "force": {
                    "type": "boolean",
                    "description": "Allow non-fast-forward push (overwrites remote head). Use with caution.",
                    "default": False,
                },
            },
            "required": ["branch", "head_commit_id"],
        },
    },
    {
        "name": "muse_config",
        "server_side": True,
        "description": (
            "Read info about Muse configuration keys or generate a 'muse config set' command. "
            "Equivalent to 'muse config get <key>' or 'muse config set <key> <value>'. "
            "Call without arguments to list all known config keys. "
            "Pass key and value to get the exact CLI command to run. "
            "Repo-level keys (stored in .muse/config.toml): hub.url, user.type. "
            "Auth tokens are stored per-hub in ~/.muse/identity.toml — use 'muse auth login' "
            "or write the token directly under the hub hostname section. "
            "Example: muse_config(key='hub.url', value='https://musehub.ai')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "Configuration key to query or set "
                        "(e.g. 'hub.url', 'user.type'). "
                        "Note: auth tokens live in ~/.muse/identity.toml, not config.toml. "
                        "Omit to list all known keys."
                    ),
                },
                "value": {
                    "type": "string",
                    "description": (
                        "When provided together with key, returns the CLI command "
                        "'muse config set <key> <value>'."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_publish_domain",
        "server_side": True,
        "description": (
            "Register a new Muse domain plugin in the MuseHub marketplace. "
            "After registration the domain appears in musehub_list_domains and can be "
            "selected when creating repos (musehub_create_repo). "
            "The scoped identifier '@{author_slug}/{slug}' must be globally unique. "
            "Authentication required: call musehub_create_agent_token first. "
            "The 'capabilities' object must follow the Muse domain schema:\n"
            "  dimensions: list of {name, description} objects\n"
            "  viewer_type: primary viewer identifier (e.g. 'midi', 'code', 'spatial')\n"
            "  artifact_types: list of MIME types the domain produces\n"
            "  merge_semantics: 'ot' | 'crdt' | 'three_way'\n"
            "  supported_commands: list of muse CLI commands this domain supports\n"
            "Returns: {domain_id, scoped_id, manifest_hash} on success. "
            "Example: musehub_publish_domain(author_slug='gabriel', slug='genomics', "
            "display_name='Genomics', description='Version DNA sequences', "
            "capabilities={...}, viewer_type='sequence', version='0.1.0')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "author_slug": {
                    "type": "string",
                    "description": "Your MuseHub username (owner of the domain).",
                },
                "slug": {
                    "type": "string",
                    "description": "URL-safe domain name (e.g. 'genomics', 'spatial-3d').",
                },
                "display_name": {
                    "type": "string",
                    "description": "Human-readable name shown in the marketplace.",
                },
                "description": {
                    "type": "string",
                    "description": "What this domain models and why it benefits from semantic VCS.",
                },
                "capabilities": {
                    "type": "object",
                    "description": (
                        "Domain capabilities manifest. Required keys: "
                        "dimensions (list of {name, description}), "
                        "viewer_type (string), "
                        "artifact_types (list of MIME strings), "
                        "merge_semantics ('ot'|'crdt'|'three_way'), "
                        "supported_commands (list of muse CLI command names)."
                    ),
                },
                "viewer_type": {
                    "type": "string",
                    "description": "Primary viewer identifier (e.g. 'midi', 'code', 'spatial', 'genome').",
                },
                "version": {
                    "type": "string",
                    "description": "Semver string (e.g. '0.1.0').",
                    "default": "0.1.0",
                },
            },
            "required": [
                "author_slug", "slug", "display_name",
                "description", "capabilities", "viewer_type",
            ],
        },
    },
]


# ── Elicitation-powered tools (MCP 2025-11-25) ────────────────────────────────


MUSEHUB_ELICITATION_TOOLS: list[MCPToolDef] = [
    {
        "name": "musehub_create_with_preferences",
        "server_side": True,
        "description": (
            "Interactively create new domain state by collecting user preferences via "
            "form-mode elicitation (MCP 2025-11-25). Currently implements the MIDI domain's "
            "composition workflow — eliciting key signature, tempo, time signature, mood, "
            "genre, reference artist, and duration, then returning a complete composition plan "
            "with chord progressions, section structure, harmonic tension profile, and a "
            "step-by-step Muse project workflow. The elicitation schema will evolve to be "
            "fully domain-aware as additional domain plugins are registered. "
            "ELICITATION BEHAVIOUR: requires an active MCP session (Mcp-Session-Id header). "
            "Without a session the tool still succeeds — it returns a structured JSON prompt "
            "listing every preference field with allowed values and defaults so the caller "
            "can collect the inputs and call again with preferences={...}. "
            "Non-elicitation clients: pass preferences={key_signature, tempo_bpm, "
            "time_signature, mood, genre, reference_artist, duration_bars} to skip elicitation. "
            "Example: musehub_create_with_preferences(repo_id='a3f2-...') "
            "or musehub_create_with_preferences(repo_id='a3f2-...', "
            "preferences={key_signature:'C major', tempo_bpm:120, mood:'uplifting'})."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Optional repository to scaffold the new state into.",
                },
                "preferences": {
                    "type": "object",
                    "description": (
                        "Pre-filled preferences to bypass elicitation. "
                        "Keys: key_signature (e.g. 'C major'), tempo_bpm (int), "
                        "time_signature (e.g. '4/4'), mood (e.g. 'uplifting'), "
                        "genre (e.g. 'jazz'), reference_artist (string), "
                        "duration_bars (int). Omit to trigger interactive elicitation."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_review_pr_interactive",
        "server_side": True,
        "description": (
            "Review a pull request interactively by first eliciting the reviewer's focus "
            "dimension and depth (quick / standard / thorough). Returns a deep structured "
            "review targeting the chosen dimensions with per-dimension divergence scores. "
            "Currently implements the MIDI domain's dimension vocabulary "
            "(melodic / harmonic / rhythmic / structural / dynamic / all). "
            "For repos on other domains, call musehub_get_domain first to learn the correct "
            "dimension names, then pass dimension= directly to skip elicitation. "
            "For a non-interactive review, use musehub_get_pr + musehub_submit_pr_review instead. "
            "ELICITATION BEHAVIOUR: requires an active MCP session (Mcp-Session-Id header). "
            "Without a session, pass dimension= and depth= directly to skip elicitation. "
            "Example: musehub_review_pr_interactive(repo_id='a3f2-...', pr_id='pr-uuid') "
            "or musehub_review_pr_interactive(repo_id='a3f2-...', pr_id='pr-uuid', "
            "dimension='harmonic', depth='thorough')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request to review.",
                },
                "dimension": {
                    "type": "string",
                    "description": (
                        "Focus dimension to bypass elicitation. "
                        "One of: melodic, harmonic, rhythmic, structural, dynamic, all."
                    ),
                    "enum": ["melodic", "harmonic", "rhythmic", "structural", "dynamic", "all"],
                },
                "depth": {
                    "type": "string",
                    "description": "Review depth to bypass elicitation: quick, standard, or thorough.",
                    "enum": ["quick", "standard", "thorough"],
                },
            },
            "required": ["pr_id"],
        },
    },
    {
        "name": "musehub_connect_streaming_platform",
        "server_side": True,
        "description": (
            "Connect a streaming platform account (Spotify, SoundCloud, Bandcamp, YouTube Music, "
            "Apple Music, TIDAL, Amazon Music, Deezer) via URL-mode elicitation (OAuth). "
            "Directs the user to a MuseHub OAuth start page; once authorised, the agent can "
            "distribute Muse releases directly to the platform. "
            "ELICITATION BEHAVIOUR: requires an active MCP session with URL elicitation capability. "
            "Without a session, pass platform= directly to get the OAuth URL returned as text "
            "so the caller can present it manually. "
            "Example: musehub_connect_streaming_platform(platform='Spotify', repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Streaming platform name. Elicited from user if omitted.",
                    "enum": [
                        "Spotify", "SoundCloud", "Bandcamp", "YouTube Music",
                        "Apple Music", "TIDAL", "Amazon Music", "Deezer",
                    ],
                },
                "repo_id": {
                    "type": "string",
                    "description": "Optional repository context for release distribution.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_connect_daw_cloud",
        "server_side": True,
        "description": (
            "Connect a cloud DAW or mastering service (LANDR, Splice, Soundtrap, BandLab, "
            "Audiotool) via URL-mode elicitation (OAuth). Once connected, agents can trigger "
            "cloud renders, stems exports, and AI mastering jobs directly from MuseHub workflows. "
            "ELICITATION BEHAVIOUR: requires an active MCP session with URL elicitation capability. "
            "Without a session, pass service= directly to get the OAuth URL returned as text "
            "so the caller can present it manually. "
            "Example: musehub_connect_daw_cloud(service='LANDR')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Cloud DAW / mastering service name. Elicited if omitted.",
                    "enum": ["LANDR", "Splice", "Soundtrap", "BandLab", "Audiotool"],
                },
            },
            "required": [],
        },
    },
    {
        "name": "musehub_create_release_interactive",
        "server_side": True,
        "description": (
            "Create a release interactively in two chained elicitation steps: "
            "(1) form-mode: collects tag, title, release notes, changelog highlight, "
            "and pre-release flag; "
            "(2) URL-mode (optional): offers streaming platform OAuth connection. "
            "Creates the release then returns distribution guidance for connected platforms. "
            "For a non-interactive release, use musehub_create_release with explicit arguments. "
            "ELICITATION BEHAVIOUR: requires an active MCP session with elicitation capability. "
            "Without a session, pass tag=, title=, notes= directly to bypass elicitation and "
            "create the release immediately (identical to musehub_create_release). "
            "Example: musehub_create_release_interactive(repo_id='a3f2-...') "
            "or musehub_create_release_interactive(repo_id='a3f2-...', "
            "tag='v1.0.0', title='First release', notes='Initial commit')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **_REPO_ID_PROP,
                "tag": {
                    "type": "string",
                    "description": "Semver tag string (e.g. 'v1.0.0'). Elicited if omitted.",
                },
                "title": {
                    "type": "string",
                    "description": "Release title. Elicited if omitted.",
                },
                "notes": {
                    "type": "string",
                    "description": "Release notes markdown. Elicited if omitted.",
                },
                "pre_release": {
                    "type": "boolean",
                    "description": "Whether this is a pre-release. Default: false.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
]


# ── Combined catalogue ────────────────────────────────────────────────────────

MUSEHUB_TOOLS: list[MCPToolDef] = (
    MUSEHUB_READ_TOOLS + MUSEHUB_WRITE_TOOLS + MUSEHUB_ELICITATION_TOOLS
)

MUSEHUB_TOOL_NAMES: set[str] = {t["name"] for t in MUSEHUB_TOOLS}
"""Set of all musehub_* and muse_* tool names — used by the MCP dispatcher to route calls."""

MUSEHUB_WRITE_TOOL_NAMES: set[str] = {
    t["name"] for t in MUSEHUB_WRITE_TOOLS + MUSEHUB_ELICITATION_TOOLS
}
"""Set of write/interactive tool names — requires authentication."""

MUSEHUB_ELICITATION_TOOL_NAMES: set[str] = {t["name"] for t in MUSEHUB_ELICITATION_TOOLS}
"""Set of elicitation-powered tool names — requires active session."""

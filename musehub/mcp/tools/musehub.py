"""MuseHub MCP tool definitions — all 32 tools for AI agents (MCP 2025-11-25).

Covers the full MuseHub surface: reads (15), writes (12), and elicitation-powered
interactive tools (5).

Elicitation-powered tools use the ToolCallContext to collect user preferences
mid-call via the MCP 2025-11-25 elicitation protocol. They require an active
session (``Mcp-Session-Id``) and degrade gracefully without one.

Reads give agents complete browsing power — repos, branches, commits, files,
musical analysis, issues, PRs, releases, and global discovery.

Writes give agents full contribution capability — create repos, open and
manage issues and PRs, merge, publish releases, and build social graphs.

Naming convention:
  ``musehub_<verb>_<noun>`` — distinct from DAW tools which use ``muse_``.

All tools carry ``server_side: True`` so the dispatcher routes them to the
executor layer rather than forwarding to a connected DAW.
"""

from musehub.contracts.mcp_types import MCPToolDef


# ── Read tools ────────────────────────────────────────────────────────────────


MUSEHUB_READ_TOOLS: list[MCPToolDef] = [
    # Existing 7 ─────────────────────────────────────────────────────────────

    {
        "name": "musehub_browse_repo",
        "server_side": True,
        "description": (
            "Get an overview of a MuseHub repository: metadata, branches, and recent commits. "
            "Use this to orient yourself before reading files or analysing commit history. "
            "Example: musehub_browse_repo(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
            },
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_list_branches",
        "server_side": True,
        "description": (
            "List all branches in a MuseHub repository with their head commit IDs. "
            "Call before musehub_list_commits to identify the target branch ref. "
            "Example: musehub_list_branches(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
            },
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_list_commits",
        "server_side": True,
        "description": (
            "List commits on a MuseHub repository (newest first). "
            "Optionally filter by branch name and cap the result count. "
            "Example: musehub_list_commits(repo_id='a3f2-...', branch='main', limit=10)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_read_file",
        "server_side": True,
        "description": (
            "Read the metadata for a stored artifact (MIDI, MP3, WebP piano roll) "
            "in a MuseHub repo. Returns path, size_bytes, mime_type, and object_id. "
            "Binary content is not returned — discover object IDs via musehub_browse_repo first. "
            "Example: musehub_read_file(repo_id='a3f2-...', object_id='sha256:abc...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "object_id": {
                    "type": "string",
                    "description": "Content-addressed object ID (e.g. 'sha256:abc...').",
                },
            },
            "required": ["repo_id", "object_id"],
        },
    },
    {
        "name": "musehub_get_analysis",
        "server_side": True,
        "description": (
            "Get structured analysis for a MuseHub repository. "
            "Dimensions: 'overview' returns repo stats + branch/commit/object counts; "
            "'commits' returns commit activity summary (authors, message samples); "
            "'objects' returns artifact inventory grouped by MIME type. "
            "Example: musehub_get_analysis(repo_id='a3f2-...', dimension='overview')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "dimension": {
                    "type": "string",
                    "description": "Analysis dimension: 'overview', 'commits', or 'objects'.",
                    "enum": ["overview", "commits", "objects"],
                    "default": "overview",
                },
            },
            "required": ["repo_id"],
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
            "Example: musehub_search(repo_id='a3f2-...', query='bass', mode='path')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository to search within.",
                },
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
            "required": ["repo_id", "query"],
        },
    },
    {
        "name": "musehub_get_context",
        "server_side": True,
        "description": (
            "Get the full AI context document for a MuseHub repository. "
            "This is the primary read-side interface for music generation agents: it returns "
            "a structured summary of the repo's musical state — branches, recent commits, "
            "artifact inventory, and repo metadata — in a single call. "
            "Feed this document to the agent before generating new music to ensure "
            "harmonic and structural coherence with existing work. "
            "Example: musehub_get_context(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
            },
            "required": ["repo_id"],
        },
    },

    # New read tools (8) ──────────────────────────────────────────────────────

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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "commit_id": {
                    "type": "string",
                    "description": "Commit ID (SHA or short ID).",
                },
            },
            "required": ["repo_id", "commit_id"],
        },
    },
    {
        "name": "musehub_compare",
        "server_side": True,
        "description": (
            "Compare two refs (branches or commit IDs) in a MuseHub repository. "
            "Returns a musical diff: which artifacts were added, removed, or modified, "
            "and per-dimension change scores (harmony, rhythm, groove) when analysis data is available. "
            "Example: musehub_compare(repo_id='a3f2-...', base_ref='main', head_ref='feature/jazz-bridge')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "base_ref": {
                    "type": "string",
                    "description": "Base branch name or commit ID.",
                },
                "head_ref": {
                    "type": "string",
                    "description": "Head branch name or commit ID to compare against base.",
                },
            },
            "required": ["repo_id", "base_ref", "head_ref"],
        },
    },
    {
        "name": "musehub_list_issues",
        "server_side": True,
        "description": (
            "List issues for a MuseHub repository. "
            "Filter by state (open/closed/all), label string, or assignee. "
            "Example: musehub_list_issues(repo_id='a3f2-...', state='open', label='bug')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_get_issue",
        "server_side": True,
        "description": (
            "Get a single issue by its per-repo number, including the full comment thread. "
            "Example: musehub_get_issue(repo_id='a3f2-...', issue_number=42)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "issue_number": {
                    "type": "integer",
                    "description": "Per-repo issue number.",
                },
            },
            "required": ["repo_id", "issue_number"],
        },
    },
    {
        "name": "musehub_list_prs",
        "server_side": True,
        "description": (
            "List pull requests for a MuseHub repository. "
            "Filter by state (open/merged/closed/all) and/or target branch. "
            "Example: musehub_list_prs(repo_id='a3f2-...', state='open')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "state": {
                    "type": "string",
                    "description": "Filter by state: 'open', 'merged', 'closed', or 'all'.",
                    "enum": ["open", "merged", "closed", "all"],
                    "default": "all",
                },
            },
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_get_pr",
        "server_side": True,
        "description": (
            "Get a single pull request by ID, including reviews and inline comments. "
            "Example: musehub_get_pr(repo_id='a3f2-...', pr_id='b5e8-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request.",
                },
            },
            "required": ["repo_id", "pr_id"],
        },
    },
    {
        "name": "musehub_list_releases",
        "server_side": True,
        "description": (
            "List all releases for a MuseHub repository, ordered newest first. "
            "Each release includes tag, title, release notes, and asset counts. "
            "Example: musehub_list_releases(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
            },
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_search_repos",
        "server_side": True,
        "description": (
            "Discover public MuseHub repositories by text query or musical attributes. "
            "Filter by key signature, tempo range, or free-text tags. "
            "Returns repos sorted by relevance. "
            "Example: musehub_search_repos(query='jazz', tempo_min=120, tempo_max=160)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text query matched against repo names and descriptions.",
                },
                "key_signature": {
                    "type": "string",
                    "description": "Filter by key signature (e.g. 'C major', 'F# minor').",
                },
                "tempo_min": {
                    "type": "integer",
                    "description": "Minimum tempo (BPM) filter.",
                    "minimum": 20,
                    "maximum": 400,
                },
                "tempo_max": {
                    "type": "integer",
                    "description": "Maximum tempo (BPM) filter.",
                    "minimum": 20,
                    "maximum": 400,
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
]


# ── Write tools ───────────────────────────────────────────────────────────────


MUSEHUB_WRITE_TOOLS: list[MCPToolDef] = [
    {
        "name": "musehub_create_repo",
        "server_side": True,
        "description": (
            "Create a new MuseHub repository. "
            "The slug is auto-generated from the name. "
            "Set initialize=true (default) to get an empty initial commit and default branch immediately. "
            "Example: musehub_create_repo(name='Jazz Experiment', visibility='public')."
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
                "tags": {
                    "type": "array",
                    "description": "Musical category tags (e.g. ['jazz', 'bebop']).",
                    "items": {"type": "string"},
                },
                "key_signature": {
                    "type": "string",
                    "description": "Musical key (e.g. 'C major', 'F# minor').",
                },
                "tempo_bpm": {
                    "type": "integer",
                    "description": "Tempo in beats per minute.",
                    "minimum": 20,
                    "maximum": 400,
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
            "Use issues to track musical problems, feature requests, or collaboration needs. "
            "Example: musehub_create_issue(repo_id='a3f2-...', title='Bass too muddy in bars 8-16')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "title"],
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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "issue_number"],
        },
    },
    {
        "name": "musehub_create_issue_comment",
        "server_side": True,
        "description": (
            "Add a comment to an existing issue. "
            "Example: musehub_create_issue_comment(repo_id='a3f2-...', issue_number=42, body='Fixed in commit abc...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "issue_number": {
                    "type": "integer",
                    "description": "Per-repo issue number.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown comment body.",
                },
            },
            "required": ["repo_id", "issue_number", "body"],
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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "title", "from_branch", "to_branch"],
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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "pr_id"],
        },
    },
    {
        "name": "musehub_create_pr_comment",
        "server_side": True,
        "description": (
            "Post a comment on a pull request, optionally anchored to a specific track or beat region. "
            "Use target_type='track' + target_track to reference a named track. "
            "Use target_type='region' + target_track + target_beat_start + target_beat_end for bar-level comments. "
            "Example: musehub_create_pr_comment(repo_id='a3f2-...', pr_id='b5e8-...', "
            "body='This groove feels rushed', target_type='region', target_track='Drums', "
            "target_beat_start=8.0, target_beat_end=12.0)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request.",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown comment body.",
                },
                "target_type": {
                    "type": "string",
                    "description": "Comment anchor: 'general' (PR-level), 'track', or 'region'.",
                    "enum": ["general", "track", "region"],
                    "default": "general",
                },
                "target_track": {
                    "type": "string",
                    "description": "Track name for 'track' or 'region' comments.",
                },
                "target_beat_start": {
                    "type": "number",
                    "description": "Start beat for 'region' comments.",
                },
                "target_beat_end": {
                    "type": "number",
                    "description": "End beat for 'region' comments.",
                },
            },
            "required": ["repo_id", "pr_id", "body"],
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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "pr_id", "event"],
        },
    },
    {
        "name": "musehub_create_release",
        "server_side": True,
        "description": (
            "Publish a new release for a MuseHub repository. "
            "A release pins a version tag to a commit and packages the musical snapshot. "
            "Tags must be unique per repo (e.g. 'v1.0', 'final-mix'). "
            "Example: musehub_create_release(repo_id='a3f2-...', tag='v1.0', title='First Release', "
            "body='Initial jazz session recording.')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
                    "description": "Optional commit UUID to pin this release to.",
                },
                "is_prerelease": {
                    "type": "boolean",
                    "description": "When true, marks as pre-release.",
                    "default": False,
                },
            },
            "required": ["repo_id", "tag", "title"],
        },
    },
    {
        "name": "musehub_star_repo",
        "server_side": True,
        "description": (
            "Star a MuseHub repository to show appreciation and follow its activity. "
            "Starred repos appear in the user's starred list. Idempotent. "
            "Example: musehub_star_repo(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository to star.",
                },
            },
            "required": ["repo_id"],
        },
    },
    {
        "name": "musehub_fork_repo",
        "server_side": True,
        "description": (
            "Fork a public MuseHub repository under the authenticated user's account. "
            "Creates a new repo with all branches and establishes fork lineage. "
            "Only public repos can be forked. "
            "Example: musehub_fork_repo(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the public repository to fork.",
                },
            },
            "required": ["repo_id"],
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
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
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
            "required": ["repo_id", "name", "color"],
        },
    },
]


# ── Elicitation-powered tools (MCP 2025-11-25) ────────────────────────────────


MUSEHUB_ELICITATION_TOOLS: list[MCPToolDef] = [
    {
        "name": "musehub_compose_with_preferences",
        "server_side": True,
        "description": (
            "Interactively compose a musical piece by collecting user preferences via "
            "form-mode elicitation. Asks the user for key signature, tempo, time signature, "
            "mood, genre, reference artist, and duration. Returns a complete composition plan "
            "with chord progressions, section structure, harmonic tension profile, and a "
            "step-by-step Muse project workflow. "
            "Requires an active MCP session with elicitation capability. "
            "Example: musehub_compose_with_preferences(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Optional repository to scaffold the composition into.",
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
            "dimension (melodic / harmonic / rhythmic / structural / dynamic / all) and "
            "depth (quick / standard / thorough). Returns a deep structured review targeting "
            "the user-chosen dimensions with harmonic tension and rhythmic consistency checks. "
            "Requires an active MCP session with elicitation capability. "
            "Example: musehub_review_pr_interactive(repo_id='a3f2-...', pr_id='pr-uuid')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the MuseHub repository.",
                },
                "pr_id": {
                    "type": "string",
                    "description": "UUID of the pull request to review.",
                },
            },
            "required": ["repo_id", "pr_id"],
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
            "Requires an active MCP session with URL elicitation capability. "
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
            "Requires an active MCP session with URL elicitation capability. "
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
            "Requires an active MCP session with elicitation capability. "
            "Example: musehub_create_release_interactive(repo_id='a3f2-...')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "UUID of the repository to create the release in.",
                },
            },
            "required": ["repo_id"],
        },
    },
]


# ── Combined catalogue ────────────────────────────────────────────────────────

MUSEHUB_TOOLS: list[MCPToolDef] = (
    MUSEHUB_READ_TOOLS + MUSEHUB_WRITE_TOOLS + MUSEHUB_ELICITATION_TOOLS
)

MUSEHUB_TOOL_NAMES: set[str] = {t["name"] for t in MUSEHUB_TOOLS}
"""Set of all musehub_* tool names — used by the MCP dispatcher to route calls."""

MUSEHUB_WRITE_TOOL_NAMES: set[str] = {
    t["name"] for t in MUSEHUB_WRITE_TOOLS + MUSEHUB_ELICITATION_TOOLS
}
"""Set of write/interactive tool names — requires authentication."""

MUSEHUB_ELICITATION_TOOL_NAMES: set[str] = {t["name"] for t in MUSEHUB_ELICITATION_TOOLS}
"""Set of elicitation-powered tool names — requires active session."""

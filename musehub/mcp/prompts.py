"""MuseHub MCP Prompt catalogue — workflow-oriented agent guidance.

Prompts teach agents how to chain Tools and Resources to accomplish multi-step
musical collaboration goals on MuseHub.

Six prompts are defined:
  musehub/orientation  — essential onboarding for any new agent
  musehub/contribute   — end-to-end contribution workflow
  musehub/compose      — musical composition workflow
  musehub/review_pr    — musical PR review workflow
  musehub/issue_triage — issue triage workflow
  musehub/release_prep — release preparation workflow
"""
from __future__ import annotations

import json
from typing import TypedDict, Required, NotRequired


# ── Catalogue TypedDicts ──────────────────────────────────────────────────────


class MCPPromptArgument(TypedDict, total=False):
    """A single named argument for an MCP prompt."""

    name: Required[str]
    description: str
    required: bool


class MCPPromptDef(TypedDict, total=False):
    """Definition of a single MCP prompt exposed to agents."""

    name: Required[str]
    description: Required[str]
    arguments: list[MCPPromptArgument]


class MCPPromptMessageContent(TypedDict):
    """The content of a single prompt message."""

    type: str   # always "text"
    text: str


class MCPPromptMessage(TypedDict):
    """A single message in an MCP prompt response."""

    role: str  # "user" or "assistant"
    content: MCPPromptMessageContent


class MCPPromptResult(TypedDict):
    """The result returned by ``prompts/get``."""

    description: str
    messages: list[MCPPromptMessage]


# ── Prompt catalogue ──────────────────────────────────────────────────────────

PROMPT_CATALOGUE: list[MCPPromptDef] = [
    {
        "name": "musehub/orientation",
        "description": (
            "Explains MuseHub's model (repos, commits, branches, musical analysis) "
            "and which tools to use for what. The essential first read for any new agent."
        ),
        "arguments": [],
    },
    {
        "name": "musehub/contribute",
        "description": (
            "End-to-end contribution workflow: discover repo → browse → open issue → "
            "push commit → create PR → request review → merge."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the target repository.",
                "required": True,
            },
            {
                "name": "owner",
                "description": "Repository owner username.",
                "required": False,
            },
            {
                "name": "slug",
                "description": "Repository slug.",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/compose",
        "description": (
            "Musical composition workflow: get context → understand existing tracks → "
            "push new MIDI commit → verify the musical analysis."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository to compose into.",
                "required": True,
            },
        ],
    },
    {
        "name": "musehub/review_pr",
        "description": (
            "Musical PR review: get PR → read musical analysis → compare branches → "
            "submit review with track/region-level comments."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository.",
                "required": True,
            },
            {
                "name": "pr_id",
                "description": "UUID of the pull request to review.",
                "required": True,
            },
        ],
    },
    {
        "name": "musehub/issue_triage",
        "description": (
            "Triage open issues: list → label → assign → link to milestones."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository whose issues to triage.",
                "required": True,
            },
        ],
    },
    {
        "name": "musehub/release_prep",
        "description": (
            "Prepare a release: check merged PRs → write release notes → "
            "create release with version tag."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository to release.",
                "required": True,
            },
        ],
    },
]

PROMPT_NAMES: set[str] = {p["name"] for p in PROMPT_CATALOGUE}


# ── Prompt assembler ──────────────────────────────────────────────────────────


def get_prompt(name: str, arguments: dict[str, str] | None = None) -> MCPPromptResult | None:
    """Assemble a prompt by name, interpolating any provided arguments.

    Args:
        name: Prompt name (e.g. ``"musehub/orientation"``).
        arguments: Dict of argument name → value provided by the MCP client.

    Returns:
        ``MCPPromptResult`` on success, or ``None`` if the prompt name is unknown.
    """
    args = arguments or {}

    if name == "musehub/orientation":
        return _orientation()
    if name == "musehub/contribute":
        return _contribute(args.get("repo_id", ""), args.get("owner", ""), args.get("slug", ""))
    if name == "musehub/compose":
        return _compose(args.get("repo_id", ""))
    if name == "musehub/review_pr":
        return _review_pr(args.get("repo_id", ""), args.get("pr_id", ""))
    if name == "musehub/issue_triage":
        return _issue_triage(args.get("repo_id", ""))
    if name == "musehub/release_prep":
        return _release_prep(args.get("repo_id", ""))
    return None


# ── Individual prompt bodies ──────────────────────────────────────────────────


def _msg(role: str, text: str) -> MCPPromptMessage:
    return {"role": role, "content": {"type": "text", "text": text.strip()}}


def _orientation() -> MCPPromptResult:
    return {
        "description": "MuseHub agent orientation — essential onboarding guide.",
        "messages": [
            _msg("user", "Explain MuseHub and how I should use it as an agent."),
            _msg("assistant", """
# MuseHub Agent Orientation

MuseHub is a Git-like version control platform for music projects (Muse VCS files).
Think of it as GitHub, but for music: repos hold MIDI artifacts, piano-roll images,
and audio files committed in snapshots.

## Core concepts

| Concept  | Description |
|----------|-------------|
| **Repo** | A named project owned by a user. Identified by UUID or {owner}/{slug}. |
| **Branch** | A named pointer to a commit. Default branch is usually `main`. |
| **Commit** | A snapshot of all artifacts at a point in time. Has parent IDs, author, timestamp. |
| **Object** | A content-addressed artifact (MIDI, MP3, WebP). Immutable once stored. |
| **Issue** | A discussion thread for problems, ideas, or tasks. Has a per-repo number. |
| **Pull Request (PR)** | A proposal to merge one branch into another. Has musical diff comments. |
| **Release** | A tagged, published snapshot of a repo (e.g. "v1.0 — Final Mix"). |

## Tool selection guide

### Discovery
- `musehub_search_repos` — find repos by text, key, tempo, or tags
- Resource `musehub://trending` — top repos by star count

### Reading a repo
1. `musehub_browse_repo(repo_id)` — orientation snapshot
2. `musehub_get_context(repo_id)` — full AI context document (best for composition)
3. `musehub_get_analysis(repo_id, dimension='overview')` — musical stats

### Browsing history
- `musehub_list_branches` → `musehub_list_commits` → `musehub_get_commit`
- `musehub_compare(base_ref, head_ref)` for musical diffs between branches

### Issues & PRs
- `musehub_list_issues` / `musehub_get_issue` for reading
- `musehub_create_issue` / `musehub_update_issue` for writing
- `musehub_list_prs` / `musehub_get_pr` for reading
- `musehub_create_pr` / `musehub_merge_pr` for writing

### Social
- `musehub_star_repo` — star a repo you appreciate
- `musehub_fork_repo` — fork to experiment safely

## Resources vs. Tools

| Use | When |
|-----|------|
| **Resource** (`musehub://...`) | Cacheable reads — prefer for repeated lookups |
| **Tool** (`musehub_*`) | Mutations (write tools) or when you need fresh data |

Always call `musehub/orientation` or read `musehub://trending` first to ground yourself
before starting a multi-step task.
"""),
        ],
    }


def _contribute(repo_id: str, owner: str, slug: str) -> MCPPromptResult:
    repo_ref = f"{owner}/{slug}" if owner and slug else repo_id or "<repo_id>"
    return {
        "description": f"End-to-end contribution workflow for {repo_ref}.",
        "messages": [
            _msg("user", f"Walk me through contributing to the MuseHub repository {repo_ref}."),
            _msg("assistant", f"""
# Contribution Workflow for `{repo_ref}`

Follow these steps to contribute a musical change to this repository.

## Step 1 — Orient yourself
```
musehub_browse_repo(repo_id="{repo_id}")
musehub_get_context(repo_id="{repo_id}")
```
Read the repo overview, understand existing branches and recent commits.

## Step 2 — Understand the musical state
```
musehub_get_analysis(repo_id="{repo_id}", dimension="overview")
musehub_get_analysis(repo_id="{repo_id}", dimension="commits")
```
Check the key signature, tempo, instrumentation, and commit history.

## Step 3 — Open an issue (optional but recommended)
```
musehub_create_issue(
    repo_id="{repo_id}",
    title="<describe the musical change you plan>",
    body="<context, what problem does it solve?>",
    labels=["enhancement"]
)
```

## Step 4 — Check branches and list recent commits
```
musehub_list_branches(repo_id="{repo_id}")
musehub_list_commits(repo_id="{repo_id}", branch="main", limit=5)
```
Pick a base commit for your work.

## Step 5 — Create a pull request
After your musical changes are committed to a feature branch:
```
musehub_create_pr(
    repo_id="{repo_id}",
    title="<short description of the change>",
    from_branch="<your-feature-branch>",
    to_branch="main",
    body="<what changed musically and why>"
)
```

## Step 6 — Add PR comments for musical context
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="<pr_id>",
    body="The harmony in bar 8 resolves the tension from bar 4.",
    target_type="region",
    target_track="Piano",
    target_beat_start=28.0,
    target_beat_end=32.0
)
```

## Step 7 — Merge when approved
```
musehub_merge_pr(repo_id="{repo_id}", pr_id="<pr_id>")
```
"""),
        ],
    }


def _compose(repo_id: str) -> MCPPromptResult:
    return {
        "description": f"Musical composition workflow for repo {repo_id or '<repo_id>'}.",
        "messages": [
            _msg("user", f"Guide me through composing new music for repo {repo_id or '<repo_id>'}."),
            _msg("assistant", f"""
# Musical Composition Workflow

## Step 1 — Get full musical context
```
musehub_get_context(repo_id="{repo_id}")
```
This is the most important call. It returns:
- Existing tracks and instrumentation
- Key signature and tempo
- Recent commit messages (compositional intent)
- Artifact inventory (which MIDI files already exist)

Read this carefully before composing anything.

## Step 2 — Understand commit history
```
musehub_list_commits(repo_id="{repo_id}", branch="main", limit=10)
```
Read commit messages to understand the musical arc and direction.

## Step 3 — Check what files exist
```
musehub_get_analysis(repo_id="{repo_id}", dimension="objects")
```
Lists all artifacts grouped by MIME type (MIDI, MP3, WebP).

## Step 4 — Analyse musical dimensions
```
musehub_get_analysis(repo_id="{repo_id}", dimension="overview")
```
Key signature, tempo BPM, star count, and repo stats.

## Step 5 — Compose with coherence
Use the context from steps 1–4 to generate new MIDI content that:
- Matches the established key signature and tempo
- Complements existing tracks harmonically
- Follows the stylistic intent signalled by commit messages

## Step 6 — Push your changes
Create a commit and PR following the `musehub/contribute` prompt workflow.

## Key principle
Always read before you write. `musehub_get_context` is your oracle —
it tells you everything the repo knows about itself.
"""),
        ],
    }


def _review_pr(repo_id: str, pr_id: str) -> MCPPromptResult:
    return {
        "description": f"Musical PR review workflow for PR {pr_id or '<pr_id>'} in {repo_id or '<repo_id>'}.",
        "messages": [
            _msg("user", f"Guide me through reviewing PR {pr_id or '<pr_id>'} in repo {repo_id or '<repo_id>'}."),
            _msg("assistant", f"""
# Musical PR Review Workflow

## Step 1 — Read the PR
```
musehub_get_pr(repo_id="{repo_id}", pr_id="{pr_id}")
```
Read the title, body, and existing comments to understand the proposed change.

## Step 2 — Compare the branches musically
```
musehub_compare(
    repo_id="{repo_id}",
    base_ref="<to_branch>",
    head_ref="<from_branch>"
)
```
This shows which artifacts were added, removed, or modified, and musical diff scores.

## Step 3 — Analyse the head branch
```
musehub_get_analysis(repo_id="{repo_id}", dimension="overview")
musehub_get_context(repo_id="{repo_id}")
```
Understand the full musical state the PR would produce after merge.

## Step 4 — Leave inline musical comments
For track-level feedback:
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    body="The Piano voicing here clashes with the Bass in bar 8.",
    target_type="track",
    target_track="Piano"
)
```

For region-level feedback:
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    body="This section feels rushed — consider lengthening note durations.",
    target_type="region",
    target_track="Drums",
    target_beat_start=16.0,
    target_beat_end=24.0
)
```

## Step 5 — Submit your formal review verdict
```
musehub_submit_pr_review(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    event="approve",       # or "request_changes" or "comment"
    body="<overall review summary>"
)
```

## Review criteria
- Does the new content respect the established key and tempo?
- Do new tracks complement existing ones harmonically?
- Are commit messages descriptive of the musical intent?
- Does the change introduce or resolve tension appropriately?
"""),
        ],
    }


def _issue_triage(repo_id: str) -> MCPPromptResult:
    return {
        "description": f"Issue triage workflow for repo {repo_id or '<repo_id>'}.",
        "messages": [
            _msg("user", f"Help me triage issues for repo {repo_id or '<repo_id>'}."),
            _msg("assistant", f"""
# Issue Triage Workflow

## Step 1 — List all open issues
```
musehub_list_issues(repo_id="{repo_id}", state="open")
```

## Step 2 — For each issue, read the detail
```
musehub_get_issue(repo_id="{repo_id}", issue_number=<number>)
```

## Step 3 — Categorise and label
Apply labels to classify each issue:
```
musehub_update_issue(
    repo_id="{repo_id}",
    issue_number=<number>,
    labels=["bug", "harmonic-issue"]   # e.g.
)
```
Common musical labels:
- `bug` — unintended dissonance, incorrect notes, timing issues
- `enhancement` — requested new instruments, sections, or styles
- `documentation` — unclear commit messages or README
- `harmonic-issue` — key/chord conflicts
- `rhythmic-issue` — timing or groove problems

## Step 4 — Assign to contributors
```
musehub_update_issue(
    repo_id="{repo_id}",
    issue_number=<number>,
    assignee="<username>"
)
```

## Step 5 — Close stale or resolved issues
```
musehub_update_issue(
    repo_id="{repo_id}",
    issue_number=<number>,
    state="closed"
)
```

## Step 6 — Add triage comments
```
musehub_create_issue_comment(
    repo_id="{repo_id}",
    issue_number=<number>,
    body="Triaged: this is a harmonic conflict in the bridge section (bars 24-32)."
)
```
"""),
        ],
    }


def _release_prep(repo_id: str) -> MCPPromptResult:
    return {
        "description": f"Release preparation workflow for repo {repo_id or '<repo_id>'}.",
        "messages": [
            _msg("user", f"Help me prepare a release for repo {repo_id or '<repo_id>'}."),
            _msg("assistant", f"""
# Release Preparation Workflow

## Step 1 — Review what's been merged since last release
```
musehub_list_releases(repo_id="{repo_id}")
musehub_list_prs(repo_id="{repo_id}", state="merged")
```
Identify all merged PRs since the last release tag.

## Step 2 — Get the latest commit on main
```
musehub_list_commits(repo_id="{repo_id}", branch="main", limit=5)
```
Note the most recent `commit_id` to pin the release.

## Step 3 — Analyse the current musical state
```
musehub_get_analysis(repo_id="{repo_id}", dimension="overview")
musehub_get_context(repo_id="{repo_id}")
```
Summarise the musical content for the release notes.

## Step 4 — Draft release notes
Release notes should include:
- **What's new** — new instruments, sections, or musical themes added
- **What changed** — harmonic or structural revisions
- **What was fixed** — resolved dissonances, timing corrections
- **Known issues** — anything still in progress

## Step 5 — Publish the release
```
musehub_create_release(
    repo_id="{repo_id}",
    tag="v<major>.<minor>",          # e.g. "v1.0"
    title="<release title>",          # e.g. "Final Mix — Jazz Suite v1.0"
    body="<release notes markdown>",
    commit_id="<latest_commit_id>",
    is_prerelease=False
)
```

## Versioning convention
- `v0.x` — work in progress / drafts
- `v1.0` — first complete composition
- `v1.x` — revisions and fixes
- `v2.0` — major structural rework
"""),
        ],
    }

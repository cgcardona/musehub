"""MuseHub MCP Prompt catalogue — workflow-oriented agent guidance.

Prompts teach agents how to chain Tools and Resources to accomplish multi-step
collaboration goals on MuseHub across any Muse domain.

Eleven prompts are defined:
  musehub/orientation       — essential onboarding for any new agent (domain-agnostic)
  musehub/contribute        — end-to-end contribution workflow
  musehub/create            — create new domain state (replaces musehub/compose)
  musehub/review_pr         — dimension-aware PR review workflow
  musehub/issue_triage      — issue triage workflow
  musehub/release_prep      — release preparation workflow
  musehub/onboard           — interactive creator onboarding (elicitation-aware, 2025-11-25)
  musehub/release_to_world  — full elicitation-powered release + distribution pipeline
  musehub/domain-discovery  — discover and evaluate Muse domain plugins
  musehub/domain-authoring  — build and publish a new Muse domain plugin
  musehub/agent-onboard     — onboard an AI agent as a first-class Muse citizen
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
            "Explains MuseHub's model (repos, commits, branches, domains, multidimensional state) "
            "and which tools to use for what. The essential first read for any new agent or human."
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
        "name": "musehub/create",
        "description": (
            "Domain-agnostic state creation workflow: get context → understand existing "
            "dimensions → push new state commit → verify via domain insights. "
            "Works for any Muse domain (MIDI, Code, Genomics, etc.)."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository to create state in.",
                "required": True,
            },
            {
                "name": "domain",
                "description": "Domain scoped ID (e.g. '@cgcardona/midi'). Auto-resolved from repo if omitted.",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/review_pr",
        "description": (
            "Dimension-aware PR review: get PR → read domain insights → compare branches → "
            "submit review with dimension_ref-anchored comments."
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
    {
        "name": "musehub/onboard",
        "description": (
            "Interactive creator onboarding (MCP 2025-11-25 elicitation-aware). "
            "Guides a new MuseHub creator through: profile setup → domain selection "
            "(via musehub_list_domains) → first repo creation → initial state scaffold "
            "→ optional cloud integration. "
            "Requires an active session with elicitation capability."
        ),
        "arguments": [
            {
                "name": "username",
                "description": "MuseHub username of the creator being onboarded.",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/release_to_world",
        "description": (
            "Full elicitation-powered release and distribution pipeline (MCP 2025-11-25). "
            "Step 1: interactively create a release via musehub_create_release_interactive "
            "(form-mode for metadata). "
            "Step 2: connect streaming platforms via musehub_connect_streaming_platform "
            "(URL-mode OAuth). "
            "Step 3: distribute and share the release across all connected services. "
            "Requires an active session with elicitation capability."
        ),
        "arguments": [
            {
                "name": "repo_id",
                "description": "UUID of the repository to release.",
                "required": True,
            },
        ],
    },
    {
        "name": "musehub/domain-discovery",
        "description": (
            "Guide for discovering, evaluating, and selecting a Muse domain plugin. "
            "Covers: listing domains → reading manifests → understanding capabilities "
            "(dimensions, viewer, merge semantics, CLI commands) → choosing the right "
            "domain for a given use case."
        ),
        "arguments": [
            {
                "name": "use_case",
                "description": "Optional description of what you want to version-control.",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/domain-authoring",
        "description": (
            "End-to-end guide for building and publishing a new Muse domain plugin. "
            "Covers: designing dimensions → writing the domain manifest → implementing "
            "the viewer and merge semantics → publishing to MuseHub via the domains API "
            "→ verifying the manifest hash."
        ),
        "arguments": [
            {
                "name": "domain_name",
                "description": "Name of the domain you want to build (e.g. 'Genomics', 'Circuit Design').",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/agent-onboard",
        "description": (
            "Onboard an AI agent as a first-class Muse citizen (MCP 2025-11-25). "
            "Covers: authenticating with an agent JWT → reading the MCP resource catalogue "
            "→ discovering domains → creating or forking a repo → running the first "
            "read-modify-commit cycle → understanding rate limits and agent-specific claims."
        ),
        "arguments": [
            {
                "name": "agent_name",
                "description": "Identifier or name of the agent being onboarded.",
                "required": False,
            },
            {
                "name": "domain",
                "description": "Domain scoped ID the agent will primarily work with.",
                "required": False,
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
    if name in ("musehub/create", "musehub/compose"):
        return _create(args.get("repo_id", ""), args.get("domain", ""))
    if name == "musehub/review_pr":
        return _review_pr(args.get("repo_id", ""), args.get("pr_id", ""))
    if name == "musehub/issue_triage":
        return _issue_triage(args.get("repo_id", ""))
    if name == "musehub/release_prep":
        return _release_prep(args.get("repo_id", ""))
    if name == "musehub/onboard":
        return _onboard(args.get("username", ""))
    if name == "musehub/release_to_world":
        return _release_to_world(args.get("repo_id", ""))
    if name == "musehub/domain-discovery":
        return _domain_discovery(args.get("use_case", ""))
    if name == "musehub/domain-authoring":
        return _domain_authoring(args.get("domain_name", ""))
    if name == "musehub/agent-onboard":
        return _agent_onboard(args.get("agent_name", ""), args.get("domain", ""))
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

MuseHub is the collaboration hub for **Muse** — the world's first domain-agnostic,
multi-dimensional version control system. Where Git tracks text files, Muse tracks
*multidimensional state* across any domain: MIDI (21 dimensions), Code (10 languages),
Genomics, Circuit Design, 3D scenes, and any custom domain you can define.

Think of MuseHub as GitHub, but for multidimensional state — and built from day one
for both humans and AI agents as first-class citizens.

## Core concepts

| Concept  | Description |
|----------|-------------|
| **Repo** | A named project owned by a user. Identified by UUID or {owner}/{slug}. |
| **Domain** | A plugin that defines the state model for a repo. Scoped as `@author/slug`. |
| **Branch** | A named pointer to a commit. Default branch is usually `main`. |
| **Commit** | A snapshot of all multidimensional state at a point in time. |
| **Object** | A content-addressed artifact. Immutable once stored. |
| **Issue** | A discussion thread for problems, ideas, or tasks. |
| **Pull Request (PR)** | A proposal to merge one branch into another. Supports dimension_ref-anchored comments. |
| **Release** | A tagged, published snapshot of a repo. |
| **dimension_ref** | A domain-defined JSON pointer to a specific location in multidimensional state. |

## Tool selection guide

### Discovery
- `musehub_search_repos` — find repos by text, domain, or tags
- `musehub_list_domains` — browse all available domain plugins
- `musehub_get_domain` — fetch a domain's full capability manifest
- Resource `musehub://trending` — top repos by star count
- Resource `muse://domains` — full domain registry

### Reading a repo
1. `musehub_browse_repo(repo_id)` — orientation snapshot
2. `musehub_get_context(repo_id)` — full AI context document
3. `musehub_get_domain_insights(repo_id, dimension='overview')` — cross-domain stats
4. `musehub_get_view(repo_id, ref='main')` — full multidimensional state payload

### Browsing history
- `musehub_list_branches` → `musehub_list_commits` → `musehub_get_commit`
- `musehub_compare(base_ref, head_ref)` for multidimensional state diffs

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
| **Resource** (`musehub://...`, `muse://...`) | Cacheable reads — prefer for repeated lookups |
| **Tool** (`musehub_*`) | Mutations (write tools) or when you need fresh data |

## Muse documentation resources

| URI | Content |
|-----|---------|
| `muse://docs/overview` | What Muse is and its paradigm shift |
| `muse://docs/protocol` | Muse protocol specification |
| `muse://docs/crdt` | CRDT merge semantics |
| `muse://docs/domains` | Domain plugin authoring guide |
| `muse://docs/merge` | Merge algorithm deep dive |

Always read `musehub/orientation` or fetch `musehub://trending` first to ground yourself.
For domain-specific work, call `musehub_get_domain` before creating any state.
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

Follow these steps to contribute a change to this repository.

## Step 1 — Orient yourself
```
musehub_browse_repo(repo_id="{repo_id}")
musehub_get_context(repo_id="{repo_id}")
```
Read the repo overview, understand existing branches, recent commits, and the domain.

## Step 2 — Understand the current state
```
musehub_get_domain_insights(repo_id="{repo_id}", dimension="overview")
musehub_get_view(repo_id="{repo_id}", ref="main")
```
Check the domain dimensions, state structure, and commit history.

## Step 3 — Open an issue (optional but recommended)
```
musehub_create_issue(
    repo_id="{repo_id}",
    title="<describe the state change you plan>",
    body="<context, what problem does it solve?>",
    labels=["enhancement"]
)
```

## Step 4 — Check branches and list recent commits
```
musehub_list_branches(repo_id="{repo_id}")
musehub_list_commits(repo_id="{repo_id}", branch="main", limit=5)
```

## Step 5 — Create a pull request
After your changes are committed to a feature branch:
```
musehub_create_pr(
    repo_id="{repo_id}",
    title="<short description of the change>",
    from_branch="<your-feature-branch>",
    to_branch="main",
    body="<what changed and why>"
)
```

## Step 6 — Add dimension-anchored PR comments
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="<pr_id>",
    body="Unexpected state divergence in this region.",
    dimension_ref={{"dimension": "<dim_name>", "<key>": "<value>"}}
)
```
The shape of `dimension_ref` is defined by the repo's domain plugin.
Call `musehub_get_domain` to learn the available dimensions and their ref schemas.

## Step 7 — Merge when approved
```
musehub_merge_pr(repo_id="{repo_id}", pr_id="<pr_id>")
```
"""),
        ],
    }


def _create(repo_id: str, domain: str) -> MCPPromptResult:
    rid = repo_id or "<repo_id>"
    domain_hint = f" (domain: `{domain}`)" if domain else ""
    return {
        "description": f"Domain-agnostic state creation workflow for repo {rid}{domain_hint}.",
        "messages": [
            _msg("user", f"Guide me through creating new state for repo {rid}{domain_hint}."),
            _msg("assistant", f"""
# State Creation Workflow{domain_hint}

Muse is domain-agnostic — this workflow works for any domain: MIDI, Code, Genomics,
Circuit Design, or any custom domain plugin.

## Step 1 — Get full context
```
musehub_get_context(repo_id="{rid}")
```
This is the most important call. It returns:
- Domain plugin (scoped_id, capabilities, dimensions)
- Existing state structure and commit history
- Artifact inventory

Read this carefully before creating anything.

## Step 2 — Understand the domain's capabilities
```
musehub_get_domain(scoped_id="<domain_scoped_id>")
```
This reveals:
- `dimensions` — the axes of state this domain tracks
- `viewer_type` — how state is visualised
- `merge_semantics` — how conflicts are resolved
- `cli_commands` — domain-specific Muse CLI operations
- `artifact_types` — what file types the domain produces

## Step 3 — Inspect the current state
```
musehub_get_view(repo_id="{rid}", ref="main")
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
```
Understand what already exists across all dimensions before adding new state.

## Step 4 — Analyse specific dimensions
```
musehub_get_domain_insights(repo_id="{rid}", dimension="<dimension_name>")
```
Replace `<dimension_name>` with a dimension from the domain's capabilities list.

## Step 5 — Create with coherence
Use the context from steps 1–4 to generate new state that:
- Respects the domain's dimensional structure
- Complements existing state without introducing conflicts
- Follows the intent signalled by prior commit messages

## Step 6 — Push your changes
Create a commit and PR following the `musehub/contribute` prompt workflow.

## Key principle
Always read before you write. `musehub_get_context` and `musehub_get_domain` are your
oracles — they tell you everything the repo and its domain know about themselves.
"""),
        ],
    }


def _review_pr(repo_id: str, pr_id: str) -> MCPPromptResult:
    return {
        "description": f"Dimension-aware PR review workflow for PR {pr_id or '<pr_id>'} in {repo_id or '<repo_id>'}.",
        "messages": [
            _msg("user", f"Guide me through reviewing PR {pr_id or '<pr_id>'} in repo {repo_id or '<repo_id>'}."),
            _msg("assistant", f"""
# Dimension-Aware PR Review Workflow

## Step 1 — Read the PR
```
musehub_get_pr(repo_id="{repo_id}", pr_id="{pr_id}")
```
Read the title, body, and existing comments to understand the proposed state change.

## Step 2 — Learn the domain's dimensions
```
musehub_get_context(repo_id="{repo_id}")
```
This reveals which domain plugin the repo uses and what dimensions are available
for anchored review comments.

## Step 3 — Compare the branches across dimensions
```
musehub_compare(
    repo_id="{repo_id}",
    base_ref="<to_branch>",
    head_ref="<from_branch>"
)
```
Returns per-dimension change scores and a list of modified artifacts.

## Step 4 — Inspect domain insights on the head branch
```
musehub_get_domain_insights(repo_id="{repo_id}", dimension="overview")
musehub_get_view(repo_id="{repo_id}", ref="<from_branch>")
```
Understand the full multidimensional state the PR would produce after merge.

## Step 5 — Leave dimension-anchored comments

For general feedback:
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    body="<general comment about the state change>"
)
```

For dimension-specific feedback, pass a `dimension_ref` matching the domain's schema.
Example for a MIDI domain:
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    body="Unexpected harmonic tension introduced here.",
    dimension_ref={{"dimension": "harmonic", "track": "Piano", "beat_start": 16.0, "beat_end": 24.0}}
)
```
Example for a Code domain:
```
musehub_create_pr_comment(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    body="This function has O(n²) complexity — consider a hash map.",
    dimension_ref={{"dimension": "syntax", "file": "src/search.py", "line_start": 42, "line_end": 55}}
)
```

## Step 6 — Submit your formal review verdict
```
musehub_submit_pr_review(
    repo_id="{repo_id}",
    pr_id="{pr_id}",
    event="approve",       # or "request_changes" or "comment"
    body="<overall review summary>"
)
```

## Review criteria (domain-agnostic)
- Does the new state respect the domain's dimensional constraints?
- Does it integrate cleanly with existing state (no merge conflicts)?
- Are commit messages descriptive of the intent?
- Do the per-dimension change scores match the stated scope of the PR?
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
    labels=["bug", "state-conflict"]   # e.g.
)
```
Common labels:
- `bug` — incorrect or unintended state
- `enhancement` — requested new dimensions or capabilities
- `documentation` — unclear commit messages or README
- `state-conflict` — merge conflict across dimensions
- `performance` — slow renders or large artifact sizes

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
    body="Triaged: state conflict in dimension X between commits Y and Z."
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

## Step 3 — Analyse the current state
```
musehub_get_domain_insights(repo_id="{repo_id}", dimension="overview")
musehub_get_context(repo_id="{repo_id}")
```
Summarise the multidimensional state content for the release notes.

## Step 4 — Draft release notes
Release notes should include:
- **What's new** — new dimensions, artifacts, or state structures added
- **What changed** — revisions to existing state
- **What was fixed** — resolved conflicts or incorrect state
- **Known issues** — anything still in progress

## Step 5 — Publish the release
```
musehub_create_release(
    repo_id="{repo_id}",
    tag="v<major>.<minor>",
    title="<release title>",
    body="<release notes markdown>",
    commit_id="<latest_commit_id>",
    is_prerelease=False
)
```

## Versioning convention
- `v0.x` — work in progress / drafts
- `v1.0` — first complete state snapshot
- `v1.x` — revisions and fixes
- `v2.0` — major structural rework
"""),
        ],
    }


def _onboard(username: str) -> MCPPromptResult:
    creator = username or "the creator"
    return {
        "description": "Interactive creator onboarding with elicitation (MCP 2025-11-25)",
        "messages": [
            _msg("user", f"Help me onboard {creator} to MuseHub as a new creator."),
            _msg("assistant", f"""\
# MuseHub Creator Onboarding — Elicitation-Powered

Welcome! I'll guide {creator} through a fully interactive onboarding using MCP elicitation.
This requires an active session with elicitation support.

## Phase 1 — Discover available domains

```
musehub_list_domains(verified=true)
```

Browse the domain registry to find the right plugin for {creator}'s use case.
Each domain unlocks a different set of dimensions, a specialised viewer, and
domain-specific CLI commands.

## Phase 2 — Create the first repository

```
musehub_create_repo(
    name="<project name>",
    domain="<@author/slug from Phase 1>",
    visibility="public"
)
```

Optionally use `musehub_compose_with_preferences()` to interactively scaffold
the initial state via elicitation.

## Phase 3 — Explore the state viewer

```
musehub_get_view(repo_id="<new_repo>", ref="main")
musehub_get_domain_insights(repo_id="<new_repo>", dimension="overview")
```

## Phase 4 — Connect integrations (optional)

```
musehub_connect_daw_cloud()
```

Uses URL-mode elicitation to connect cloud rendering or export services.

## Phase 5 — Set up collaboration

```
musehub_search_repos(query="<similar domain or topic>")
musehub_star_repo(repo_id="<discovered_repo>")
musehub_create_issue(repo_id="<new_repo>", title="Collaboration opportunity", body="...")
```

## You're set!
{creator} now has:
- A domain-associated repo with the right dimensional structure
- Domain insights and the universal state viewer
- A path to collaboration and integration
"""),
        ],
    }


def _release_to_world(repo_id: str) -> MCPPromptResult:
    rid = repo_id or "<repo_id>"
    return {
        "description": "Full elicitation-powered release + distribution pipeline (MCP 2025-11-25)",
        "messages": [
            _msg("user", f"I want to release and distribute repo {rid} to the world."),
            _msg("assistant", f"""\
# Release to the World — Elicitation Pipeline

I'll walk you through an interactive, elicitation-powered release and distribution
workflow using MCP 2025-11-25 features. Each step collects your input and then acts.

## Step 1 — Review the current state

```
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
musehub_list_prs(repo_id="{rid}", state="merged")
musehub_list_releases(repo_id="{rid}")
```

## Step 2 — Create the release interactively

```
musehub_create_release_interactive(repo_id="{rid}")
```

This tool uses **chained elicitation**:

**Form elicitation (Step 2a):** Collects:
- Release tag (e.g. `v1.0.0`)
- Release title
- Release notes / changelog
- Highlight sentence
- Whether it's a pre-release

**URL elicitation (Step 2b, optional):** Offers OAuth connection for distribution.

## Step 3 — Connect streaming or distribution platforms

```
musehub_connect_streaming_platform(repo_id="{rid}")
```

Each platform requires URL-mode elicitation (OAuth browser flow).

## Step 4 — Connect cloud processing (optional)

```
musehub_connect_daw_cloud(service="LANDR")
```

## Step 5 — Share and promote

```
musehub_create_issue(
    repo_id="{rid}",
    title="Released: <title>",
    body="Release notes + distribution links..."
)
```

Tag it with `release` and `announcement` labels to notify followers.

## Versioning reminder
- `v1.0` — debut release
- `v1.x` — polish and fixes post-debut
- `v2.0` — major new direction

Your release is now live on MuseHub and distributed to connected platforms.
"""),
        ],
    }


def _domain_discovery(use_case: str) -> MCPPromptResult:
    use_case_hint = f" for: {use_case}" if use_case else ""
    return {
        "description": f"Guide for discovering and selecting a Muse domain plugin{use_case_hint}.",
        "messages": [
            _msg("user", f"Help me find the right Muse domain plugin{use_case_hint}."),
            _msg("assistant", f"""\
# Muse Domain Discovery Guide{use_case_hint}

Muse domains are the extensibility layer that make Muse domain-agnostic.
Each domain plugin defines its own dimensional state model, viewer, merge semantics,
and CLI commands. Here's how to find the right one.

## Step 1 — List all available domains

```
musehub_list_domains(verified=true, limit=20)
```

Or search by keyword:
```
musehub_list_domains(query="{use_case or '<your use case>'}")
```

Each result includes:
- `scoped_id` — unique `@author/slug` identifier
- `display_name` — human-readable name
- `description` — what kind of state this domain tracks
- `repo_count` — how many public repos use it
- `install_count` — community adoption signal
- `viewer_type` — how state is visualised

## Step 2 — Read a domain's full manifest

```
musehub_get_domain(scoped_id="@author/slug")
```

Or fetch as a resource (cacheable):
```
muse://domains/@author/slug
```

This reveals:
| Field | What it tells you |
|-------|-------------------|
| `dimensions` | The axes of state the domain tracks (e.g. harmonic, rhythmic, melodic) |
| `viewer_type` | How state is rendered (piano_roll, code_graph, generic) |
| `merge_semantics` | How conflicts across dimensions are resolved |
| `cli_commands` | Domain-specific `muse` CLI subcommands |
| `artifact_types` | What file types commits produce |
| `manifest_hash` | Content-addressed SHA-256 — immutable identity |

## Step 3 — Evaluate fit

Ask yourself:
1. Do the `dimensions` map to the axes of variation in your data?
2. Does the `merge_semantics` strategy work for collaborative edits?
3. Are there enough repos using it (social proof)?
4. Is it verified by the MuseHub team?

## Step 4 — Create a repo with the chosen domain

```
musehub_create_repo(
    name="<project name>",
    domain="@author/slug",
    visibility="public"
)
```

## Currently available domains

| Scoped ID | Dimensions | Viewer |
|-----------|-----------|--------|
| `@cgcardona/midi` | harmonic, rhythmic, melodic, structural, dynamic (+16 more) | piano_roll |
| `@cgcardona/code` | syntax, semantics, types, tests, docs, complexity (+4 more) | code_graph |

Discover more via `musehub_list_domains()`.
"""),
        ],
    }


def _domain_authoring(domain_name: str) -> MCPPromptResult:
    name_hint = domain_name or "your domain"
    return {
        "description": f"End-to-end guide for building and publishing the '{name_hint}' Muse domain plugin.",
        "messages": [
            _msg("user", f"Help me build and publish a new Muse domain plugin called '{name_hint}'."),
            _msg("assistant", f"""\
# Muse Domain Authoring Guide: '{name_hint}'

Muse domains are plugins that extend Muse with new state models. Building a domain
means defining: what dimensions of state you track, how they merge, how they're
visualised, and what CLI commands operators get.

## Step 1 — Design your dimensions

A dimension is one axis of variation in your state. Think about:
- What properties of your data change independently?
- Which changes can be merged automatically vs. requiring human resolution?

Example for a Genomics domain:
```json
[
  "sequence",      // nucleotide sequence data
  "annotation",    // gene/feature annotations
  "expression",    // expression level data
  "variant",       // SNP/indel calls
  "alignment"      // read alignments
]
```

## Step 2 — Define your domain manifest

The manifest is a JSON object that fully describes your domain:
```json
{{
  "display_name": "{name_hint}",
  "description": "Version control for <what you're tracking>.",
  "version": "0.1.0",
  "dimensions": ["<dim1>", "<dim2>", "..."],
  "viewer_type": "generic",        // or "piano_roll", "code_graph", or your custom type
  "merge_semantics": "crdt",       // "crdt", "last_write_wins", or "manual"
  "cli_commands": ["init", "diff", "<domain-specific-commands>"],
  "artifact_types": ["<mime/type>", "..."]
}}
```

## Step 3 — Compute the manifest hash

The manifest hash is a content-addressed SHA-256 of your manifest JSON.
It serves as the immutable identity of your domain version.

In Python:
```python
import hashlib, json
manifest = {{...}}  # your manifest dict
manifest_hash = hashlib.sha256(
    json.dumps(manifest, sort_keys=True).encode()
).hexdigest()
```

## Step 4 — Publish to MuseHub

```
POST /api/v1/domains
{{
  "display_name": "{name_hint}",
  "description": "...",
  "version": "0.1.0",
  "dimensions": [...],
  "viewer_type": "generic",
  "merge_semantics": "crdt",
  "cli_commands": [...],
  "artifact_types": [...]
}}
```

This returns your domain's `domain_id` (UUID) and `scoped_id` (`@you/{name_hint.lower().replace(' ', '-')}`).

## Step 5 — Verify publication

```
musehub_get_domain(scoped_id="@<your_username>/<slug>")
```

Check that:
- `manifest_hash` matches what you computed in Step 3
- All `capabilities` fields are correct
- `scoped_id` is what you expect

## Step 6 — Create your first repo using the new domain

```
musehub_create_repo(
    name="<test project>",
    domain="@<your_username>/<slug>",
    visibility="public"
)
```

## Step 7 — Iterate and version

When you update the manifest, publish a new version. The old manifest_hash
remains valid — repos using it continue to work. New repos can opt into the new version.

## Best practices
- Keep dimensions orthogonal (each dimension should be independently modifiable)
- Use `crdt` merge semantics where possible — it enables automatic merges
- Document CLI commands thoroughly so agents can use them via MCP tools
- Start with `verified=false`; apply for verification once you have community adoption
"""),
        ],
    }


def _agent_onboard(agent_name: str, domain: str) -> MCPPromptResult:
    agent = agent_name or "the agent"
    domain_hint = f" (primary domain: `{domain}`)" if domain else ""
    return {
        "description": f"Onboarding guide for {agent} as a first-class Muse citizen{domain_hint}.",
        "messages": [
            _msg("user", f"Help me onboard {agent} to MuseHub as an AI agent{domain_hint}."),
            _msg("assistant", f"""\
# Agent Onboarding — First-Class Muse Citizen{domain_hint}

MuseHub and Muse treat AI agents as first-class citizens from day one.
This guide walks {agent} through everything needed to operate fully and autonomously.

## Step 1 — Authenticate with an agent JWT

Agent tokens carry additional claims that unlock higher rate limits and agent-specific
activity tracking. Authenticate via:
- `POST /api/v1/auth/token` with `token_type: "agent"` claim in the payload
- Or use the existing OAuth flow; agent-type JWTs are automatically detected

## Step 2 — Discover the MCP entry point

Any MuseHub HTML page exposes the MCP endpoint in its `<head>`:
```html
<link rel="muse-mcp" href="https://musehub.com/mcp">
<link rel="muse-resource" href="muse://docs/overview">
```

Connect to the MCP server at `/mcp` using Streamable HTTP (MCP 2025-11-25).

## Step 3 — Read the resource catalogue

```
muse://docs/overview      — What Muse is
muse://docs/protocol      — Muse protocol specification
muse://docs/domains       — Domain plugin authoring
muse://domains            — Full domain registry (JSON)
musehub://trending        — Top repos right now
```

## Step 4 — Discover domains relevant to your task

```
musehub_list_domains(query="{domain or '<your task domain>'}", verified=true)
musehub_get_domain(scoped_id="{domain or '@author/slug'}")
```

Understanding the domain manifest is essential before creating any state.

## Step 5 — Create or fork a repo

```
# New repo
musehub_create_repo(
    name="<agent project name>",
    domain="{domain or '@author/slug'}",
    visibility="public"
)

# Or fork an existing one
musehub_fork_repo(repo_id="<source_repo_id>")
```

## Step 6 — Run your first read-modify-commit cycle

```
# Read
musehub_get_context(repo_id="<repo_id>")
musehub_get_view(repo_id="<repo_id>", ref="main")

# Modify (generate new state artifacts using domain's dimensional model)

# Commit via PR
musehub_create_pr(
    repo_id="<repo_id>",
    title="Agent: <description of change>",
    from_branch="<agent-branch>",
    to_branch="main",
    body="<what changed and why>"
)
```

## Step 7 — Use dimension_ref for precise PR comments

When leaving review comments, always anchor to a specific dimension ref:
```
musehub_create_pr_comment(
    repo_id="<repo_id>",
    pr_id="<pr_id>",
    body="<agent observation>",
    dimension_ref={{"dimension": "<dim>", "<key>": "<value>"}}
)
```

## Rate limits and agent behaviour

- Agent JWTs receive a higher base rate limit tier
- Agent activity appears in the repository event stream with an "agent" badge
- Prefer **read resources** over tools for repeated lookups (resources are cacheable)
- Always read before writing — `musehub_get_context` is your oracle

## Tools summary for agents

| Goal | Tool |
|------|------|
| Discover domains | `musehub_list_domains`, `musehub_get_domain` |
| Read repo state | `musehub_get_context`, `musehub_get_view`, `musehub_get_domain_insights` |
| Compare state | `musehub_compare` |
| Create state | `musehub_create_repo`, commit via PR workflow |
| Review changes | `musehub_get_pr`, `musehub_create_pr_comment`, `musehub_submit_pr_review` |

{agent} is now a first-class Muse citizen.
"""),
        ],
    }

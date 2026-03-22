"""MuseHub MCP Prompt catalogue — workflow-oriented agent guidance.

Prompts teach agents how to chain Tools and Resources to accomplish multi-step
collaboration goals on MuseHub across any Muse domain.

Ten prompts are defined:
  musehub/orientation       — essential onboarding for any caller; pass caller_type='agent' for agent-specific guidance
  musehub/contribute        — end-to-end contribution workflow including authentication and push setup
  musehub/create            — create new domain state (domain-agnostic)
  musehub/review_pr         — dimension-aware PR review workflow
  musehub/issue_triage      — issue triage workflow
  musehub/release_prep      — release preparation workflow
  musehub/onboard           — interactive creator onboarding (elicitation-aware, 2025-11-25)
  musehub/release_to_world  — full elicitation-powered release + distribution pipeline
  musehub/domain-discovery  — discover and evaluate Muse domain plugins
  musehub/domain-authoring  — build and publish a new Muse domain plugin
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
            "and which tools to use for what. The essential first read for any new caller. "
            "Pass caller_type='agent' for agent-specific guidance including JWT auth, "
            "rate limits, agent onboarding, and the read-modify-commit cycle."
        ),
        "arguments": [
            {
                "name": "caller_type",
                "description": "Caller type: 'human' (default) or 'agent'. Tailors the orientation content.",
                "required": False,
            },
        ],
    },
    {
        "name": "musehub/contribute",
        "description": (
            "End-to-end contribution workflow: authenticate → set up remote → "
            "discover repo → orient via get_context → open issue → "
            "push commit → create PR → request review → merge. "
            "Includes push setup (auth, remote config, muse_push) as a prerequisite step."
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
                "description": "Domain scoped ID (e.g. '@gabriel/midi'). Auto-resolved from repo if omitted.",
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
            "the viewer and merge semantics → publishing to MuseHub via musehub_publish_domain "
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
        return _orientation(args.get("caller_type", "human"))
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
    return None


# ── Individual prompt bodies ──────────────────────────────────────────────────


def _msg(role: str, text: str) -> MCPPromptMessage:
    return {"role": role, "content": {"type": "text", "text": text.strip()}}


def _orientation(caller_type: str = "human") -> MCPPromptResult:
    is_agent = caller_type == "agent"
    description = (
        "MuseHub agent orientation — essential onboarding guide (agent edition)."
        if is_agent else
        "MuseHub orientation — essential onboarding guide."
    )

    agent_section = """
## Agent-specific guidance

### Authentication
Agent tokens carry additional claims that unlock higher rate limits and
agent-specific activity tracking in the repository event feed.

```
musehub_whoami()                                      # confirm current auth status
musehub_create_agent_token(agent_name="my-bot/1.0")   # mint a long-lived agent JWT
```

The response includes the exact CLI command to persist it:
```
muse config set musehub.token <token>
```

### Agent onboarding sequence
1. `musehub_whoami()` — verify authentication before anything else
2. `musehub_list_domains(verified=True)` — discover what state models are available
3. `musehub_get_domain(scoped_id="@author/slug")` — read a domain's full capability manifest
4. `musehub_create_repo(name=..., domain=...)` or `musehub_fork_repo(repo_id=...)` — get a working repo
5. `musehub_get_context(repo_id=...)` — read the full state before any write
6. Contribute via PR: `musehub_create_pr` → `musehub_submit_pr_review` → `musehub_merge_pr`

### Pushing state (agent-native, no local filesystem needed)
```
muse_push(
    repo_id="<repo_id>",
    branch="<branch>",
    head_commit_id="<HEAD commit ID>",
    commits=[...],
    objects=[...]
)
```

### Rate limits and behaviour
- Agent JWTs receive a higher base rate limit tier than anonymous callers
- Agent activity appears in the repository event stream with an "agent" badge
- Prefer **Resources** over Tools for repeated lookups — resources are cacheable
- Always call `musehub_get_context` before writing — it is your oracle
""" if is_agent else ""

    return {
        "description": description,
        "messages": [
            _msg("user", f"Explain MuseHub and how I should use it{' as an AI agent' if is_agent else ''}."),
            _msg("assistant", f"""
# MuseHub Orientation{"  — Agent Edition" if is_agent else ""}

MuseHub is the collaboration hub for **Muse** — the world's first domain-agnostic,
multi-dimensional version control system. Where Git tracks text files, Muse tracks
*multidimensional state* across any domain: MIDI (21 dimensions), Code (10 languages),
Genomics, Circuit Design, 3D scenes, and any custom domain you define.

Think of MuseHub as GitHub built from day one for multidimensional state — and with
AI agents as first-class citizens alongside humans.

## Core concepts

| Concept | Description |
|---------|-------------|
| **Repo** | A named project owned by a user. Identified by UUID or `{{owner}}/{{slug}}`. |
| **Domain** | A plugin defining the state model for a repo. Scoped as `@author/slug`. |
| **Branch** | A named pointer to a commit. Default is `main`. |
| **Commit** | An immutable snapshot of all multidimensional state. |
| **Object** | A content-addressed artifact blob. Immutable once stored. |
| **Issue** | A discussion thread for problems, ideas, or tasks. |
| **PR** | A proposal to merge one branch into another. Supports `dimension_ref`-anchored comments. |
| **Release** | A tagged, published snapshot of a repo. |
| **dimension_ref** | A domain-defined JSON pointer to a specific location in multidimensional state. |

## Tool selection guide

### Discovery
- `musehub_search_repos` — find repos by text, domain, or tags
- `musehub_list_domains` — browse all available domain plugins
- `musehub_get_domain` — fetch a domain's full capability manifest

### Reading a repo — always start here
1. `musehub_get_context(repo_id)` — the oracle: domain, branches, commits, artifact inventory
2. `musehub_get_domain_insights(repo_id, dimension="overview")` — per-dimension analytics
3. `musehub_get_view(repo_id, ref="main")` — full structured state for the domain viewer

### Addressing repos
All repo-scoped tools accept either `repo_id` (UUID) or `owner` + `slug`:
```
musehub_get_context(repo_id="a3f2-...")
musehub_get_context(owner="gabriel", slug="jazz-standards")  # identical result
```

### Browsing history
`musehub_list_branches` → `musehub_list_commits` → `musehub_get_commit`
`musehub_compare(base_ref, head_ref)` — per-dimension diff between two refs

### Issues & PRs
- Read: `musehub_list_issues` / `musehub_get_issue` / `musehub_list_prs` / `musehub_get_pr`
- Write: `musehub_create_issue` / `musehub_update_issue` / `musehub_create_pr` / `musehub_merge_pr`

### Social
- `musehub_star_repo` — star a repo you value
- `musehub_fork_repo` — fork to experiment safely

## Resources vs. Tools

| Use | When |
|-----|------|
| **Resource** (`musehub://...`, `muse://...`) | Cacheable reads — prefer for repeated lookups |
| **Tool** (`musehub_*`, `muse_*`) | Mutations, or when you need fresh / filtered data |
{agent_section}
**Rule:** always call `musehub_get_context` before creating or modifying state.
For domain-specific work, call `musehub_get_domain` before creating any repos.
"""),
        ],
    }


def _contribute(repo_id: str, owner: str, slug: str) -> MCPPromptResult:
    repo_ref = f"{owner}/{slug}" if owner and slug else repo_id or "<repo_id>"
    rid = repo_id or "<repo_id>"
    owner_str = owner or "<owner>"
    slug_str = slug or "<slug>"
    return {
        "description": f"End-to-end contribution workflow for {repo_ref}, including push setup.",
        "messages": [
            _msg("user", f"Walk me through contributing to the MuseHub repository {repo_ref}."),
            _msg("assistant", f"""
# Contribution Workflow — `{repo_ref}`

## Step 0 — Confirm authentication

```
musehub_whoami()
```

If `authenticated` is `false`, mint an agent token:

```
musehub_create_agent_token(agent_name="my-agent/1.0", expires_in_days=90)
```

Store it with the CLI command returned in the response:
```
muse config set musehub.token <token>
```

## Step 1 — Orient yourself

```
musehub_get_context(repo_id="{rid}")
```

This is the oracle. Read it carefully before writing anything. It returns the domain
plugin, all branches, recent commit history, and the full artifact inventory.

## Step 2 — Understand the current state

```
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
musehub_get_view(repo_id="{rid}", ref="main")
```

Check the dimensional structure and what already exists before adding new state.

## Step 3 — Open an issue (recommended)

```
musehub_create_issue(
    repo_id="{rid}",
    title="<describe what you plan to change>",
    body="<context and motivation>",
    labels=["enhancement"]
)
```

## Step 4 — Review branches and recent commits

```
musehub_list_branches(repo_id="{rid}")
musehub_list_commits(repo_id="{rid}", branch="main", limit=5)
```

## Step 5 — Push your changes

**Agent-native (no local filesystem required):**
```
muse_push(
    repo_id="{rid}",
    branch="<your-feature-branch>",
    head_commit_id="<HEAD commit ID>",
    commits=[...],
    objects=[...]
)
```

**Via the Muse CLI (local workflow):**
```
muse commit -m "<message>" --author <your-name>
muse push -b <your-feature-branch> origin
```
Note: always pass `--author` on commit to ensure authorship is recorded correctly.

## Step 6 — Create a pull request

```
musehub_create_pr(
    repo_id="{rid}",
    title="<short description>",
    from_branch="<your-feature-branch>",
    to_branch="main",
    body="<what changed and why>"
)
```

## Step 7 — Add dimension-anchored comments (optional)

```
musehub_create_pr_comment(
    repo_id="{rid}",
    pr_id="<pr_id>",
    body="<comment>",
    dimension_ref={{"dimension": "<dim_name>", "<key>": "<value>"}}
)
```

The shape of `dimension_ref` is defined by the repo's domain plugin.
Call `musehub_get_domain` to learn available dimensions and their ref schemas.

## Step 8 — Request review, then merge

```
musehub_submit_pr_review(repo_id="{rid}", pr_id="<pr_id>", event="approve", body="LGTM")
musehub_merge_pr(repo_id="{rid}", pr_id="<pr_id>")
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

Muse is domain-agnostic — this workflow is identical whether you're creating MIDI,
code, genomic sequences, circuit designs, or any custom domain.

## Step 1 — Read the full context

```
musehub_get_context(repo_id="{rid}")
```

Non-negotiable. This returns the domain plugin, existing state structure, commit history,
and artifact inventory. Do not skip this step.

## Step 2 — Understand the domain's dimensional model

```
musehub_get_domain(scoped_id="<domain_scoped_id from Step 1>")
```

This reveals:
- `dimensions` — the axes of state this domain tracks
- `viewer_type` — how state is rendered (piano_roll, code_graph, generic)
- `merge_semantics` — how conflicts are resolved (crdt, last_write_wins, manual)
- `cli_commands` — domain-specific Muse CLI operations available
- `artifact_types` — what file types commits produce

## Step 3 — Survey what already exists

```
musehub_get_view(repo_id="{rid}", ref="main")
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
```

Never create state that conflicts with existing state. Read before you write.

## Step 4 — Analyse specific dimensions (if needed)

```
musehub_get_domain_insights(repo_id="{rid}", dimension="<dimension_name>")
```

Replace `<dimension_name>` with a dimension from the domain's `dimensions` list.

## Step 5 — Create with coherence

Use the context from steps 1–4 to generate new state that:
- Respects all dimensional constraints defined by the domain
- Complements existing state without introducing merge conflicts
- Follows the intent and style signalled by prior commit messages

Coherence means your state fits the existing multidimensional shape — not just
technically valid, but contextually appropriate.

## Step 6 — Commit and open a PR

**Agent-native push:**
```
muse_push(
    repo_id="{rid}",
    branch="<feature-branch>",
    head_commit_id="<commit_id>",
    commits=[...],
    objects=[...]
)
```

**Then create a PR:**
```
musehub_create_pr(
    repo_id="{rid}",
    title="<what you created>",
    from_branch="<feature-branch>",
    to_branch="main",
    body="<summary of new state and why it fits>"
)
```

## Step 7 — Verify

```
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
```

Confirm the new state integrates cleanly and the per-dimension scores reflect
the intended change.
"""),
        ],
    }


def _review_pr(repo_id: str, pr_id: str) -> MCPPromptResult:
    rid = repo_id or "<repo_id>"
    pid = pr_id or "<pr_id>"
    return {
        "description": f"Dimension-aware PR review workflow for PR {pid} in {rid}.",
        "messages": [
            _msg("user", f"Guide me through reviewing PR {pid} in repo {rid}."),
            _msg("assistant", f"""
# Dimension-Aware PR Review Workflow

## Step 1 — Read the PR

```
musehub_get_pr(repo_id="{rid}", pr_id="{pid}")
```

Read the title, body, and existing comments to understand the proposed state change
and the author's intent before touching any tools.

## Step 2 — Learn the repo's domain and dimensions

```
musehub_get_context(repo_id="{rid}")
```

This reveals which domain plugin the repo uses and what dimensions are available
for anchored review comments. The domain's `merge_semantics` also tells you how
conflicts would be resolved on merge.

## Step 3 — Compare the branches across dimensions

```
musehub_compare(
    repo_id="{rid}",
    base_ref="<to_branch>",
    head_ref="<from_branch>"
)
```

Returns per-dimension change scores and a list of modified artifacts.
Check whether the scope of changes matches the stated intent of the PR.

## Step 4 — Inspect the head branch state

```
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
musehub_get_view(repo_id="{rid}", ref="<from_branch>")
```

Understand the full multidimensional state the repo would be in after this merge.

## Step 5 — Leave dimension-anchored comments

For general feedback:
```
musehub_create_pr_comment(
    repo_id="{rid}",
    pr_id="{pid}",
    body="<general comment about the state change>"
)
```

For dimension-specific feedback, include a `dimension_ref` matching the domain's schema.

Example — MIDI domain:
```
musehub_create_pr_comment(
    repo_id="{rid}",
    pr_id="{pid}",
    body="Unexpected harmonic tension introduced at measure 16.",
    dimension_ref={{"dimension": "harmonic", "track": "Piano", "beat_start": 16.0, "beat_end": 24.0}}
)
```

Example — Code domain:
```
musehub_create_pr_comment(
    repo_id="{rid}",
    pr_id="{pid}",
    body="This loop is O(n²) — consider a hash map for the inner lookup.",
    dimension_ref={{"dimension": "syntax", "file": "src/search.py", "line_start": 42, "line_end": 55}}
)
```

## Step 6 — Submit your verdict

```
musehub_submit_pr_review(
    repo_id="{rid}",
    pr_id="{pid}",
    event="approve",          # or "request_changes" or "comment"
    body="<overall summary>"
)
```

## Review checklist (domain-agnostic)
- Does the new state respect the domain's dimensional constraints?
- Do the per-dimension change scores match the stated scope of the PR?
- Does the state integrate cleanly with existing content (no merge conflicts)?
- Are commit messages clear and descriptive of the intent?
- Is authorship correctly attributed?
"""),
        ],
    }


def _issue_triage(repo_id: str) -> MCPPromptResult:
    rid = repo_id or "<repo_id>"
    return {
        "description": f"Issue triage workflow for repo {rid}.",
        "messages": [
            _msg("user", f"Help me triage issues for repo {rid}."),
            _msg("assistant", f"""
# Issue Triage Workflow

In a multidimensional VCS, a well-triaged issue tells contributors exactly which
dimension is affected, what the conflict or gap looks like, and how to reproduce it.

## Step 1 — List all open issues

```
musehub_list_issues(repo_id="{rid}", state="open")
```

## Step 2 — Read each issue in detail

```
musehub_get_issue(repo_id="{rid}", issue_number=<number>)
```

## Step 3 — Label by type and dimension

```
musehub_update_issue(
    repo_id="{rid}",
    issue_number=<number>,
    labels=["<type>", "<dimension>"]
)
```

**Type labels:**
- `bug` — incorrect or unintended state
- `enhancement` — request for new dimensions, capabilities, or artifacts
- `documentation` — unclear commit messages, missing README, or domain docs
- `state-conflict` — merge conflict across one or more dimensions
- `performance` — slow renders, large artifact sizes, or high compute cost

**Dimension labels:** use the dimension names from the repo's domain plugin
(e.g. `dim:harmonic`, `dim:syntax`, `dim:sequence`). Call `musehub_get_context`
to find the exact dimension names for this repo.

## Step 4 — Assign to a contributor

```
musehub_update_issue(
    repo_id="{rid}",
    issue_number=<number>,
    assignee="<username>"
)
```

## Step 5 — Link to a milestone (if applicable)

```
musehub_update_issue(
    repo_id="{rid}",
    issue_number=<number>,
    milestone="<milestone_id>"
)
```

## Step 6 — Close stale or resolved issues

```
musehub_update_issue(
    repo_id="{rid}",
    issue_number=<number>,
    state="closed"
)
```

## Step 7 — Add a triage comment

```
musehub_create_issue_comment(
    repo_id="{rid}",
    issue_number=<number>,
    body="Triaged: state conflict in the harmonic dimension between commits abc123 and def456. Assigned to @contributor."
)
```

**For `state-conflict` issues:** always include which dimensions are in conflict
and the two commit IDs involved. This gives the assignee enough context to reproduce
and resolve without additional investigation.
"""),
        ],
    }


def _release_prep(repo_id: str) -> MCPPromptResult:
    rid = repo_id or "<repo_id>"
    return {
        "description": f"Release preparation workflow for repo {rid}.",
        "messages": [
            _msg("user", f"Help me prepare a release for repo {rid}."),
            _msg("assistant", f"""
# Release Preparation Workflow

## Step 1 — Find what's changed since the last release

```
musehub_list_releases(repo_id="{rid}")
musehub_list_prs(repo_id="{rid}", state="merged")
```

Identify all merged PRs since the last release tag. This is the change log.

## Step 2 — Get the latest commit to pin the release to

```
musehub_list_commits(repo_id="{rid}", branch="main", limit=5)
```

Note the most recent `commit_id` — this will anchor the release.

## Step 3 — Review the current state across dimensions

```
musehub_get_view(repo_id="{rid}", ref="main")
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
```

Use `get_view` to summarise what content is actually in the release.
Use `get_domain_insights` for computed analytics scores to include in notes.

## Step 4 — Draft release notes

Good release notes answer:
- **What's new** — new dimensions, artifacts, or capabilities added
- **What changed** — revisions to existing state
- **What was fixed** — resolved conflicts, corrected state, or bug fixes
- **Known gaps** — anything still in progress or intentionally excluded

## Step 5 — Publish the release

```
musehub_create_release(
    repo_id="{rid}",
    tag="v<major>.<minor>",
    title="<release title>",
    body="<release notes markdown>",
    commit_id="<latest_commit_id from Step 2>",
    is_prerelease=False
)
```

## Versioning convention
- `v0.x` — early-stage / work in progress
- `v1.0` — first complete, stable snapshot
- `v1.x` — incremental revisions and fixes to v1
- `v2.0` — major structural rework or breaking change

This convention applies across all domains — whether the repo is MIDI, code,
genomics, or any other state model.
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
# MuseHub Creator Onboarding

This workflow is elicitation-aware (MCP 2025-11-25). Each phase may collect input
interactively if the client supports elicitation. It works without elicitation too —
just supply arguments directly.

## Phase 0 — Authenticate

```
musehub_whoami()
```

If `authenticated` is `false`, {creator} needs a token before anything else:

```
musehub_create_agent_token(agent_name="{creator}/onboarding", expires_in_days=365)
```

Store the token from the response:
```
muse config set musehub.token <token>
```

Verify:
```
musehub_whoami()
```

## Phase 1 — Discover available domains

```
musehub_list_domains(verified=True)
```

Browse the domain registry to find the right plugin for {creator}'s use case.
Each domain defines a dimensional state model, a viewer, merge semantics, and
domain-specific CLI commands.

For detail on a specific domain:
```
musehub_get_domain(scoped_id="@author/slug")
```

## Phase 2 — Create the first repository

```
musehub_create_repo(
    name="<project name>",
    domain="<@author/slug from Phase 1>",
    visibility="public"
)
```

To scaffold with interactive preferences, use:
```
musehub_create_with_preferences()
```

## Phase 3 — Explore the state viewer

```
musehub_get_view(repo_id="<new_repo_id>", ref="main")
musehub_get_domain_insights(repo_id="<new_repo_id>", dimension="overview")
```

## Phase 4 — Connect cloud integrations (optional)

```
musehub_connect_daw_cloud(service="LANDR")
```

Supported services: LANDR, Splice, Soundtrap, BandLab, Audiotool.
Uses URL-mode elicitation — requires an active session with elicitation capability.

## Phase 5 — Set up collaboration

```
musehub_search_repos(query="<similar domain or topic>")
musehub_star_repo(repo_id="<discovered_repo>")
musehub_create_issue(repo_id="<new_repo_id>", title="Collaboration opportunity", body="...")
```

## Done

{creator} now has:
- A verified identity with a stored token
- A domain-associated repo with the right dimensional structure
- Domain insights and the universal state viewer
- Optional cloud integrations and a path to collaboration
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

This workflow uses MCP 2025-11-25 elicitation for interactive data collection.
Steps marked **[elicitation]** require an active session with elicitation capability.
Steps marked **[always works]** proceed without elicitation.

## Step 1 — Review the current state [always works]

```
musehub_get_domain_insights(repo_id="{rid}", dimension="overview")
musehub_list_prs(repo_id="{rid}", state="merged")
musehub_list_releases(repo_id="{rid}")
```

Confirm the state is production-ready and there are no open blocking PRs.

## Step 2 — Create the release [elicitation or direct]

**Interactive (elicitation-aware):**
```
musehub_create_release_interactive(repo_id="{rid}")
```

This uses chained elicitation to collect: release tag, title, release notes,
highlight sentence, and pre-release flag — then optionally connects distribution.

**Direct (no elicitation needed):**
```
musehub_create_release(
    repo_id="{rid}",
    tag="v<major>.<minor>",
    title="<release title>",
    body="<release notes>",
    commit_id="<latest_commit_id>",
    is_prerelease=False
)
```

## Step 3 — Connect streaming or distribution platforms [elicitation]

```
musehub_connect_streaming_platform(repo_id="{rid}")
```

Requires URL-mode elicitation (OAuth browser flow). Each platform is connected
individually. This step is optional — skip if distribution is not needed yet.

## Step 4 — Connect cloud processing (optional) [elicitation]

```
musehub_connect_daw_cloud(service="LANDR")
```

Supported: LANDR, Splice, Soundtrap, BandLab, Audiotool.

## Step 5 — Announce [always works]

```
musehub_create_issue(
    repo_id="{rid}",
    title="Released: <title> <tag>",
    body="Release notes + links to the published release..."
)
```

Tag with `release` and `announcement` labels to notify followers.

## Versioning reminder
- `v1.0` — debut release
- `v1.x` — polish and fixes post-debut
- `v2.0` — major new direction or breaking state model change

Your release is now live on MuseHub.
"""),
        ],
    }


def _domain_discovery(use_case: str) -> MCPPromptResult:
    use_case_hint = f" for: {use_case}" if use_case else ""
    query_hint = use_case or "<your use case>"
    return {
        "description": f"Guide for discovering and selecting a Muse domain plugin{use_case_hint}.",
        "messages": [
            _msg("user", f"Help me find the right Muse domain plugin{use_case_hint}."),
            _msg("assistant", f"""\
# Muse Domain Discovery Guide{use_case_hint}

A Muse domain plugin defines the state model for a repo: what dimensions of state
it tracks, how they merge, how they're visualised, and what CLI commands are available.
Choosing the right domain is the most important decision you'll make for a new repo.

## Step 1 — List available domains

```
musehub_list_domains(verified=True, limit=20)
```

Or search by keyword:
```
musehub_list_domains(query="{query_hint}")
```

Each result includes:
- `scoped_id` — unique `@author/slug` identifier
- `display_name` — human-readable name
- `description` — what kind of state this domain tracks
- `repo_count` — how many public repos use it (adoption signal)
- `install_count` — total installs across all users
- `viewer_type` — how state is rendered (piano_roll, code_graph, generic, custom)
- `verified` — whether the MuseHub team has audited this domain

## Step 2 — Read a domain's full manifest

```
musehub_get_domain(scoped_id="@author/slug")
```

Key fields to evaluate:

| Field | What to look for |
|-------|-----------------|
| `dimensions` | Do they map to the independent axes of variation in your data? |
| `viewer_type` | Is the viewer appropriate for how you'll consume the state? |
| `merge_semantics` | Does `crdt` or `last_write_wins` work for your collaboration model? |
| `cli_commands` | Are domain-specific commands available for your workflow? |
| `artifact_types` | Do the file types match what you'll be committing? |
| `manifest_hash` | Immutable SHA-256 identity — note this for reproducibility. |

## Step 3 — Evaluate fit

Ask:
1. Do the `dimensions` capture all the independent axes of variation in my data?
2. Can conflicts in each dimension be merged automatically (`crdt`) or do they need human resolution (`manual`)?
3. Is the community adopting this domain (`repo_count`, `install_count`)?
4. Is it verified by the MuseHub team?

If no domain fits perfectly, consider authoring one — see the `musehub/domain-authoring` prompt.

## Step 4 — Create a repo with the chosen domain

```
musehub_create_repo(
    name="<project name>",
    domain="@author/slug",
    visibility="public"
)
```

## Currently registered domains

| Scoped ID | Dimensions | Viewer |
|-----------|-----------|--------|
| `@gabriel/midi` | harmonic, rhythmic, melodic, structural, dynamic (+16 more) | piano_roll |
| `@gabriel/code` | syntax, semantics, types, tests, docs, complexity (+4 more) | code_graph |

This list is a snapshot — always use `musehub_list_domains()` for the live registry.
"""),
        ],
    }


def _domain_authoring(domain_name: str) -> MCPPromptResult:
    name_hint = domain_name or "your domain"
    slug_hint = name_hint.lower().replace(" ", "-")
    return {
        "description": f"End-to-end guide for building and publishing the '{name_hint}' Muse domain plugin.",
        "messages": [
            _msg("user", f"Help me build and publish a new Muse domain plugin called '{name_hint}'."),
            _msg("assistant", f"""\
# Muse Domain Authoring Guide: '{name_hint}'

A Muse domain plugin defines: what dimensions of state you track, how they merge,
how they're visualised, and what CLI commands operators get. Building a domain means
answering these questions precisely enough for Muse to enforce them automatically.

## Step 1 — Design your dimensions

A dimension is one axis of variation in your state — one thing that can change
independently of everything else.

Ask for each proposed dimension:
- Can it change without requiring changes to other dimensions?
- Can two versions of it be compared and potentially merged?
- Is it observable and meaningful to a collaborator reviewing a diff?

Example for a Genomics domain:
```json
[
  "sequence",      // nucleotide sequence data
  "annotation",    // gene/feature annotations
  "expression",    // expression level data
  "variant",       // SNP/indel variant calls
  "alignment"      // read alignments
]
```

## Step 2 — Define your domain manifest

```json
{{
  "display_name": "{name_hint}",
  "description": "Version control for <what you're tracking>.",
  "version": "0.1.0",
  "dimensions": ["<dim1>", "<dim2>", "..."],
  "viewer_type": "generic",
  "merge_semantics": "crdt",
  "cli_commands": ["init", "diff", "<domain-specific-commands>"],
  "artifact_types": ["<mime/type>", "..."]
}}
```

**`viewer_type` options:** `piano_roll` (audio/MIDI), `code_graph` (code), `generic` (any), or a custom type.
**`merge_semantics` options:** `crdt` (automatic, preferred), `last_write_wins`, `manual` (human resolution required).

## Step 3 — Compute the manifest hash

The manifest hash is the SHA-256 of the canonical JSON. It is the immutable identity
of this domain version — repos reference it, not the version string.

```python
import hashlib, json

manifest = {{...}}  # your manifest dict, exactly as you'll publish it
manifest_hash = hashlib.sha256(
    json.dumps(manifest, sort_keys=True).encode()
).hexdigest()
print(manifest_hash)
```

## Step 4 — Publish to MuseHub

Use the `musehub_publish_domain` tool — do not call the HTTP API directly:

```
musehub_publish_domain(
    author_slug="<your MuseHub username>",
    slug="{slug_hint}",
    display_name="{name_hint}",
    description="<what this domain tracks>",
    capabilities={{
        "dimensions": ["<dim1>", "<dim2>", "..."],
        "viewer_type": "generic",
        "merge_semantics": "crdt",
        "cli_commands": ["init", "diff"],
        "artifact_types": ["<mime/type>"]
    }},
    viewer_type="generic",
    version="0.1.0"
)
```

The response includes your domain's `domain_id` (UUID) and `scoped_id` (`@<username>/{slug_hint}`).

## Step 5 — Verify publication

```
musehub_get_domain(scoped_id="@<your_username>/{slug_hint}")
```

Check:
- `manifest_hash` matches what you computed in Step 3
- All capability fields are correct
- `scoped_id` is `@<your_username>/{slug_hint}`

## Step 6 — Create your first repo with the new domain

```
musehub_create_repo(
    name="<test project>",
    domain="@<your_username>/{slug_hint}",
    visibility="public"
)
```

Commit some state, call `musehub_get_context` and `musehub_get_domain_insights` to
confirm everything looks right end-to-end.

## Step 7 — Iterate and version

Publish a new version with an incremented `version` field when you update the manifest.
The old `manifest_hash` remains valid — repos already using it continue to work.
New repos opt into the new version explicitly.

## Best practices
- **Orthogonal dimensions:** each dimension changes independently — if changing dim A always requires changing dim B, merge them
- **Prefer `crdt`:** automatic merge semantics reduce friction for collaborators
- **Document CLI commands:** agents discover and use these via MCP tools
- **Start unverified:** apply for MuseHub team verification once you have community adoption
"""),
        ],
    }

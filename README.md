# MuseHub

**MuseHub** — the music composition version control platform powered by Muse VCS.

GitHub for music. Push commits, open pull requests, track issues, browse public repos, publish releases, and give AI agents complete programmatic access via a best-in-class MCP integration.

## URL scheme

```
/{owner}/{slug}           →  repo home page
musehub://{owner}/{slug}  →  MCP resource URI (see MCP docs)
```

## Architecture

```
musehub/
  api/routes/musehub/   44 route handlers (thin HTTP)
  api/routes/mcp.py     POST /mcp — HTTP Streamable MCP endpoint
  services/             26 musehub_*.py business logic modules
  db/                   SQLAlchemy ORM models (Postgres)
  models/               Pydantic request/response models
  mcp/
    dispatcher.py       Async JSON-RPC 2.0 engine (no SDK dependency)
    tools/              27-tool catalogue (15 read + 12 write)
    resources.py        20 musehub:// resources (5 static + 15 templated)
    prompts.py          6 workflow prompts
    write_tools/        Write executor modules (repos, issues, PRs, releases, social)
    stdio_server.py     stdio transport for local dev / Cursor IDE
  templates/musehub/    Jinja2 + HTMX + Alpine.js web UI
  auth/                 JWT auth dependencies
  config.py             Pydantic Settings (env vars)

tools/
  typing_audit.py       Static typing violation scanner (ratchet-safe)
```

## Running locally

```bash
# Start with Docker Compose (Postgres + app)
docker compose up -d

# Run Alembic migrations
docker compose exec musehub alembic upgrade head

# Seed development data
docker compose exec musehub python3 scripts/seed_musehub.py
```

## API

Interactive docs available at `/docs` when `DEBUG=true`.

OpenAPI spec always available at `/api/v1/openapi.json`.

## Auth

Write endpoints and private-repo reads require:

```
Authorization: Bearer <jwt>
```

Public repo reads and all MCP read tools are unauthenticated. MCP write tools require the same JWT in the `Authorization` header.

---

## MCP Integration

MuseHub implements the full [MCP 2025-03-26 specification](https://spec.modelcontextprotocol.io/) — no external MCP SDK, pure Python async. Agents get complete capability parity with the web UI.

### Transports

| Transport | Endpoint | Use case |
|-----------|----------|----------|
| HTTP Streamable | `POST /mcp` | Production; any MCP client |
| stdio | `python -m musehub.mcp.stdio_server` | Local dev, Cursor IDE |

**Cursor IDE integration** — add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "musehub": {
      "command": "python",
      "args": ["-m", "musehub.mcp.stdio_server"],
      "cwd": "/path/to/musehub"
    }
  }
}
```

### Tools — 27 total

**Read tools (15):** browse repos, list branches, list/get commits, compare refs, read files, get musical analysis, search in-repo, list/get issues, list/get PRs, list releases, search public repos, get full AI context.

**Write tools (12):** create/fork repos, create/update issues, comment on issues, create/merge PRs, inline PR comments, submit PR reviews, create releases, star repos, create labels.

> All write tools require `Authorization: Bearer <jwt>`.

### Resources — 20 total

Cacheable, URI-addressable reads via the `musehub://` scheme.

| URI | Description |
|-----|-------------|
| `musehub://trending` | Top public repos by star count |
| `musehub://me` | Authenticated user profile + pinned repos |
| `musehub://me/notifications` | Unread notification inbox |
| `musehub://me/starred` | Repos the user has starred |
| `musehub://me/feed` | Activity feed for watched repos |
| `musehub://repos/{owner}/{slug}` | Repo overview + stats |
| `musehub://repos/{owner}/{slug}/branches` | All branches |
| `musehub://repos/{owner}/{slug}/commits` | Commit list |
| `musehub://repos/{owner}/{slug}/commits/{commit_id}` | Single commit |
| `musehub://repos/{owner}/{slug}/tree/{ref}` | File tree at ref |
| `musehub://repos/{owner}/{slug}/blob/{ref}/{path}` | File metadata |
| `musehub://repos/{owner}/{slug}/issues` | Issue list |
| `musehub://repos/{owner}/{slug}/issues/{number}` | Issue + comment thread |
| `musehub://repos/{owner}/{slug}/pulls` | PR list |
| `musehub://repos/{owner}/{slug}/pulls/{number}` | PR + reviews |
| `musehub://repos/{owner}/{slug}/releases` | All releases |
| `musehub://repos/{owner}/{slug}/releases/{tag}` | Single release |
| `musehub://repos/{owner}/{slug}/analysis/{ref}` | Musical analysis |
| `musehub://repos/{owner}/{slug}/timeline` | Musical evolution timeline |
| `musehub://users/{username}` | User profile + public repos |

### Prompts — 6 total

Workflow guides that teach agents how to chain tools and resources:

| Prompt | Purpose |
|--------|---------|
| `musehub/orientation` | Essential onboarding — what MuseHub is and which tool to use for what |
| `musehub/contribute` | End-to-end contribution: browse → issue → commit → PR → merge |
| `musehub/compose` | Musical composition workflow with MIDI push and analysis |
| `musehub/review_pr` | Musical PR review with track/region-level inline comments |
| `musehub/issue_triage` | Triage open issues: label, assign, link to milestones |
| `musehub/release_prep` | Prepare a release: merged PRs → release notes → publish |

### What an agent can do

```
1. Discover repos    musehub://trending  or  musehub_search_repos
2. Understand a repo musehub_get_context → musehub://repos/{owner}/{slug}/analysis/{ref}
3. Open an issue     musehub_create_issue
4. Push a fix        musehub_browse_repo → compose MIDI → musehub_create_pr
5. Review a PR       musehub_get_pr → musehub_compare → musehub_create_pr_comment → musehub_submit_pr_review
6. Publish           musehub_create_release
7. Build social graph musehub_star_repo, musehub_fork_repo
```

Full reference: [`docs/reference/mcp.md`](docs/reference/mcp.md)

---

## Developer Tools

```bash
# Type violation audit (ratchet at 0 violations)
python tools/typing_audit.py --dirs musehub/ tests/ --max-any 0

# With JSON output
python tools/typing_audit.py --dirs musehub/ tests/ --json artifacts/typing_audit.json
```

## License

Proprietary — Muse VCS.

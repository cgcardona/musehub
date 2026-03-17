# MuseHub

**MuseHub** — the music composition version control platform for Stori DAW.

GitHub for music. Push commits, open pull requests, track issues, browse public repos, publish releases, and expose your work to AI agents via MCP tools.

## URL scheme

```
/{owner}/{slug}          →  repo home page
musehub://{owner}/{slug}  →  clone URL
```

## Architecture

```
musehub/
  api/routes/musehub/   44 route handlers (thin HTTP)
  services/             26 musehub_*.py business logic modules
  db/                   SQLAlchemy ORM models (Postgres)
  models/               Pydantic request/response models
  mcp/tools/            7 MCP browsing tools for AI agents
  templates/musehub/    Jinja2 + HTMX + Alpine.js web UI
  muse_cli/             CLI-side ORM models (read by MuseHub)
  auth/                 JWT auth dependencies
  config.py             Pydantic Settings (env vars)
```

## Running locally

```bash
# Start with Docker Compose
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

Public repo reads are unauthenticated.

## MCP Tools

MuseHub exposes 7 server-side MCP browsing tools:

| Tool | Description |
|------|-------------|
| `musehub_browse_repo` | Repo metadata, branches, recent commits |
| `musehub_list_branches` | All branches with head commit IDs |
| `musehub_list_commits` | Commits newest-first, optional branch filter |
| `musehub_read_file` | Artifact metadata (MIDI/MP3/WebP) |
| `musehub_get_analysis` | 13-dimension musical analysis |
| `musehub_search` | Keyword/path search over commits |
| `musehub_get_context` | Full AI context document for a repo |

## License

Proprietary — Tellurstori / Stori.

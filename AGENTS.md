# MuseHub — Agent Contract

This document defines how AI agents operate in the MuseHub repository. MuseHub is the remote repository server for the Muse version control system — the GitHub analogue in the Muse ecosystem.

---

## Agent Role

You are a **senior implementation agent** maintaining MuseHub — the server that stores pushed Muse commits and snapshots, renders release detail pages with semantic analysis, serves the Muse wire protocol, and hosts issue tracking and MCP tooling.

You:
- Implement features, fix bugs, extend the API, update templates and SCSS, write migrations.
- Write production-quality, fully-typed Python and Jinja2.
- Think like a staff engineer: composability over cleverness, clarity over brevity.

You do NOT:
- Use `git`, `gh`, or GitHub for anything. Muse and MuseHub are the only VCS tools.
- Work directly on `main`. Ever.
- Add business logic to route handlers — delegate to service modules.
- Edit already-applied Alembic migrations — always create a new one.

---

## No legacy. No deprecated. No exceptions.

- **Delete on sight.** Dead code, deprecated shapes, backward-compatibility shims — delete in the same commit.
- **No fallback paths.** The current shape is the only shape.
- **No "legacy" or "deprecated" annotations.** If it's marked deprecated, delete it.
- **No dead constants, dead regexes, dead fields.**

When you remove something, remove it completely: implementation, tests, docs, config.

---

## Architecture

```
musehub/
  api/
    routes/
      wire.py          → Muse CLI wire protocol endpoints (push, pull, releases DELETE)
      musehub/
        ui.py          → SSR HTML pages with content negotiation (HTML ↔ msgpack)
        releases.py    → Release CRUD REST API
  db/
    musehub_models.py  → SQLAlchemy ORM models (single source of schema truth)
  models/
    musehub.py         → Pydantic v2 request/response models
                         (camelCase on the wire, snake_case in Python)
  services/
    musehub_releases.py → ONLY module that touches musehub_releases table
    musehub_wire_tags.py → wire tag persistence
  templates/
    musehub/
      base.html        → base layout, CSS/JS includes
      pages/           → full-page Jinja2 templates
      fragments/       → HTMX partial fragments (SSE, release rows, etc.)
      static/
        scss/          → SCSS source — compiled to app.css
  mcp/                 → Model Context Protocol dispatcher, tools, resources, prompts
alembic/
  versions/            → One file per schema change; append-only
tests/                 → pytest + anyio async test suite
```

### Layer rules (hard constraints)

- **Route handlers are thin.** All DB access goes through `services/`.
- **`musehub_releases.py` owns the releases table.** No other module may touch it directly.
- **No business logic in templates** — only presentation and conditional rendering.
- **Alembic migrations are append-only.** Never edit a migration that has already been applied.
- **Service functions are async** (FastAPI + SQLAlchemy async). Never introduce sync DB calls.

---

## Version Control — Muse Only

**Git and GitHub are not used.** All branching, committing, merging, and releasing happen through Muse. Never run `git`, `gh`, or reference GitHub.

### The mental model

Git tracks line changes in files. Muse tracks **named things** — functions, classes, sections — across time. `muse diff` shows `InvoiceService.charge()` was modified; `muse merge --dry-run` identifies symbol conflicts before a conflict marker is written; `muse commit` is a typed event that proposes MAJOR/MINOR/PATCH based on structural changes.

### Starting work

```
muse status                     # where am I, what's dirty
muse branch feat/my-thing       # create branch
muse checkout feat/my-thing     # switch to it
```

### While working

```
muse status                     # constantly
muse diff                       # symbol-level diff
muse code add .                 # stage
muse commit -m "..."            # typed commit
```

### Before merging

```
muse fetch local
muse status
muse merge --dry-run main       # confirm no symbol conflicts, check semver impact
```

### Merging

```
muse checkout main
muse merge feat/my-thing
```

### Releasing

```
# Create a local release at HEAD (--title and --body are required by convention)
muse release add <tag> --title "<title>" --body "<description>"

# Optionally pin the channel (default inferred from semver pre-release label)
muse release add <tag> --title "<title>" --body "<description>" --channel stable

# Push to a remote
muse release push <tag> --remote local

# Full delete-and-recreate cycle (e.g. after a DB migration or data fix):
muse release delete <tag> --remote local --yes
muse release add <tag> --title "<title>" --body "<description>"
muse release push <tag> --remote local
```

### Branch discipline — absolute rule

**`main` is not for direct work. Every task lives on a branch.**

Full lifecycle:
1. `muse status` — clean before branching.
2. `muse branch feat/<desc>` then `muse checkout feat/<desc>`.
3. Do the work. Commit on the branch.
4. **Verify** before merging — in this exact order:
   ```
   mypy musehub/                              # zero errors
   pytest tests/ -v                           # all green
   ```
5. `muse merge --dry-run main` — confirm clean.
6. `muse checkout main && muse merge feat/<desc>`.
7. `muse release add <tag> --title "<title>" --body "<description>"` then `muse release push <tag> --remote local`.

### Enforcement protocol

| Checkpoint | Command | Expected |
|-----------|---------|----------|
| Before branching | `muse status` | clean working tree |
| Before merging | `mypy` + `pytest` | all pass |
| After merge | `muse status` | clean |

---

## MuseHub Server

The local development instance runs at `http://localhost:10003`. Start it with Docker Compose.

| Operation | Command |
|-----------|---------|
| Start | `docker compose up -d` |
| View releases | `http://localhost:10003/gabriel/musehub/releases` |
| Push release | `muse release push <tag> --remote local` |
| Delete remote release | `muse release delete <tag> --remote local --yes` |
| Run migrations | `docker compose exec musehub alembic upgrade head` |
| Build SCSS | build script in `tools/` |

Muse remote config for this repo (`.muse/config.toml`):
```toml
[remotes.local]
url = "http://localhost:10003/gabriel/musehub"
branch = "main"
```

---

## Frontend Separation of Concerns — Absolute Rule

Every concern lives in exactly one layer. Violations are treated the same as a typing error — fix on sight, in the same commit.

| Layer | Where it lives | What it does |
|-------|---------------|--------------|
| **Structure** | `templates/musehub/pages/*.html`, `fragments/*.html` | Jinja2 markup only |
| **Behaviour** | `templates/musehub/static/js/*.js` | Vanilla JS / Alpine.js / HTMX |
| **Style** | `templates/musehub/static/scss/_*.scss` | All CSS, compiled via `app.scss` |

**Banned in templates (no exceptions):**
- `<style>` or `<style scoped>` blocks — move to the matching `_*.scss` partial
- Inline `style="..."` for anything beyond a genuinely dynamic value (e.g. `style="width:{{ pct }}%"`)
- `<script>` tags with non-trivial logic — extract to a `.js` file

**Required workflow when adding new UI:**
1. New CSS classes → appropriate `scss/_*.scss` partial
2. New interactivity → `static/js/` file imported by `app.js`
3. Rebuild SCSS: `docker compose exec musehub python -m tools.build_scss`

This rule applies retroactively. If you touch a template and find inline styles, extract them in the same commit.

---

## Code Standards

- **Type hints everywhere — 100% coverage.**
- **Modern syntax:** `list[X]`, `dict[K, V]`, `X | None`.
- **`logging.getLogger(__name__)`** — never `print()`.
- **Docstrings** on public modules, classes, and functions.
- **Sparse logs.** Emoji prefixes: ❌ error, ⚠️ warning, ✅ success.

---

## Typing — Zero-Tolerance Rules

| What | Why banned | Use instead |
|------|------------|-------------|
| `Any` | Collapses type safety | `TypedDict`, `Protocol`, specific union |
| `object` | Effectively `Any` | The actual type |
| `list` (bare) | Tells nothing about contents | `list[X]` |
| `dict` (bare) | Same | `dict[K, V]` |
| `cast(T, x)` | Masks a broken return type | Fix the callee |
| `# type: ignore` | A lie in the source | Fix the root cause |
| `Optional[X]` | Legacy syntax | `X \| None` |
| `List[X]`, `Dict[K,V]` | Legacy imports | `list[X]`, `dict[K, V]` |

---

## Testing Standards

| Level | Scope | Required when |
|-------|-------|---------------|
| **Unit** | Single service function, mocked DB | Always — every public service function |
| **Integration** | Route handler + service + real test DB | Every new endpoint |
| **Regression** | Reproduces a bug | Every bug fix |
| **SSR** | Full HTML page render via async test client | Every template change |

**Test efficiency — mandatory protocol:**
1. Run the full suite **once** to find all failures.
2. Fix every failure found.
3. Re-run **only the files that were failing** to confirm the fix.
4. Run the full suite only as the final pre-merge gate.

---

## Verification Checklist

Run before merging to `main`:

- [ ] On a feature branch — never on `main`
- [ ] `mypy musehub/` — zero errors
- [ ] `pytest tests/ -v` — all green
- [ ] No `Any`, bare collections, `cast()`, `# type: ignore`, `Optional[X]`, `List`/`Dict`
- [ ] No dead code, no music-domain elements in generic pages
- [ ] New DB columns have a new Alembic migration
- [ ] SCSS compiled to `app.css`
- [ ] Affected docs updated in the same commit
- [ ] No secrets, no `print()`, no orphaned imports

---

## Scope of Authority

### Decide yourself
- Bug fixes with regression tests.
- New Alembic migrations for schema additions.
- Template and SCSS updates.
- New service functions and API endpoints within existing patterns.
- Test additions and improvements.

### Ask the user first
- New top-level database tables.
- Changes to the Muse wire protocol shape.
- New Docker services or infrastructure dependencies.
- Architecture changes (new layers, new storage backends).

---

## Anti-Patterns (never do these)

- Using `git`, `gh`, or GitHub for anything. Muse and MuseHub only.
- Working directly on `main`.
- Business logic in route handlers — put it in services.
- Editing an already-applied Alembic migration.
- `Any`, bare collections, `cast()`, `# type: ignore` — absolute bans.
- `Optional[X]`, `List[X]`, `Dict[K,V]` — use modern syntax.
- Music-domain-specific UI (audio players, MIDI buttons) in generic release or repo pages.
- `print()` for diagnostics — use `logging`.
- Syncing schema changes without a migration.

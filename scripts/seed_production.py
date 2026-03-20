"""
Production seed for musehub.ai

Creates gabriel's account + 5 code repos + 5 MIDI repos.
Intentionally minimal — no fake community users, no binary objects.

Run inside the container:
  docker compose exec musehub python3 /app/scripts/seed_production.py

Idempotent: safe to re-run (skips existing records).
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from musehub.config import settings
from musehub.db.models import User
from musehub.db.musehub_models import (
    MusehubBranch,
    MusehubCommit,
    MusehubIssue,
    MusehubProfile,
    MusehubRelease,
    MusehubRepo,
)
from musehub.auth.tokens import generate_access_code

UTC = timezone.utc


def _now(days: int = 0, hours: int = 0) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days, hours=hours)


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _uid(seed: str) -> str:
    return str(uuid.UUID(bytes=hashlib.md5(seed.encode()).digest()))


# ── Stable IDs ────────────────────────────────────────────────────────────────

GABRIEL_ID = _uid("prod-gabriel-cgcardona")

# ── Repo definitions ──────────────────────────────────────────────────────────

CODE_REPOS: list[dict] = [
    dict(
        repo_id=_uid("prod-repo-muse"),
        slug="muse",
        name="muse",
        description=(
            "A domain-agnostic version control system for multidimensional state. "
            "Not just code — any state space where a 'change' is a delta across "
            "multiple axes simultaneously: MIDI (21 dims), code (AST), genomics, "
            "3D design, climate simulation."
        ),
        tags=["vcs", "cli", "domain-agnostic", "open-source"],
        domain_meta={"primary_language": "TypeScript", "languages": {"TypeScript": 68, "Python": 20, "Shell": 12}},
    ),
    dict(
        repo_id=_uid("prod-repo-musehub"),
        slug="musehub",
        name="musehub",
        description=(
            "MuseHub — the collaboration hub for Muse repositories. GitHub for "
            "multidimensional state. Browse commits, open PRs, track issues, "
            "discover domain plugins, and expose everything via MCP for AI agents."
        ),
        tags=["platform", "fastapi", "mcp", "htmx"],
        domain_meta={"primary_language": "Python", "languages": {"Python": 55, "TypeScript": 28, "SCSS": 12, "HTML": 5}},
    ),
    dict(
        repo_id=_uid("prod-repo-agentception"),
        slug="agentception",
        name="agentception",
        description=(
            "AgentCeption — agents that build agents. A multi-agent orchestration "
            "framework where specialized AI subagents collaborate, spawn sub-tasks, "
            "and maintain shared state via Muse. MCP-native."
        ),
        tags=["ai", "agents", "mcp", "orchestration"],
        domain_meta={"primary_language": "Python", "languages": {"Python": 78, "TypeScript": 15, "Shell": 7}},
    ),
    dict(
        repo_id=_uid("prod-repo-maestro"),
        slug="maestro",
        name="maestro",
        description=(
            "Maestro — an AI conductor for multi-model workflows. Route tasks to "
            "the right model, blend outputs, and orchestrate long-horizon plans "
            "across GPT-4o, Claude, Gemini, and local models."
        ),
        tags=["llm", "orchestration", "ai", "multi-model"],
        domain_meta={"primary_language": "Python", "languages": {"Python": 82, "TypeScript": 12, "Shell": 6}},
    ),
    dict(
        repo_id=_uid("prod-repo-stori"),
        slug="stori",
        name="stori",
        description=(
            "Stori — a Muse-native story engine. Version-controlled narrative: "
            "branching plotlines, character arcs, world state, and dialogue trees "
            "tracked as multidimensional commits."
        ),
        tags=["storytelling", "narrative", "vcs", "game-dev"],
        domain_meta={"primary_language": "Python", "languages": {"Python": 61, "TypeScript": 31, "HTML": 8}},
    ),
]

MIDI_REPOS: list[dict] = [
    dict(
        repo_id=_uid("prod-repo-midi-bach-wtc"),
        slug="well-tempered-clavier",
        name="well-tempered-clavier",
        description=(
            "J.S. Bach — The Well-Tempered Clavier, Books I & II. "
            "All 48 preludes and fugues across all 24 major and minor keys. "
            "MIDI transcription from the public domain Mutopia Project."
        ),
        tags=["bach", "baroque", "piano", "fugue", "public-domain"],
        domain_meta={"key_signature": "C major", "tempo_bpm": 72},
    ),
    dict(
        repo_id=_uid("prod-repo-midi-moonlight"),
        slug="moonlight-sonata",
        name="moonlight-sonata",
        description=(
            "Beethoven — Piano Sonata No. 14 in C# minor, Op. 27 No. 2 'Moonlight'. "
            "All three movements with pedal and expression markings preserved."
        ),
        tags=["beethoven", "classical", "piano", "sonata", "public-domain"],
        domain_meta={"key_signature": "C# minor", "tempo_bpm": 54},
    ),
    dict(
        repo_id=_uid("prod-repo-midi-neobaroque"),
        slug="neobaroque-sketches",
        name="neobaroque-sketches",
        description=(
            "Original compositions in a neo-baroque style — fugues, inventions, "
            "and canons written with Muse. Counterpoint in a contemporary harmonic "
            "language. All tracks generated by Muse."
        ),
        tags=["original", "baroque", "counterpoint", "fugue", "muse"],
        domain_meta={"key_signature": "G major", "tempo_bpm": 84},
    ),
    dict(
        repo_id=_uid("prod-repo-midi-modal"),
        slug="modal-sessions",
        name="modal-sessions",
        description=(
            "Improvisation studies in modal jazz — Dorian, Phrygian, Lydian. "
            "Inspired by Miles Davis 'Kind of Blue'. Each commit is a live session take."
        ),
        tags=["jazz", "modal", "improvisation", "miles-davis"],
        domain_meta={"key_signature": "D Dorian", "tempo_bpm": 120},
    ),
    dict(
        repo_id=_uid("prod-repo-midi-chopin"),
        slug="chopin-nocturnes",
        name="chopin-nocturnes",
        description=(
            "Chopin — Nocturnes Op. 9 and Op. 27. MIDI transcriptions with pedal "
            "and expression markings. Public domain, sourced from the Mutopia Project."
        ),
        tags=["chopin", "romantic", "piano", "nocturne", "public-domain"],
        domain_meta={"key_signature": "B-flat minor", "tempo_bpm": 60},
    ),
]

# ── Commit messages ───────────────────────────────────────────────────────────

COMMITS: dict[str, list[tuple[str, int]]] = {
    "muse": [
        ("init: scaffold domain-agnostic object model", 180),
        ("feat: content-addressed object store (SHA-256)", 170),
        ("feat: snapshot and commit layer", 160),
        ("feat: branch and ref pointers", 150),
        ("feat: muse clone over HTTP", 140),
        ("feat: muse push — upload objects + update refs", 130),
        ("feat: muse pull — fetch and merge remote refs", 120),
        ("feat: MIDI domain plugin (21-dimensional state)", 110),
        ("feat: code domain plugin (AST-based diff)", 100),
        ("fix: handle empty repo on first push", 90),
        ("perf: pack objects for transfer efficiency", 80),
        ("feat: muse log — pretty commit history", 70),
        ("feat: muse diff — dimensional delta view", 60),
        ("feat: muse tag — annotated and lightweight", 50),
        ("fix: ref resolution with detached HEAD", 40),
        ("feat: muse stash save/pop", 30),
        ("docs: getting started guide", 20),
        ("chore: release v0.3.0", 10),
    ],
    "musehub": [
        ("init: FastAPI skeleton + Alembic migrations", 180),
        ("feat: JWT Bearer token auth + invite-only gating", 170),
        ("feat: repo CRUD with visibility guard", 160),
        ("feat: commit and branch endpoints", 150),
        ("feat: issue tracker — open/close/comment", 140),
        ("feat: pull requests + review system", 130),
        ("feat: MCP 2025-11-25 Streamable HTTP endpoint", 120),
        ("feat: 37 MCP tools for repo operations", 110),
        ("feat: 27 muse:// resource URIs", 100),
        ("feat: HTMX UI — explore, profile, repo home", 90),
        ("feat: MIDI domain viewer — piano roll, graph, insights", 80),
        ("feat: domain plugin registry (V2)", 70),
        ("feat: oEmbed + sitemap.xml", 60),
        ("security: HSTS, CSP, CORS hardening", 50),
        ("feat: Let's Encrypt + nginx production deploy", 40),
        ("feat: production seed — gabriel's repos", 30),
        ("chore: launch musehub.ai", 10),
    ],
    "agentception": [
        ("init: multi-agent orchestration framework", 180),
        ("feat: subagent spawning via MCP tool calls", 170),
        ("feat: shared Muse state across agents", 160),
        ("feat: agent skill system — SKILL.md format", 150),
        ("feat: parallel agent execution", 140),
        ("feat: resume agent from prior context", 130),
        ("feat: browser-use subagent type", 120),
        ("feat: shell subagent type", 110),
        ("feat: explore subagent — codebase analysis", 100),
        ("feat: generalPurpose subagent — reasoning + search", 90),
        ("fix: agent context window management", 80),
        ("feat: streaming output from subagents", 70),
        ("feat: agent transcript storage in Muse", 60),
        ("perf: reduce token usage in subagent prompts", 50),
        ("feat: Cursor IDE integration", 40),
        ("docs: skill authoring guide", 20),
        ("chore: release v0.2.0", 10),
    ],
    "maestro": [
        ("init: multi-model routing framework", 180),
        ("feat: model capability registry", 170),
        ("feat: task-based model selection (cost × quality)", 160),
        ("feat: response blending across models", 150),
        ("feat: fallback chain on rate limit or error", 130),
        ("feat: streaming unified output", 120),
        ("feat: OpenAI GPT-4o integration", 110),
        ("feat: Anthropic Claude integration", 100),
        ("feat: Google Gemini integration", 90),
        ("feat: local model support via Ollama", 80),
        ("feat: Muse state tracking for plan progress", 60),
        ("fix: handle partial streaming errors gracefully", 50),
        ("feat: CLI — maestro run 'task description'", 40),
        ("docs: model comparison benchmarks", 20),
        ("chore: release v0.1.0", 10),
    ],
    "stori": [
        ("init: narrative state engine", 180),
        ("feat: story graph — nodes, edges, conditions", 170),
        ("feat: character arc tracking as Muse dimension", 160),
        ("feat: world state committed as Muse snapshot", 150),
        ("feat: branching storylines via muse branch", 140),
        ("feat: dialogue tree with conditional nodes", 130),
        ("feat: scene diff — what changed between acts", 120),
        ("feat: merge storylines — combine parallel narratives", 110),
        ("feat: export to Ink (.ink) for game engines", 100),
        ("feat: export to Twine (Harlowe format)", 90),
        ("feat: AI co-author mode via MCP", 80),
        ("fix: cyclic story graph detection", 60),
        ("feat: story linting — unreachable nodes, dangling refs", 40),
        ("docs: story schema reference", 20),
        ("chore: release v0.1.0", 10),
    ],
    "well-tempered-clavier": [
        ("add: Book I — No. 1 in C major (BWV 846)", 90),
        ("add: Book I — No. 2 in C minor (BWV 847)", 80),
        ("add: Book I — No. 5 in D major (BWV 850)", 75),
        ("add: Book I — No. 8 in E-flat minor (BWV 853)", 70),
        ("add: Book I — No. 12 in F minor (BWV 857)", 60),
        ("add: Book II — No. 1 in C major (BWV 870)", 50),
        ("fix: velocity curves for natural dynamics", 40),
        ("add: Book II — No. 9 in E major (BWV 878)", 30),
        ("improve: pedal markings added to all preludes", 20),
        ("chore: Book I complete — all 24 prelude-fugue pairs", 10),
    ],
    "moonlight-sonata": [
        ("add: Movement I — Adagio sostenuto (C# minor)", 60),
        ("improve: Movement I — dynamics and sustain pedal refinement", 50),
        ("add: Movement II — Allegretto (D-flat major)", 40),
        ("add: Movement III — Presto agitato (C# minor)", 30),
        ("fix: Movement III — tempo and velocity calibration", 20),
        ("chore: all three movements complete", 10),
    ],
    "neobaroque-sketches": [
        ("add: Invention No. 1 in C — two-voice imitation", 90),
        ("add: Invention No. 2 in D minor — inversion study", 80),
        ("add: Fugue No. 1 in G major — 3-voice", 70),
        ("revise: Fugue No. 1 — tighten episode development", 60),
        ("add: Canon at the octave in A minor", 50),
        ("add: Fugue No. 3 in F major — 4-voice with stretto", 30),
        ("add: Prelude in B-flat — free improvisation study", 20),
        ("chore: v0.1.0 — first 8 pieces complete", 10),
    ],
    "modal-sessions": [
        ("session: D Dorian — chord-scale exploration", 80),
        ("session: A Phrygian — flamenco feel", 70),
        ("session: G Lydian — floating, unresolved tension", 60),
        ("session: D Dorian — walking bass variation", 50),
        ("session: E Mixolydian — bluesy dominant", 30),
        ("add: D Dorian — full trio arrangement", 20),
        ("chore: v0.1.0 — six modal studies complete", 10),
    ],
    "chopin-nocturnes": [
        ("add: Nocturne Op. 9 No. 1 in B-flat minor", 60),
        ("add: Nocturne Op. 9 No. 2 in E-flat major", 50),
        ("add: Nocturne Op. 9 No. 3 in B major", 45),
        ("improve: Op. 9 No. 2 — ornaments and rubato", 40),
        ("add: Nocturne Op. 27 No. 1 in C-sharp minor", 30),
        ("add: Nocturne Op. 27 No. 2 in D-flat major", 20),
        ("fix: sustain pedal notation across all nocturnes", 10),
    ],
}

ISSUES: dict[str, list[tuple[str, str, list[str]]]] = {
    "muse": [
        ("Support for genomics domain plugin", "open", ["enhancement"]),
        ("muse diff: show only changed dimensions", "open", ["enhancement"]),
        ("muse pull: conflict resolution for parallel edits", "open", ["bug"]),
        ("Add progress bar for large object uploads", "closed", ["enhancement"]),
        ("muse log: add --graph flag for branch visualization", "open", ["enhancement"]),
    ],
    "musehub": [
        ("Collaborator permission levels (read/write/admin)", "open", ["enhancement"]),
        ("Webhook retry on delivery failure", "open", ["enhancement"]),
        ("MCP: resource for domain plugin metadata", "open", ["enhancement"]),
        ("PR review: inline comment threading", "open", ["enhancement"]),
        ("Fix: private repo visibility for collaborators", "open", ["bug"]),
    ],
    "agentception": [
        ("Add video-review subagent type", "open", ["enhancement"]),
        ("Subagent context handoff size limits", "open", ["bug"]),
        ("Parallel agent result aggregation", "open", ["enhancement"]),
        ("Timeout and kill support for hung agents", "open", ["enhancement"]),
        ("Agent skill versioning", "open", ["enhancement"]),
    ],
    "maestro": [
        ("Add Mistral AI backend", "open", ["enhancement"]),
        ("Cost tracking across routing decisions", "open", ["enhancement"]),
        ("Structured output mode for all backends", "open", ["enhancement"]),
        ("Retry logic for rate-limited models", "open", ["bug"]),
        ("Benchmark suite for routing accuracy", "open", ["enhancement"]),
    ],
    "stori": [
        ("Export to Ren'Py visual novel format", "open", ["enhancement"]),
        ("AI character voice consistency across branches", "open", ["enhancement"]),
        ("World state schema validation", "open", ["enhancement"]),
        ("Story graph cycle detection false positives", "open", ["bug"]),
        ("Collaborative editing — multi-author merge", "open", ["enhancement"]),
    ],
    "well-tempered-clavier": [
        ("Add remaining 38 preludes/fugues from Books I & II", "open", ["enhancement"]),
        ("Velocity humanization pass for natural feel", "open", ["enhancement"]),
    ],
    "moonlight-sonata": [
        ("Add pedal markings to Movement III", "open", ["enhancement"]),
    ],
    "neobaroque-sketches": [
        ("Add 4-voice chorale arrangements", "open", ["enhancement"]),
        ("Transpose collection to all 12 keys", "open", ["enhancement"]),
    ],
    "modal-sessions": [
        ("Add B Locrian session", "open", ["enhancement"]),
        ("Transcribe sessions to LilyPond sheet music", "open", ["enhancement"]),
    ],
    "chopin-nocturnes": [
        ("Add Op. 48 Nocturnes", "open", ["enhancement"]),
        ("Dynamics pass — match Rubinstein reference recording", "open", ["enhancement"]),
    ],
}


async def seed() -> None:
    db_url = settings.database_url or "sqlite+aiosqlite:///./muse.db"
    engine = create_async_engine(db_url)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:

        # ── 1. Gabriel's core user record ─────────────────────────────────
        existing_user = await session.get(User, GABRIEL_ID)
        if existing_user is None:
            session.add(User(id=GABRIEL_ID, created_at=_now(365)))
            print("[+] Created User: gabriel")
        else:
            print("[=] User gabriel already exists, skipping")

        # ── 2. Gabriel's public profile ────────────────────────────────────
        existing_profile = await session.get(MusehubProfile, GABRIEL_ID)
        if existing_profile is None:
            session.add(MusehubProfile(
                user_id=GABRIEL_ID,
                username="gabriel",
                display_name="Gabriel Cardona",
                bio=(
                    "Building Muse — a domain-agnostic VCS for multidimensional state. "
                    "Code, music, narrative, genomics. If it changes over time, Muse can version it."
                ),
                location="San Francisco, CA",
                website_url="https://musehub.ai",
                twitter_handle="cgcardona",
                is_verified=True,
                pinned_repo_ids=[],
                created_at=_now(365),
            ))
            print("[+] Created Profile: gabriel")
        else:
            print("[=] Profile gabriel already exists, skipping")

        await session.flush()

        # ── 3. Repos (code + MIDI) ─────────────────────────────────────────
        all_repos = CODE_REPOS + MIDI_REPOS

        for repo_def in all_repos:
            repo_id = repo_def["repo_id"]
            slug = repo_def["slug"]

            existing = await session.get(MusehubRepo, repo_id)
            if existing:
                print(f"[=] Repo gabriel/{slug} already exists, skipping")
                continue

            session.add(MusehubRepo(
                repo_id=repo_id,
                owner="gabriel",
                owner_user_id=GABRIEL_ID,
                name=repo_def["name"],
                slug=slug,
                description=repo_def["description"],
                visibility="public",
                tags=repo_def.get("tags", []),
                domain_meta=repo_def.get("domain_meta", {}),
                settings={"default_branch": "main"},
                created_at=_now(180),
            ))

            # Default branch
            session.add(MusehubBranch(
                branch_id=_uid(f"branch-{repo_id}-main"),
                repo_id=repo_id,
                name="main",
                head_commit_id=None,
            ))

            # Commits
            commits = COMMITS.get(slug, [])
            prev_sha: str | None = None
            head_sha: str | None = None
            for i, (msg, days_ago) in enumerate(commits):
                sha = _sha(f"{repo_id}-commit-{i}")[:40]
                session.add(MusehubCommit(
                    commit_id=sha,
                    repo_id=repo_id,
                    branch="main",
                    parent_ids=[prev_sha] if prev_sha else [],
                    message=msg,
                    author="gabriel",
                    timestamp=_now(days_ago),
                    snapshot_id=None,
                    created_at=_now(days_ago),
                ))
                prev_sha = sha
                head_sha = sha

            # Update branch head to latest commit
            if head_sha:
                branch = await session.get(MusehubBranch, _uid(f"branch-{repo_id}-main"))
                if branch:
                    branch.head_commit_id = head_sha

            # Issues
            for j, (title, state, labels) in enumerate(ISSUES.get(slug, [])):
                session.add(MusehubIssue(
                    issue_id=_uid(f"issue-{repo_id}-{j}"),
                    repo_id=repo_id,
                    number=j + 1,
                    title=title,
                    body=f"Tracking: {title}",
                    state=state,
                    labels=labels,
                    author="gabriel",
                    created_at=_now(60 - j * 5),
                ))

            # Release
            if commits:
                session.add(MusehubRelease(
                    release_id=_uid(f"release-{repo_id}-v0"),
                    repo_id=repo_id,
                    tag="v0.1.0",
                    title="Initial release",
                    body="First public release.",
                    commit_id=head_sha,
                    download_urls={},
                    author="gabriel",
                    is_draft=False,
                    is_prerelease=False,
                    created_at=_now(30),
                ))

            await session.flush()
            print(f"[+] Repo gabriel/{slug} ({len(commits)} commits, {len(ISSUES.get(slug, []))} issues)")

        # ── 4. Pin all code repos on gabriel's profile ─────────────────────
        profile = await session.get(MusehubProfile, GABRIEL_ID)
        if profile and not profile.pinned_repo_ids:
            profile.pinned_repo_ids = [r["repo_id"] for r in CODE_REPOS]
            print("[+] Pinned 5 code repos on gabriel's profile")

        await session.commit()

    print()
    print("=" * 60)
    print("PRODUCTION SEED COMPLETE")
    print("=" * 60)
    print()
    print("Mint your admin JWT (run inside the container):")
    print()
    print("  docker compose exec musehub python3 -c \"")
    print("  from musehub.auth.tokens import generate_access_code")
    print(f"  print(generate_access_code(user_id='{GABRIEL_ID}', duration_days=365, is_admin=True))")
    print("  \"")
    print()
    print("Then configure your Muse CLI:")
    print("  muse config set hub.token <token>")
    print("  muse config set hub.url https://musehub.ai")
    print()


if __name__ == "__main__":
    asyncio.run(seed())

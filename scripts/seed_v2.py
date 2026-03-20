"""MuseHub V2 seed script — domain-agnostic showcase data.

Generates a rich, realistic dataset that demonstrates Muse's domain-agnostic
multi-dimensional state versioning across both MIDI and Code domains.

New in V2 (run this AFTER the base seed_musehub.py):
  - Domain registry: @cgcardona/midi (21 dims), @cgcardona/code (10 langs)
  - 8 MIDI showcase repos with REAL PLAYABLE .mid files on disk
    (Bach WTC, Satie Gymnopédie, Chopin Nocturne, Beethoven Moonlight,
     + 4 original multi-track grooves)
  - 3 real GitHub repos cloned + ported to the Muse code domain:
      • github.com/cgcardona/muse         — VCS engine, ~198 commits
      • github.com/cgcardona/agentception — multi-agent orchestration, 250 commits
      • github.com/cgcardona/musehub      — this platform itself, ~37 commits
    Every real git commit is converted to a Muse commit with the original
    author, timestamp, message, and parent DAG.  HEAD file trees are stored
    as content-addressed MusehubObjects on disk.
  - Full MuseHub social layer: stars, issues, PRs, reviews, releases
  - All repos linked via domain_id to the domain registry

Requires network access during seeding to clone the three GitHub repos.
If a clone fails the repo is skipped with a warning (MIDI repos are unaffected).

Run inside the container:
  docker compose exec musehub python3 /app/scripts/seed_v2.py

Idempotent: pass --force to wipe V2 rows and re-insert.

Prerequisites:
  - seed_musehub.py must have run first (users + base repos exist)
  - OR pass --standalone to seed users + domains without the base data
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add parent so we can import musehub.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from musehub.config import settings
from musehub.db.models import AccessToken, User
from musehub.db.musehub_collaborator_models import MusehubCollaborator
from musehub.db.musehub_domain_models import MusehubDomain, MusehubDomainInstall
from musehub.db.musehub_label_models import (
    MusehubIssueLabel,
    MusehubLabel,
    MusehubPRLabel,
)
from musehub.db.musehub_models import (
    MusehubBranch,
    MusehubCommit,
    MusehubEvent,
    MusehubFollow,
    MusehubIssue,
    MusehubIssueComment,
    MusehubMilestone,
    MusehubNotification,
    MusehubObject,
    MusehubPRComment,
    MusehubPRReview,
    MusehubProfile,
    MusehubPullRequest,
    MusehubReaction,
    MusehubRelease,
    MusehubReleaseAsset,
    MusehubRepo,
    MusehubStar,
    MusehubViewEvent,
    MusehubWatch,
)

# Import our MIDI generator
sys.path.insert(0, str(Path(__file__).parent))
from midi_generator import MIDI_GENERATORS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UTC = timezone.utc

FORCE = "--force" in sys.argv
STANDALONE = "--standalone" in sys.argv


def _now(days: int = 0, hours: int = 0) -> datetime:
    return datetime.now(tz=UTC) - timedelta(days=days, hours=hours)


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _uid(seed: str) -> str:
    return str(uuid.UUID(bytes=hashlib.md5(seed.encode()).digest()))


# ---------------------------------------------------------------------------
# Stable IDs — never change between re-seeds so URLs stay valid
# ---------------------------------------------------------------------------

# Domain IDs
DOMAIN_MIDI = "domain-midi-cgcardona-0001"
DOMAIN_CODE = "domain-code-cgcardona-0001"

# Users (reuse from seed_musehub.py — must already exist unless --standalone)
GABRIEL = "user-gabriel-001"
SOFIA   = "user-sofia-002"
MARCUS  = "user-marcus-003"
YUKI    = "user-yuki-004"
AALIYA  = "user-aaliya-005"
CHEN    = "user-chen-006"
FATOU   = "user-fatou-007"
PIERRE  = "user-pierre-008"

# Historical composer users (also from base seed)
BACH      = "user-bach-000000009"
CHOPIN    = "user-chopin-00000010"
BEETHOVEN = "user-beethoven-000014"
SATIE     = "user-satie-00000017"

# V2 MIDI showcase repos
REPO_V2_WTC       = "repo-v2-wtc-prelude-001"
REPO_V2_GYMNO     = "repo-v2-gymnopedie-0001"
REPO_V2_NOCTURNE  = "repo-v2-nocturne-00001"
REPO_V2_MOONLIGHT = "repo-v2-moonlight-0001"
REPO_V2_NEO_SOUL  = "repo-v2-neo-soul-00001"
REPO_V2_MODAL     = "repo-v2-modal-jazz-0001"
REPO_V2_AFRO      = "repo-v2-afrobeat-00001"
REPO_V2_CHANSON   = "repo-v2-chanson-00001"

# V2 Code domain repos — real GitHub repos ported to Muse
REPO_V2_MUSE         = "repo-v2-muse-vcs-00001"   # cgcardona/muse (198 commits)
REPO_V2_AGENTCEPTION = "repo-v2-agentcept-00001"  # cgcardona/agentception (1175 commits)
REPO_V2_MUSEHUB_SRC  = "repo-v2-musehub-src-001"  # cgcardona/musehub (37 commits)

ALL_CONTRIBUTORS = [
    "gabriel", "sofia", "marcus", "yuki", "aaliya", "chen", "fatou", "pierre",
]

# ---------------------------------------------------------------------------
# Domain capability definitions
# ---------------------------------------------------------------------------

_MIDI_CAPS = {
    "dimensions": [
        {"id": "harmonic",    "name": "Harmonic",    "description": "Pitch classes, chord progressions, key areas",    "unit": "cents",      "token": "--dim-a"},
        {"id": "rhythmic",    "name": "Rhythmic",    "description": "Note timing, groove, quantisation",               "unit": "ms",         "token": "--dim-b"},
        {"id": "melodic",     "name": "Melodic",     "description": "Melodic contour, intervals, ornaments",           "unit": "semitones",  "token": "--dim-c"},
        {"id": "structural",  "name": "Structural",  "description": "Section boundaries, form, repetition",            "unit": "bars",       "token": "--dim-d"},
        {"id": "dynamic",     "name": "Dynamic",     "description": "Velocity, expression, articulation",              "unit": "MIDI vel",   "token": "--dim-e"},
        {"id": "timbral",     "name": "Timbral",     "description": "Instrument choice, program, sound design",        "unit": "GM no.",     "token": "--dim-a"},
        {"id": "spatial",     "name": "Spatial",     "description": "Pan position, stereo field",                      "unit": "degrees",    "token": "--dim-b"},
        {"id": "textural",    "name": "Textural",    "description": "Density, polyphony, voice independence",          "unit": "voices",     "token": "--dim-c"},
        {"id": "pedal",       "name": "Pedal",       "description": "Sustain, sostenuto, una corda events",            "unit": "bool",       "token": "--dim-d"},
        {"id": "microtonal",  "name": "Microtonal",  "description": "Pitch bend, microtonality, tuning",               "unit": "cents",      "token": "--dim-e"},
        {"id": "tempo",       "name": "Tempo",       "description": "BPM, rubato, tempo changes",                      "unit": "BPM",        "token": "--dim-a"},
        {"id": "time_sig",    "name": "Meter",       "description": "Time signature, metric modulation",               "unit": "n/d",        "token": "--dim-b"},
        {"id": "phrase",      "name": "Phrase",      "description": "Phrase lengths, breath marks",                    "unit": "beats",      "token": "--dim-c"},
        {"id": "ornament",    "name": "Ornament",    "description": "Trills, mordents, turns, grace notes",            "unit": "enum",       "token": "--dim-d"},
        {"id": "chord_type",  "name": "Chord Type",  "description": "Triad, seventh, extended, suspended",            "unit": "type",       "token": "--dim-e"},
        {"id": "voice_lead",  "name": "Voice Lead",  "description": "Smoothness, parallel motion, voice crossing",     "unit": "cents",      "token": "--dim-a"},
        {"id": "modulation",  "name": "Modulation",  "description": "Key change, pivot chord, tonicisation",           "unit": "keys",       "token": "--dim-b"},
        {"id": "register",    "name": "Register",    "description": "Pitch range, tessitura",                         "unit": "MIDI range", "token": "--dim-c"},
        {"id": "counterpoint","name": "Counterpoint","description": "Independence of voices, imitation, canon",        "unit": "score",      "token": "--dim-d"},
        {"id": "form",        "name": "Form",        "description": "ABA, rondo, sonata, through-composed",            "unit": "enum",       "token": "--dim-e"},
        {"id": "genre",       "name": "Genre",       "description": "Style tag: jazz, baroque, ambient, afrobeat",     "unit": "tag",        "token": "--dim-a"},
    ],
    "viewer_type":         "piano_roll",
    "merge_semantics":     "ot",
    "artifact_types":      ["audio/midi", "audio/mpeg", "image/webp"],
    "supported_commands":  [
        "muse piano-roll",   "muse listen",   "muse arrange",
        "muse analyze",      "muse groove-check", "muse export midi",
        "muse export mp3",   "muse diff --dim harmonic",
        "muse render",       "muse session start",
    ],
    "cli_help": "Muse MIDI domain — 21-dimensional musical state versioning",
}

_CODE_CAPS = {
    "dimensions": [
        {"id": "syntax",     "name": "Syntax",     "description": "AST structure, token diff",              "unit": "nodes",    "token": "--dim-a"},
        {"id": "semantics",  "name": "Semantics",  "description": "Type correctness, binding, scope",       "unit": "errors",   "token": "--dim-b"},
        {"id": "types",      "name": "Types",      "description": "Type signatures, generics, inference",   "unit": "types",    "token": "--dim-c"},
        {"id": "tests",      "name": "Tests",      "description": "Test coverage, assertions, pass rate",   "unit": "%",        "token": "--dim-d"},
        {"id": "docs",       "name": "Docs",       "description": "Docstring coverage, API docs",           "unit": "%",        "token": "--dim-e"},
        {"id": "complexity", "name": "Complexity", "description": "Cyclomatic complexity, depth",           "unit": "score",    "token": "--dim-a"},
        {"id": "deps",       "name": "Deps",       "description": "Import graph, dependency count",         "unit": "edges",    "token": "--dim-b"},
        {"id": "security",   "name": "Security",   "description": "Vulnerability scan, CVE score",          "unit": "CVE",      "token": "--dim-c"},
        {"id": "perf",       "name": "Perf",       "description": "Runtime benchmarks, big-O",             "unit": "ms",       "token": "--dim-d"},
        {"id": "style",      "name": "Style",      "description": "Linter score, format compliance",        "unit": "score",    "token": "--dim-e"},
    ],
    "viewer_type":         "symbol_graph",
    "merge_semantics":     "three_way",
    "artifact_types":      ["text/plain", "application/json", "text/x-python", "text/typescript", "text/x-rustsrc"],
    "supported_commands":  [
        "muse diff --dim syntax",  "muse diff --dim types",
        "muse analyze --lang python", "muse graph",
        "muse test-coverage",    "muse lint",
        "muse security-scan",    "muse perf-profile",
    ],
    "supported_languages": [
        "python", "typescript", "javascript", "rust", "go",
        "java", "c", "cpp", "ruby", "swift",
    ],
    "cli_help": "Muse Code domain — multi-dimensional symbol-graph versioning",
}


# ---------------------------------------------------------------------------
# MIDI repo definitions
# ---------------------------------------------------------------------------

MIDI_REPOS: list[dict[str, Any]] = [
    dict(
        repo_id=REPO_V2_WTC, owner="bach", slug="wtc-prelude-v2",
        owner_user_id=BACH, name="Well-Tempered Clavier — Prelude No.1",
        visibility="public", star_count=142, fork_count=18, days_ago=400,
        description=(
            "Bach's Prelude No. 1 in C major from The Well-Tempered Clavier (BWV 846). "
            "The definitive demonstration of equal temperament: 35 bars of pure arpeggiated harmony. "
            "Full 4/4 at 72 BPM — rendered from Urtext (Public Domain)."
        ),
        tags=["genre:baroque", "key:C", "instrument:piano", "stage:released", "emotion:serene", "complexity:high"],
        domain_meta={"key_signature": "C major", "tempo_bpm": 72, "time_signature": "4/4",
                     "composer": "J.S. Bach", "opus": "BWV 846", "period": "Baroque"},
        midi_key="wtc_prelude_c",
        midi_files=[("piano.mid", "wtc_prelude_c")],
    ),
    dict(
        repo_id=REPO_V2_GYMNO, owner="satie", slug="gymnopedie-no1",
        owner_user_id=SATIE, name="Gymnopédie No. 1",
        visibility="public", star_count=238, fork_count=31, days_ago=380,
        description=(
            "Erik Satie's most iconic work. D major, 3/4 at 52 BPM — 'Lent et douloureux'. "
            "Floating waltz chords in the left hand, a melody that seems to hover above time. "
            "Two-track: Melody (RH) + Accompaniment (LH). Public Domain."
        ),
        tags=["genre:impressionism", "key:D", "instrument:piano", "stage:released",
              "emotion:melancholic", "emotion:tender", "complexity:medium"],
        domain_meta={"key_signature": "D major", "tempo_bpm": 52, "time_signature": "3/4",
                     "composer": "Erik Satie", "opus": "Gymnopédie No. 1", "period": "Impressionism"},
        midi_key="gymnopedie_no1",
        midi_files=[("melody.mid", "gymnopedie_no1"), ("accompaniment.mid", "gymnopedie_no1")],
    ),
    dict(
        repo_id=REPO_V2_NOCTURNE, owner="chopin", slug="nocturne-op9-no2",
        owner_user_id=CHOPIN, name="Nocturne Op. 9 No. 2 in Eb major",
        visibility="public", star_count=195, fork_count=22, days_ago=350,
        description=(
            "Chopin's most celebrated nocturne. Eb major, 12/8 at 66 BPM. "
            "Wide arpeggiated left hand over a singing cantabile melody. "
            "Ornate RH rubato throughout. Two-track. Public Domain."
        ),
        tags=["genre:romantic", "key:Eb", "instrument:piano", "stage:released",
              "emotion:tender", "emotion:melancholic", "complexity:high"],
        domain_meta={"key_signature": "Eb major", "tempo_bpm": 66, "time_signature": "12/8",
                     "composer": "Frédéric Chopin", "opus": "Op. 9 No. 2", "period": "Romantic"},
        midi_key="chopin_nocturne_op9",
        midi_files=[("melody.mid", "chopin_nocturne_op9"), ("accompaniment.mid", "chopin_nocturne_op9")],
    ),
    dict(
        repo_id=REPO_V2_MOONLIGHT, owner="beethoven", slug="moonlight-sonata-mvt1",
        owner_user_id=BEETHOVEN, name="Moonlight Sonata — Mvt. I (Adagio)",
        visibility="public", star_count=312, fork_count=45, days_ago=360,
        description=(
            "Beethoven's 'Moonlight' Sonata, Op. 27 No. 2, Mvt. I — Adagio sostenuto. "
            "C# minor, 4/4 at 54 BPM. The iconic triplet arpeggios emerge from silence. "
            "Melody floats above the churning accompaniment. Public Domain."
        ),
        tags=["genre:classical", "key:C# minor", "instrument:piano", "stage:released",
              "emotion:melancholic", "emotion:mysterious", "complexity:high"],
        domain_meta={"key_signature": "C# minor", "tempo_bpm": 54, "time_signature": "4/4",
                     "composer": "Ludwig van Beethoven", "opus": "Op. 27 No. 2", "period": "Classical"},
        midi_key="moonlight_mvt1",
        midi_files=[("melody.mid", "moonlight_mvt1"), ("triplet_arpeggio.mid", "moonlight_mvt1")],
    ),
    dict(
        repo_id=REPO_V2_NEO_SOUL, owner="gabriel", slug="neo-soul-groove-v2",
        owner_user_id=GABRIEL, name="Neo-Soul Groove in F# minor",
        visibility="public", star_count=87, fork_count=11, days_ago=45,
        description=(
            "Original neo-soul composition in F# minor at 92 BPM. "
            "Three-track: Rhodes comping with lush 9th voicings, syncopated bassline, "
            "and a pocket-groove drum pattern. 16 bars. Domain-native original."
        ),
        tags=["genre:neo-soul", "key:F# minor", "instrument:rhodes", "instrument:bass",
              "instrument:drums", "stage:draft", "emotion:tender", "complexity:medium"],
        domain_meta={"key_signature": "F# minor", "tempo_bpm": 92, "time_signature": "4/4",
                     "composer": "gabriel", "tracks": 3},
        midi_key="neo_soul",
        midi_files=[("rhodes.mid", "neo_soul"), ("bass.mid", "neo_soul"), ("drums.mid", "neo_soul")],
    ),
    dict(
        repo_id=REPO_V2_MODAL, owner="marcus", slug="modal-jazz-sketch",
        owner_user_id=MARCUS, name="Modal Jazz Sketch in D Dorian",
        visibility="public", star_count=63, fork_count=8, days_ago=30,
        description=(
            "Original modal jazz sketch in D Dorian at 120 BPM. "
            "Piano shell voicings (3rd + 7th), walking bass, brushed snare. "
            "12 bars. Classic Coltrane/Miles modal approach."
        ),
        tags=["genre:jazz", "key:D Dorian", "instrument:piano", "instrument:bass",
              "instrument:drums", "stage:wip", "emotion:complex", "complexity:medium"],
        domain_meta={"key_signature": "D Dorian", "tempo_bpm": 120, "time_signature": "4/4",
                     "composer": "marcus", "tracks": 3},
        midi_key="modal_jazz",
        midi_files=[("piano.mid", "modal_jazz"), ("bass.mid", "modal_jazz"), ("drums.mid", "modal_jazz")],
    ),
    dict(
        repo_id=REPO_V2_AFRO, owner="aaliya", slug="afrobeat-pulse-g",
        owner_user_id=AALIYA, name="Afrobeat Pulse in G major",
        visibility="public", star_count=74, fork_count=9, days_ago=20,
        description=(
            "Original afrobeat groove in G major, 12/8 at 120 BPM. "
            "Interlocking piano offbeats, anchored bass, and a djembe pattern "
            "drawing from West African traditions. 8 bars, 3 tracks."
        ),
        tags=["genre:afrobeat", "key:G", "instrument:piano", "instrument:djembe",
              "instrument:bass", "stage:draft", "emotion:energetic", "complexity:medium"],
        domain_meta={"key_signature": "G major", "tempo_bpm": 120, "time_signature": "12/8",
                     "composer": "aaliya", "tracks": 3},
        midi_key="afrobeat",
        midi_files=[("piano.mid", "afrobeat"), ("bass.mid", "afrobeat"), ("djembe.mid", "afrobeat")],
    ),
    dict(
        repo_id=REPO_V2_CHANSON, owner="pierre", slug="chanson-minimale-v2",
        owner_user_id=PIERRE, name="Chanson Minimale in A major",
        visibility="public", star_count=29, fork_count=3, days_ago=14,
        description=(
            "Original chanson minimale in A major, 3/4 at 52 BPM. "
            "Waltz LH ostinato, folk-like RH melody. Solo piano, 48 bars. "
            "Satie would approve."
        ),
        tags=["genre:chanson", "key:A", "instrument:piano", "stage:wip",
              "emotion:tender", "complexity:low"],
        domain_meta={"key_signature": "A major", "tempo_bpm": 52, "time_signature": "3/4",
                     "composer": "pierre", "tracks": 1},
        midi_key="chanson",
        midi_files=[("piano.mid", "chanson")],
    ),
]

# ---------------------------------------------------------------------------
# Code repo definitions — real GitHub repos, ported to the Muse code domain.
# Each entry includes a github_url; the seeder clones it, walks the full git
# DAG, and converts every commit + HEAD file tree to Muse objects/commits.
# max_commits caps the import for very large repos.
# ---------------------------------------------------------------------------

CODE_REPOS: list[dict[str, Any]] = [
    dict(
        repo_id=REPO_V2_MUSE,
        owner="gabriel", slug="muse",
        owner_user_id=GABRIEL,
        name="Muse — domain-agnostic VCS engine",
        visibility="public", star_count=214, fork_count=19, days_ago=180,
        description=(
            "A domain-agnostic version control system for multidimensional state. "
            "Plugin architecture: snapshot, diff, merge, drift, apply, schema. "
            "MIDI (21 dimensions) and Code (10 languages) are the reference implementations. "
            "CRDT mode enables convergent multi-agent writes with no conflict state. "
            "Ported from github.com/cgcardona/muse — full git history converted to Muse."
        ),
        tags=["python", "vcs", "domain-agnostic", "crdt", "midi", "code", "agents", "paradigm-shift"],
        domain_meta={
            "primary_language": "python", "license": "proprietary",
            "test_framework": "pytest", "python_version": "3.14",
            "source_repo": "github.com/cgcardona/muse",
        },
        github_url="https://github.com/cgcardona/muse",
        max_commits=None,  # import all ~198 commits
    ),
    dict(
        repo_id=REPO_V2_AGENTCEPTION,
        owner="gabriel", slug="agentception",
        owner_user_id=GABRIEL,
        name="AgentCeption — multi-agent orchestration",
        visibility="public", star_count=312, fork_count=47, days_ago=240,
        description=(
            "Multi-agent orchestration system for AI-powered development workflows. "
            "Brain dump → structured plan → GitHub issues → agent org tree → PRs → merged. "
            "Each agent has a cognitive architecture (historical figures + archetypes + skill domains). "
            "Supports Anthropic Claude and any Ollama-compatible local model. "
            "Ported from github.com/cgcardona/agentception — first 250 commits of 1175."
        ),
        tags=["python", "typescript", "agents", "orchestration", "fastapi", "htmx", "ai", "llm"],
        domain_meta={
            "primary_language": "python", "secondary_language": "typescript",
            "license": "MIT", "test_framework": "pytest",
            "source_repo": "github.com/cgcardona/agentception",
        },
        github_url="https://github.com/cgcardona/agentception",
        max_commits=250,  # sample of the full 1175-commit history
    ),
    dict(
        repo_id=REPO_V2_MUSEHUB_SRC,
        owner="gabriel", slug="musehub",
        owner_user_id=GABRIEL,
        name="MuseHub — the platform (self-hosted)",
        visibility="public", star_count=89, fork_count=12, days_ago=90,
        description=(
            "MuseHub itself — the domain-agnostic collaboration platform powered by Muse VCS. "
            "FastAPI + SQLAlchemy + Jinja2 + HTMX + TypeScript. "
            "Full MCP 2025-11-25 implementation: 32 tools, 20 resources, 8 prompts. "
            "This very codebase, versioned on itself using the Muse code domain. "
            "Ported from github.com/cgcardona/musehub — full git history."
        ),
        tags=["python", "typescript", "fastapi", "htmx", "mcp", "vcs", "platform", "meta"],
        domain_meta={
            "primary_language": "python", "secondary_language": "typescript",
            "license": "proprietary", "test_framework": "pytest",
            "source_repo": "github.com/cgcardona/musehub",
        },
        github_url="https://github.com/cgcardona/musehub",
        max_commits=None,  # import all ~37 commits
    ),
]

# ---------------------------------------------------------------------------
# Commit message templates
# ---------------------------------------------------------------------------

_MIDI_COMMITS: dict[str, list[tuple[str, str]]] = {
    REPO_V2_WTC: [
        ("init: Bach WTC Prelude No. 1 in C major — 4/4 at 72 BPM", "gabriel"),
        ("feat(harmony): arpeggiated C major — 16 sixteenth notes per bar", "gabriel"),
        ("feat(bars-1-8): complete first 8 bars — chord progression established", "gabriel"),
        ("feat(bars-9-16): Dm7 and G7 approaches — circle-of-5ths descent", "sofia"),
        ("feat(bars-17-24): secondary dominant seventh chain", "gabriel"),
        ("refactor(velocity): humanize 16th note accents — beat 1 +12vel", "gabriel"),
        ("feat(bars-25-35): climactic progression and final C major resolution", "chen"),
        ("fix(bar-3): correct Bdim7 chord voicing — was missing the B1 bass", "gabriel"),
        ("feat(pedal): add sustain pedal changes every 2 bars for resonance", "sofia"),
        ("refactor(tempo): adjust to 72 BPM from 80 — more stately", "pierre"),
        ("feat(dynamics): pp opening, gradual mf crescendo to bar 20", "gabriel"),
        ("feat(ornamentation): add grace notes to inner voice bar 14", "sofia"),
        ("fix(bar-24): V7 resolution voice-leading — remove parallel octaves", "gabriel"),
        ("refactor(phrasing): 4-bar groupings marked with diminuendo signs", "chen"),
        ("feat(tag): v1.0 — canonical WTC Prelude release", "gabriel"),
        ("feat(transposition): add Ab major variant — bars 1-12 only", "sofia"),
        ("fix(ab-variant): correct treble clef note B♭4→A♭4 in bar 3", "gabriel"),
        ("feat(analysis): add harmonic Roman-numeral annotations in metadata", "yuki"),
        ("refactor(notation): normalize all note durations to nearest 1/64", "gabriel"),
        ("feat(v2): Book I Prelude — second encoding pass from Bärenreiter", "pierre"),
        ("fix(v2): correct bar 23 chord — was Am/C, should be F/C", "gabriel"),
        ("feat(visualization): add metadata for piano roll colour-by-dimension", "gabriel"),
        ("refactor(merge): incorporate sofia's dynamics into main branch", "gabriel"),
        ("fix(ledger-lines): correct MIDI pitch for bass voice in bars 29-30", "chen"),
        ("feat(release-v2): final reviewed version — bar 35 fermata included", "gabriel"),
    ],
    REPO_V2_GYMNO: [
        ("init: Gymnopédie No. 1 — D major, 3/4, 52 BPM (Lent et douloureux)", "pierre"),
        ("feat(lh): waltz chord pattern — D major root / G major on beat 2-3", "pierre"),
        ("feat(rh): opening melody — pickup A4 into bar 2 E♭4 descent", "sofia"),
        ("feat(bars-1-8): first phrase — gentle rise and fall on A4", "pierre"),
        ("refactor(velocity): reduce chord loudness — melody must sing above", "pierre"),
        ("feat(bars-9-16): second phrase — higher register, slight variation", "sofia"),
        ("feat(bars-17-24): development phrase — mode inflection on bar 21", "pierre"),
        ("fix(bar-5): correct LH — G major chord, was seeding Gm", "pierre"),
        ("feat(bars-25-32): restatement — pppp, dissolving into silence", "pierre"),
        ("refactor(articulation): add tenuto marks on RH long notes", "pierre"),
        ("feat(arpeggio-roll): LH chord rolls — 8ms stagger between voices", "sofia"),
        ("fix(bar-20): melody note — F#4 was missing in RH track", "pierre"),
        ("feat(pedal): una corda from bar 25 onward — ppp texture", "pierre"),
        ("refactor(dynamics): mark mm.1-8 piano, mm.9-24 mp, mm.25-32 ppp", "sofia"),
        ("feat(v1.0): first complete version — 32 bars fully rendered", "pierre"),
        ("feat(rubato-marks): add tempo flexibility annotations to metadata", "gabriel"),
        ("feat(orchestration): add strings variant — melody doubled by flute", "chen"),
        ("fix(strings-var): correct flute range — moved octave up from bar 12", "chen"),
        ("feat(orchestra): add harp arpeggio in strings arrangement", "sofia"),
        ("refactor(strings): balance strings against piano in arrangement", "pierre"),
        ("feat(tag-v2): v2.0 — orchestrated version complete", "pierre"),
    ],
    REPO_V2_NOCTURNE: [
        ("init: Nocturne Op. 9 No. 2 — Eb major, 12/8, 66 BPM", "aaliya"),
        ("feat(lh): arpeggiated Eb major chord — 8 notes per beat", "aaliya"),
        ("feat(rh): iconic opening melody — bars 1-4 established", "aaliya"),
        ("feat(lh-bass): wide-span bass — Eb2 to upper chord tones", "gabriel"),
        ("feat(bars-5-8): ornate RH variations — turns and mordents added", "aaliya"),
        ("refactor(lh-roll): humanize chord roll — random 5-15ms stagger", "aaliya"),
        ("feat(bars-9-12): closing statement — pppp fade", "aaliya"),
        ("fix(bar-6): melody note D♭ was missing F at top of chord", "gabriel"),
        ("feat(dynamics): pp opening, cresc to mf at bar 5 climax", "aaliya"),
        ("refactor(tempo): ritardando in last 2 bars — molto rubato", "pierre"),
        ("feat(ornamentation): trills on bar 2 beat 3 — 6-note trill", "sofia"),
        ("fix(ornament): trill starts on upper note per Chopin convention", "aaliya"),
        ("feat(pedal): broad sustain throughout — clearing only at LH change", "aaliya"),
        ("feat(tag-v1): Op. 9 No. 2 — v1.0 complete", "gabriel"),
        ("feat(extended): extend to Op. 9 No. 1 — Bb minor added", "aaliya"),
        ("fix(ext): Bb minor LH voicing corrected — was Bb3 not Bb2", "aaliya"),
        ("refactor(extended): unify dynamics across both nocturnes", "sofia"),
        ("feat(tag-v2): Nocturnes v2.0 — two nocturnes complete", "aaliya"),
    ],
    REPO_V2_MOONLIGHT: [
        ("init: Moonlight Sonata Mvt. I — C# minor, 4/4, 54 BPM (Adagio)", "sofia"),
        ("feat(lh): C# minor triplet arpeggio — 12 triplet 8ths per bar", "gabriel"),
        ("feat(rh): bare RH entry on bar 4 — long sustained Cs4+12", "sofia"),
        ("feat(bars-1-4): atmospheric opening — arpeggio only, no melody", "gabriel"),
        ("feat(bars-5-8): melody enters — F# minor region", "sofia"),
        ("refactor(lh): even triplet spacing — 1/3 beat per note", "gabriel"),
        ("feat(bars-9-12): A major colouring — shift to relative brightness", "sofia"),
        ("feat(bars-13-16): final resolution back to C# minor", "gabriel"),
        ("fix(bar-7): LH pitch — C#dim7 was missing the G#", "sofia"),
        ("feat(dynamics): ppp opening, gradual swell to mf at bar 9", "gabriel"),
        ("feat(pedal): sostenuto indication throughout — Beethoven instruction", "pierre"),
        ("refactor(tempo): Adagio quarter = 54 confirmed — no rallentando", "sofia"),
        ("fix(bar-13): RH Cs4+12 held note — was cut short by 1 beat", "gabriel"),
        ("feat(ornament): accent marks on triplet beat 1 of each bar", "sofia"),
        ("feat(tag-v1): Moonlight Mvt. I — v1.0 complete (16 bars)", "gabriel"),
        ("feat(mvt2): Mvt. II (Allegretto) — 8 bars stub added", "sofia"),
        ("feat(mvt2): Mvt. II melody — Ab major, graceful dance character", "sofia"),
        ("fix(mvt2): Allegretto tempo marker — set to 100 BPM not 60", "gabriel"),
        ("feat(tag-v2): v2.0 — two movements complete", "sofia"),
        ("refactor(unified): merge Mvt. I and II into single multi-track file", "gabriel"),
    ],
    REPO_V2_NEO_SOUL: [
        ("init: Neo-Soul Groove in F# minor — 92 BPM, 4/4", "gabriel"),
        ("feat(rhodes): F# minor 9 shell voicings — rootless A-C#-E-G#", "gabriel"),
        ("feat(bass): syncopated bassline — root-to-5th-to-octave movement", "gabriel"),
        ("feat(drums): kick-snare-hat pocket groove — ghost notes on snare", "gabriel"),
        ("feat(comp): offbeat chord stabs — beats 2.5 and 3.75", "marcus"),
        ("refactor(rhodes): velocity humanization — ±12 vel on beat 1", "gabriel"),
        ("feat(bars-5-8): harmonic shift — A major colour for 2 bars", "gabriel"),
        ("feat(bass-fill): 16th note fill into bar 9 — chromatic approach", "marcus"),
        ("fix(drums): hi-hat pattern — was double-hitting on beat 3.5", "gabriel"),
        ("feat(dynamics): verse pp → chorus mf build over 4 bars", "gabriel"),
        ("feat(bars-9-12): D major escape chord — neo-soul characteristic", "marcus"),
        ("refactor(bass): add sub-bass doublings on root notes", "gabriel"),
        ("feat(bars-13-16): return to F# minor — resolution and outro", "gabriel"),
        ("fix(outro): rhodes chord on bar 15 — was E minor, corrected to Cs", "gabriel"),
        ("feat(v1): 16-bar loop complete — groove locked", "gabriel"),
    ],
    REPO_V2_MODAL: [
        ("init: Modal Jazz in D Dorian — 120 BPM, shell voicings", "marcus"),
        ("feat(piano): Dm7 shell — F + C as 3rd and 7th, no root", "marcus"),
        ("feat(bass): walking bass — D2-E2-F2-G2 ascending Dorian", "marcus"),
        ("feat(drums): brushed snare ride pattern — jazz feel", "marcus"),
        ("feat(comp): reharmonize bar 3 — Gm7sus for colour", "gabriel"),
        ("refactor(piano): vary voicings each 4 bars — avoid static texture", "marcus"),
        ("feat(bars-5-8): add Am7 colour — vi degree of Dorian", "marcus"),
        ("fix(bass): bar 6 walking line was chromatically wrong — corrected", "marcus"),
        ("feat(bars-9-12): climax — higher register piano voicings", "gabriel"),
        ("refactor(drums): add ride cymbal pings on beats 2 and 4", "marcus"),
        ("fix(piano): bar 11 top voice — Bb was out of Dorian mode", "marcus"),
        ("feat(v1): 12-bar modal sketch complete", "gabriel"),
    ],
    REPO_V2_AFRO: [
        ("init: Afrobeat Pulse in G major — 12/8, 120 BPM", "aaliya"),
        ("feat(piano): offbeat chord stabs on .5 of each dotted-quarter beat", "aaliya"),
        ("feat(bass): one-drop bass — G2 on beat 1, D3 on beat 1.5", "fatou"),
        ("feat(djembe): bass tone-slap-tone-slap West African pattern", "fatou"),
        ("refactor(piano): interlocking — must NOT clash with bass rhythm", "aaliya"),
        ("feat(bars-3-4): add Ab colour chord — Lagos jazz inflection", "aaliya"),
        ("fix(djembe): slap note velocity — was too quiet at 40, boosted to 80", "fatou"),
        ("feat(bars-5-8): call-and-response between piano and djembe", "aaliya"),
        ("refactor(bass): add octave jump at bar 5 — huge groove moment", "fatou"),
        ("fix(piano): bar 6 chord — F# was wrong note for G Dorian context", "aaliya"),
        ("feat(v1): 8-bar loop ready for extension", "gabriel"),
    ],
    REPO_V2_CHANSON: [
        ("init: Chanson Minimale — A major, 3/4, 52 BPM", "pierre"),
        ("feat(lh): waltz ostinato — A2-E3-A3 arpeggiated pattern", "pierre"),
        ("feat(rh): folk melody opening — E4 to Cs4 descent", "pierre"),
        ("feat(bars-1-8): first verse phrase — simple, direct", "pierre"),
        ("refactor(melody): add passing tones — Cs4→B3 smooth leading", "pierre"),
        ("feat(bars-9-16): development — reach up to A4 climax", "pierre"),
        ("fix(bar-12): RH note was Bb4 — should be A4 in A major", "pierre"),
        ("feat(bars-17-24): secondary phrase — rhythmic augmentation", "sofia"),
        ("feat(bars-25-32): return to opening — now marked ppp", "pierre"),
        ("refactor(lh): reduce LH velocity in bars 25-32 to pppp", "pierre"),
        ("feat(coda): sustained A3 chord — six bars, fade to silence", "pierre"),
        ("fix(coda): chord sustain was 2 bars — extended to 6 per intent", "pierre"),
        ("feat(v1): solo piano version complete — 48 bars", "pierre"),
    ],
}

# ---------------------------------------------------------------------------
# Issue templates per repo
# ---------------------------------------------------------------------------

_ISSUES: dict[str, list[dict[str, Any]]] = {
    REPO_V2_WTC: [
        {"title": "Add Book II preludes (BWV 870-893)", "body": "Currently only Book I is encoded. Book II should be added systematically.", "state": "open", "labels": ["enhancement"]},
        {"title": "Incorrect trill in Prelude No. 7 bar 3", "body": "The ornament should be a mordent (lower), not a trill starting from above.", "state": "closed", "labels": ["bug"]},
        {"title": "Add MIDI velocity curve analysis", "body": "The dynamic profile across 35 bars could be visualized as a dimension plot.", "state": "open", "labels": ["enhancement", "analysis"]},
        {"title": "Export to MusicXML format", "body": "Some users need MusicXML for notation software import.", "state": "open", "labels": ["feature-request"]},
        {"title": "Parallel octaves in Fugue No. 5 bar 14", "body": "Voice-leading violation in the subject entry needs correction.", "state": "closed", "labels": ["bug"]},
    ],
    REPO_V2_GYMNO: [
        {"title": "Add Gymnopédie No. 2 and No. 3", "body": "Complete the set — No. 2 in C major and No. 3 in G major.", "state": "open", "labels": ["enhancement"]},
        {"title": "Slow the tempo slightly — 48 BPM feels more authentic", "body": "Period recordings by Reinbert de Leeuw suggest 48-50 BPM.", "state": "open", "labels": ["discussion"]},
        {"title": "Staccato on LH beat 1 breaking waltz feel", "body": "Beat 1 should be legatissimo, not staccato — reverting.", "state": "closed", "labels": ["bug"]},
        {"title": "Add orchestral arrangement by Debussy", "body": "Debussy famously orchestrated Gymnopédie 1 and 3 — add as variant.", "state": "open", "labels": ["enhancement"]},
    ],
    REPO_V2_NEO_SOUL: [
        {"title": "Extend to 32 bars with bridge section", "body": "The groove needs a contrasting B-section — consider D major area.", "state": "open", "labels": ["enhancement"]},
        {"title": "Add percussion variations — hi-hat pattern too repetitive", "body": "Bar 4 and 8 could have open hi-hat fills for variety.", "state": "open", "labels": ["enhancement"]},
        {"title": "Rhodes voicing clashes with bass on bar 9", "body": "The A3 in the chord conflicts with the A2 bass note — revoice.", "state": "closed", "labels": ["bug"]},
        {"title": "Export stems as individual tracks", "body": "Need separate MIDI files per instrument for DAW import.", "state": "open", "labels": ["feature-request"]},
        {"title": "BPM feels rushed — try 88 BPM", "body": "Classic neo-soul sits at 85-90 BPM. 92 is slightly fast for this groove.", "state": "open", "labels": ["discussion"]},
    ],
    REPO_V2_MUSE: [
        {"title": "Add WebAssembly domain plugin", "body": "A Wasm plugin would let browser-native state versioning work without a server round-trip. The plugin interface is clean enough to support this.", "state": "open", "labels": ["enhancement", "performance"]},
        {"title": "MIDI merge conflict on simultaneous pitch-bend edits in same track", "body": "When two branches each modify pitch_bend in the same bar, the three-way merge should use the OT delta algebra, but currently falls back to 'ours'. Steps to reproduce: muse checkout -b a; edit pitch bend bar 4; muse checkout main; edit pitch bend bar 4 differently; muse merge a.", "state": "open", "labels": ["bug"]},
        {"title": "muse log --graph rendering breaks at 100+ commits", "body": "The ASCII graph renderer overflows the terminal at wide histories. This is a known issue in the graph module.", "state": "closed", "labels": ["bug"]},
        {"title": "CRDT join is O(n²) for large note sequences", "body": "RGA merge in _crdt_notes.py iterates the full tombstone list for every insert. Should switch to a skip-list or B-tree for the tombstone index.", "state": "open", "labels": ["performance"]},
        {"title": "Add support for ABC music notation format as a third domain", "body": "ABC notation is widely used in folk music. A domain plugin would let folk musicians use Muse.", "state": "open", "labels": ["feature-request"]},
        {"title": "muse revert fails when parent commit has a CRDT merge", "body": "Reverting a commit that was produced by a CRDT join panics in the merge engine because the inverse delta cannot be computed for tombstoned notes.", "state": "closed", "labels": ["bug"]},
        {"title": "Document the MuseDomainPlugin.schema() return type", "body": "The DomainSchema TypedDict is not fully documented — what keys are required vs optional? The plugin authoring guide is incomplete here.", "state": "open", "labels": ["docs"]},
    ],
    REPO_V2_AGENTCEPTION: [
        {"title": "Agent tree hangs when coordinator returns an empty plan", "body": "If the coordinator agent's LLM response parses to an empty PlanSpec (no phases), the orchestration loop spins indefinitely waiting for work items that never arrive.", "state": "closed", "labels": ["bug"]},
        {"title": "Mission Control board doesn't update when PR is merged outside AgentCeption", "body": "If a PR is merged manually on GitHub (not via the MC merge button), the issue card stays in PR_OPEN state indefinitely until the next polling cycle (5 min).", "state": "open", "labels": ["bug"]},
        {"title": "Add support for Claude claude-opus-4-6 as coordinator model", "body": "claude-opus-4-6 has a much larger context window which helps coordinators reason about full codebases. Should be selectable per-node in the org designer.", "state": "open", "labels": ["enhancement"]},
        {"title": "Local LLM connection drops after 30 minutes of inactivity", "body": "When using LOCAL_LLM_PROVIDER=ollama, long-running worker agents lose their HTTP connection after idle timeout. Should retry with exponential backoff.", "state": "open", "labels": ["bug", "local-llm"]},
        {"title": "Worker agents don't respect .gitattributes merge strategy", "body": "Workers create PRs that sometimes contain merge conflicts in files marked with 'merge=ours' in .gitattributes. The worktree setup doesn't configure the merge driver.", "state": "closed", "labels": ["bug"]},
        {"title": "Add Muse VCS as an alternative backend to Git worktrees", "body": "Since AgentCeption and Muse are from the same author, it would be a natural fit to let agents commit to a Muse repo instead of a Git worktree. Would unlock multi-domain agent collaboration.", "state": "open", "labels": ["feature-request", "muse-integration"]},
        {"title": "Cognitive architecture presets not persisted across container restarts", "body": "Custom org presets saved in the UI are stored in memory only. They should be written to the org-presets.yaml file or to the DB.", "state": "closed", "labels": ["bug"]},
    ],
    REPO_V2_MUSEHUB_SRC: [
        {"title": "Piano roll doesn't render MIDI files larger than 500KB", "body": "The /parse-midi endpoint times out on dense orchestral MIDI. Need streaming parse or a size-gated fast path.", "state": "open", "labels": ["bug", "performance"]},
        {"title": "MCP resource musehub://trending returns 500 when no repos are starred", "body": "The trending query performs ORDER BY star_count DESC — if the result set is empty, the serializer raises AttributeError on a None row.", "state": "closed", "labels": ["bug"]},
        {"title": "Domain install count doesn't decrement on uninstall", "body": "Calling DELETE /domains/{id}/install correctly removes the MusehubDomainInstall row but never decrements install_count on the domain row.", "state": "open", "labels": ["bug"]},
        {"title": "Code domain symbol graph viewer not yet implemented", "body": "The @cgcardona/code domain declares viewer_type='symbol_graph' but the frontend only has piano_roll.html. Need a symbol_graph.html template + TypeScript renderer.", "state": "open", "labels": ["enhancement", "frontend"]},
        {"title": "Search results don't include repo descriptions in the match", "body": "Full-text search only indexes repo name and tags. Descriptions should be included in the tsvector so searching 'multidimensional' finds relevant repos.", "state": "open", "labels": ["enhancement"]},
        {"title": "elicitation tools silently fail when Mcp-Session-Id is missing", "body": "Interactive tools (compose planner, PR review) call ctx.elicit() which raises if no session exists, but the error is swallowed and the tool returns an empty response.", "state": "closed", "labels": ["bug"]},
    ],
}

# ---------------------------------------------------------------------------
# Git → Muse importer
# ---------------------------------------------------------------------------

# Source-code file extensions we store as Muse objects.  Lock files, generated
# output, and binaries are excluded.
_CODE_INCLUDE_EXT = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".rs", ".go", ".rb", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".kt", ".swift", ".sh", ".bash", ".zsh",
    ".md", ".rst", ".txt",
    ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".env.example",
    ".html", ".css", ".scss", ".sql",
}

_CODE_EXCLUDE_NAMES = {
    "package-lock.json", "poetry.lock", "Cargo.lock", "yarn.lock",
    "pnpm-lock.yaml", "Pipfile.lock", "composer.lock",
}

_CODE_EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target",  # Rust build artefacts
}


def _git_code_filter(path: str) -> bool:
    """Return True if this repo path should be stored as a Muse object."""
    p = Path(path)
    if p.name in _CODE_EXCLUDE_NAMES:
        return False
    if any(part in _CODE_EXCLUDE_DIRS for part in p.parts):
        return False
    return p.suffix in _CODE_INCLUDE_EXT


async def _import_github_repo(
    db: AsyncSession,
    r: dict[str, Any],
    domain_id: str,
) -> tuple[int, int]:
    """Clone a GitHub repo, walk its full git DAG, and import into Muse.

    For each git commit we create one MusehubCommit, preserving the real
    message, author name, timestamp, and parent graph.  HEAD file contents
    are written to disk and linked as MusehubObjects.

    Returns (commits_inserted, objects_inserted).
    """
    repo_id = r["repo_id"]
    github_url = r["github_url"]
    max_commits: int | None = r.get("max_commits")

    print(f"    🌐 Cloning {github_url}…", flush=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "repo"

        # Shallow-ish clone for big repos, full for small ones
        depth_args = ["--depth", str(max_commits + 50)] if max_commits else []
        clone = subprocess.run(
            ["git", "clone", "--quiet", "--no-single-branch"] + depth_args + [github_url, str(repo_path)],
            capture_output=True, text=True, timeout=180,
        )
        if clone.returncode != 0:
            print(f"    ⚠️  Clone failed ({clone.stderr[:120].strip()}) — skipping {r['slug']}")
            return 0, 0

        def _git(*args: str) -> str:
            return subprocess.run(
                ["git"] + list(args),
                cwd=repo_path, capture_output=True, text=True, check=True,
            ).stdout.strip()

        # ── Commit log (oldest → newest) ────────────────────────────────────
        # %x1f = ASCII unit-separator — safe delimiter inside commit messages
        raw_log = _git("log", "--format=%H\x1f%an\x1f%at\x1f%s", "--all", "--reverse")
        commits_raw = [l for l in raw_log.split("\n") if l.strip()]
        if max_commits:
            commits_raw = commits_raw[:max_commits]

        # ── Parent map ───────────────────────────────────────────────────────
        parent_lines = _git("log", "--format=%H %P", "--all", "--reverse").split("\n")
        parent_map: dict[str, list[str]] = {}
        for line in parent_lines:
            parts = line.strip().split()
            if parts:
                parent_map[parts[0]] = parts[1:] if len(parts) > 1 else []

        # ── Branch names + commit-to-branch map ─────────────────────────────
        # Fetch both local and remote-tracking branches after a --no-single-branch clone.
        branches_raw = _git("branch", "-a", "--format=%(refname:short)").split("\n")
        branch_names_raw = [b.strip() for b in branches_raw if b.strip()]
        # Normalise remote-tracking refs (origin/foo → foo), drop HEAD pointers
        branch_names_set: set[str] = set()
        for b in branch_names_raw:
            if "HEAD" in b:
                continue
            b = b.removeprefix("origin/").removeprefix("remotes/origin/")
            if b:
                branch_names_set.add(b)
        branch_names = list(branch_names_set) or ["main"]

        try:
            head_branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "main"
        except Exception:
            head_branch = branch_names[0]

        # Build a map: git_hash → branch name.
        # For each branch, walk "git log <branch> --not <other_branches...>" to find
        # commits exclusive to that branch; shared (merge-base) commits fall back to
        # head_branch so every commit gets exactly one label.
        print(f"      🔀 Mapping {len(branch_names)} branch(es)…", flush=True)
        commit_branch_map: dict[str, str] = {}
        for bname in branch_names:
            try:
                other_excludes = [f"^{ob}" for ob in branch_names if ob != bname]
                branch_log = _git(
                    "log", f"origin/{bname}", "--format=%H",
                    *other_excludes,
                )
                for gh in branch_log.split("\n"):
                    gh = gh.strip()
                    if gh and gh not in commit_branch_map:
                        commit_branch_map[gh] = bname
            except Exception:
                pass  # branch may not have a remote counterpart — fall through

        # ── File objects — store HEAD files for main + all branch tips ───────
        # We store the main HEAD plus unique files from each branch tip so that
        # the diff viewer can show code for any branch.
        print(f"      📁 Storing files (HEAD + branch tips)…", flush=True)
        objects_count = 0
        refs_to_store = ["HEAD"] + [f"origin/{b}" for b in branch_names if b != head_branch]

        async def _store_files_at_ref(ref: str) -> int:
            stored = 0
            try:
                file_list = _git("ls-tree", "-r", "--name-only", ref).split("\n")
            except Exception:
                return 0
            for fpath in file_list:
                fpath = fpath.strip()
                if not fpath or not _git_code_filter(fpath):
                    continue
                try:
                    blob = subprocess.run(
                        ["git", "show", f"{ref}:{fpath}"],
                        cwd=repo_path, capture_output=True, timeout=10,
                    )
                    if blob.returncode != 0:
                        continue
                    content_bytes = blob.stdout
                    if len(content_bytes) > 300_000:
                        continue

                    obj_id = "sha256:" + hashlib.sha256(content_bytes).hexdigest()
                    ext = Path(fpath).suffix or ".txt"
                    dest = _objects_dir() / f"{obj_id.replace(':', '_')}{ext}"
                    if not dest.exists():
                        dest.write_bytes(content_bytes)

                    await db.execute(
                        text("""
                            INSERT INTO musehub_objects
                              (object_id, repo_id, path, size_bytes, disk_path, created_at)
                            VALUES (:oid, :rid, :path, :size, :dpath, now())
                            ON CONFLICT (object_id) DO NOTHING
                        """),
                        {
                            "oid": obj_id, "rid": repo_id,
                            "path": fpath,
                            "size": len(content_bytes),
                            "dpath": str(dest),
                        },
                    )
                    stored += 1
                except Exception:
                    pass
            return stored

        for ref in refs_to_store:
            objects_count += await _store_files_at_ref(ref)

        # ── Commit import ────────────────────────────────────────────────────
        print(f"      📜 Importing {len(commits_raw)} commits…", flush=True)
        git_to_muse: dict[str, str] = {}
        commits_count = 0
        last_commit_id: str | None = None

        for line in commits_raw:
            parts = line.split("\x1f", 3)
            if len(parts) < 4:
                continue
            git_hash, author_name, timestamp_str, subject = parts

            try:
                ts = datetime.fromtimestamp(int(timestamp_str), tz=UTC)
            except (ValueError, OverflowError, OSError):
                ts = datetime.now(tz=UTC)

            parent_git = parent_map.get(git_hash, [])
            parent_muse = [git_to_muse[p] for p in parent_git if p in git_to_muse]

            muse_cid = _sha(f"git-import-{repo_id}-{git_hash}")
            git_to_muse[git_hash] = muse_cid

            # Use the branch we mapped for this commit; fall back to head_branch
            commit_branch = commit_branch_map.get(git_hash, head_branch)

            await db.execute(
                text("""
                    INSERT INTO musehub_commits
                      (commit_id, repo_id, branch, parent_ids, message, author, timestamp, snapshot_id)
                    VALUES (:cid, :rid, :branch, :parents, :msg, :author, :ts, :snap)
                    ON CONFLICT (commit_id) DO NOTHING
                """),
                {
                    "cid": muse_cid,
                    "rid": repo_id,
                    "branch": commit_branch,
                    "parents": json.dumps(parent_muse),
                    "msg": subject[:1000],
                    "author": author_name[:120],
                    "ts": ts,
                    "snap": _sha(f"snap-git-{repo_id}-{git_hash}"),
                },
            )
            last_commit_id = muse_cid
            commits_count += 1

        # ── Branches ─────────────────────────────────────────────────────────
        for bname in branch_names:
            try:
                branch_head_git = _git("rev-parse", bname)
                branch_head_muse = git_to_muse.get(branch_head_git, last_commit_id)
            except Exception:
                branch_head_muse = last_commit_id

            if branch_head_muse:
                await db.execute(
                    text("""
                        INSERT INTO musehub_branches
                          (branch_id, repo_id, name, head_commit_id)
                        VALUES (:bid, :rid, :name, :hcid)
                        ON CONFLICT (branch_id) DO UPDATE
                          SET head_commit_id = EXCLUDED.head_commit_id
                    """),
                    {
                        "bid": _uid(f"branch-git-{repo_id}-{bname}"),
                        "rid": repo_id,
                        "name": bname,
                        "hcid": branch_head_muse,
                    },
                )

        print(
            f"      ✅ {commits_count} commits, {objects_count} objects "
            f"({len(branch_names)} branch{'es' if len(branch_names) != 1 else ''})"
        )
        return commits_count, objects_count


# ---------------------------------------------------------------------------
# Disk storage helpers
# ---------------------------------------------------------------------------

def _objects_dir() -> Path:
    d = Path(getattr(settings, "musehub_objects_dir", "/data/objects"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_midi_object(midi_bytes: bytes, repo_id: str, fname: str) -> tuple[str, Path]:
    """Write MIDI bytes to disk. Returns (object_id, disk_path)."""
    obj_id = "sha256:" + hashlib.sha256(midi_bytes).hexdigest()
    dest = _objects_dir() / f"{obj_id.replace(':', '_')}.mid"
    if not dest.exists():
        dest.write_bytes(midi_bytes)
    return obj_id, dest


def _write_code_object(content: str, repo_id: str, fname: str) -> tuple[str, Path]:
    """Write source code text to disk. Returns (object_id, disk_path)."""
    content_bytes = content.encode("utf-8")
    obj_id = "sha256:" + hashlib.sha256(content_bytes).hexdigest()
    ext = Path(fname).suffix or ".txt"
    dest = _objects_dir() / f"{obj_id.replace(':', '_')}{ext}"
    if not dest.exists():
        dest.write_bytes(content_bytes)
    return obj_id, dest


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

async def _table_exists(db: AsyncSession, table: str) -> bool:
    """Return True if the given table exists in the public schema."""
    result = await db.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    )
    return result.fetchone() is not None


async def _safe_delete(db: AsyncSession, table: str, where_sql: str, params: dict) -> None:
    """Delete rows only if the table exists — silently skips if it does not."""
    if await _table_exists(db, table):
        await db.execute(text(f"DELETE FROM {table} WHERE {where_sql}"), params)


async def seed(db: AsyncSession) -> None:
    print("\n🌱 MuseHub V2 seed — domain-agnostic multi-dimensional showcase")
    print("=" * 60)

    # ── 0. Pre-flight: verify the V2 migration has been applied ───────────
    if not await _table_exists(db, "musehub_domains"):
        print()
        print("  ❌ ERROR: musehub_domains table does not exist.")
        print("     Run the V2 Alembic migration first:")
        print()
        print("       docker compose exec musehub alembic upgrade head")
        print()
        print("     Then re-run this script.")
        print()
        raise SystemExit(1)

    # ── 1. Wipe V2 data if --force ────────────────────────────────────────
    if FORCE:
        print("  ⚠️  --force: wiping V2 rows…")
        for repo_id in ([r["repo_id"] for r in MIDI_REPOS] +
                        [r["repo_id"] for r in CODE_REPOS]):
            await _safe_delete(db, "musehub_repos", "repo_id = :rid", {"rid": repo_id})
        # Delete by stable author/slug rather than potentially-mismatched IDs
        await _safe_delete(
            db, "musehub_domain_installs",
            "domain_id IN (SELECT domain_id FROM musehub_domains "
            "WHERE author_slug='cgcardona' AND slug IN ('midi','code'))",
            {},
        )
        await _safe_delete(
            db, "musehub_domains",
            "author_slug='cgcardona' AND slug IN ('midi','code')",
            {},
        )
        await db.flush()
        print("  ✅ V2 rows cleared")

    # ── 2. Domain registry ────────────────────────────────────────────────
    print("\n  📦 Domain registry…")
    _midi_caps_json = json.dumps(_MIDI_CAPS, sort_keys=True)
    _code_caps_json = json.dumps(_CODE_CAPS, sort_keys=True)
    midi_hash = hashlib.sha256(_midi_caps_json.encode()).hexdigest()
    code_hash = hashlib.sha256(_code_caps_json.encode()).hexdigest()

    for stable_id, author_slug, slug, display, desc, caps, hash_, viewer, install_count in [
        (DOMAIN_MIDI, "cgcardona", "midi", "MIDI",
         "21-dimensional MIDI state versioning. Tracks harmonic, rhythmic, melodic, structural, "
         "dynamic, timbral, spatial, textural, pedal, microtonal, and 11 more dimensions. "
         "Piano roll viewer. OT merge semantics. Supports piano, orchestra, electronic, and any MIDI instrument.",
         _MIDI_CAPS, midi_hash, "piano_roll", len(MIDI_REPOS)),
        (DOMAIN_CODE, "cgcardona", "code", "Code",
         "10-language symbol-graph code versioning. Tracks syntax, semantics, types, tests, docs, "
         "complexity, dependencies, security, performance, and style dimensions. "
         "Symbol graph viewer. Three-way merge. Python, TypeScript, Rust, Go, and more.",
         _CODE_CAPS, code_hash, "symbol_graph", len(CODE_REPOS)),
    ]:
        # Try inserting with the stable ID; if the migration already seeded a row
        # with a different ID, the ON CONFLICT on (author_slug, slug) will update
        # the metadata but keep whatever ID is already there.
        await db.execute(
            text("""
                INSERT INTO musehub_domains
                  (domain_id, author_slug, slug, display_name, description, version,
                   manifest_hash, capabilities, viewer_type, install_count, is_verified, created_at, updated_at)
                VALUES
                  (:did, :author, :slug, :name, :desc, '2.0.0',
                   :hash, CAST(:caps AS jsonb), :viewer, :installs, true, now(), now())
                ON CONFLICT (author_slug, slug) DO UPDATE
                  SET manifest_hash = EXCLUDED.manifest_hash,
                      capabilities  = EXCLUDED.capabilities,
                      install_count = EXCLUDED.install_count,
                      version       = EXCLUDED.version,
                      updated_at    = now()
            """),
            {
                "did": stable_id, "author": author_slug, "slug": slug,
                "name": display, "desc": desc, "hash": hash_,
                "caps": json.dumps(caps), "viewer": viewer, "installs": install_count,
            },
        )
    await db.flush()

    # Resolve the actual domain_ids from the DB — the migration may have seeded
    # with different UUIDs; we join by (author_slug, slug) which is the stable key.
    row_midi = (await db.execute(
        text("SELECT domain_id FROM musehub_domains WHERE author_slug='cgcardona' AND slug='midi'")
    )).fetchone()
    row_code = (await db.execute(
        text("SELECT domain_id FROM musehub_domains WHERE author_slug='cgcardona' AND slug='code'")
    )).fetchone()

    if not row_midi or not row_code:
        raise RuntimeError("Domain registry insert failed — rows not found after upsert.")

    actual_midi_id = row_midi[0]
    actual_code_id = row_code[0]

    print(f"  ✅ @cgcardona/midi  → {actual_midi_id}")
    print(f"  ✅ @cgcardona/code  → {actual_code_id}")

    # ── 3. MIDI showcase repos ────────────────────────────────────────────
    print("\n  🎹 MIDI showcase repos…")
    midi_repo_count = 0
    midi_object_count = 0
    midi_commit_count = 0

    for r in MIDI_REPOS:
        repo_id = r["repo_id"]

        # Check idempotency
        existing = await db.execute(
            text("SELECT 1 FROM musehub_repos WHERE repo_id = :rid"), {"rid": repo_id}
        )
        if existing.fetchone() and not FORCE:
            print(f"    ⏭  {r['owner']}/{r['slug']} exists — skipping")
            continue

        # Insert repo
        await db.execute(
            text("""
                INSERT INTO musehub_repos
                  (repo_id, owner, owner_user_id, slug, name, description, visibility,
                   tags, domain_id, domain_meta, created_at)
                VALUES
                  (:rid, :owner, :uid, :slug, :name, :desc, :vis,
                   CAST(:tags AS json), :did, CAST(:dmeta AS json), :created)
                ON CONFLICT (repo_id) DO NOTHING
            """),
            {
                "rid": repo_id, "owner": r["owner"], "uid": r["owner_user_id"],
                "slug": r["slug"], "name": r["name"], "desc": r["description"],
                "vis": r["visibility"],
                "did": actual_midi_id, "dmeta": json.dumps(r["domain_meta"]),
                "tags": json.dumps(r["tags"]),
                "created": _now(days=r["days_ago"]),
            },
        )
        midi_repo_count += 1

        # Generate and write MIDI files
        for fname, gen_key in r["midi_files"]:
            try:
                midi_bytes = MIDI_GENERATORS[gen_key]()
            except Exception as exc:
                print(f"    ⚠️  MIDI generation failed for {gen_key}: {exc}")
                midi_bytes = b""

            if midi_bytes:
                obj_id, disk_path = _write_midi_object(midi_bytes, repo_id, fname)
                await db.execute(
                    text("""
                        INSERT INTO musehub_objects (object_id, repo_id, path, size_bytes, disk_path, created_at)
                        VALUES (:oid, :rid, :path, :size, :dpath, now())
                        ON CONFLICT (object_id) DO NOTHING
                    """),
                    {
                        "oid": obj_id, "rid": repo_id,
                        "path": f"tracks/{fname}",
                        "size": len(midi_bytes),
                        "dpath": str(disk_path),
                    },
                )
                midi_object_count += 1

        # Commits
        commit_templates = _MIDI_COMMITS.get(repo_id, [])
        prev_commit: str | None = None
        for i, (msg, author) in enumerate(commit_templates):
            cid = _sha(f"v2-midi-commit-{repo_id}-{i}")
            days = max(0, r["days_ago"] - i * 3)
            await db.execute(
                text("""
                    INSERT INTO musehub_commits
                      (commit_id, repo_id, branch, parent_ids, message, author, timestamp, snapshot_id)
                    VALUES (:cid, :rid, 'main', :parents, :msg, :author, :ts, :snap)
                    ON CONFLICT (commit_id) DO NOTHING
                """),
                {
                    "cid": cid, "rid": repo_id,
                    "parents": json.dumps([prev_commit] if prev_commit else []),
                    "msg": msg, "author": author,
                    "ts": _now(days=days),
                    "snap": _sha(f"snap-v2-{repo_id}-{i}"),
                },
            )
            prev_commit = cid
            midi_commit_count += 1

        # Main branch
        if prev_commit:
            await db.execute(
                text("""
                    INSERT INTO musehub_branches (branch_id, repo_id, name, head_commit_id)
                    VALUES (:bid, :rid, 'main', :hcid)
                    ON CONFLICT (branch_id) DO UPDATE SET head_commit_id = EXCLUDED.head_commit_id
                """),
                {"bid": _uid(f"branch-v2-{repo_id}-main"), "rid": repo_id, "hcid": prev_commit},
            )

        # Stars from community
        for j, uname in enumerate(ALL_CONTRIBUTORS[:min(r["star_count"] % 8 + 3, 8)]):
            uid = f"user-{uname.lower()}-00" + str(j + 1).zfill(4)[-2:]
            await db.execute(
                text("INSERT INTO musehub_stars (star_id, repo_id, user_id, created_at) VALUES (:sid, :rid, :uid, now()) ON CONFLICT (star_id) DO NOTHING"),
                {"sid": _uid(f"star-v2-{repo_id}-{uname}"), "rid": repo_id, "uid": uid},
            )

        print(f"    ✅ {r['owner']}/{r['slug']}")

    await db.flush()
    print(f"\n  ✅ MIDI: {midi_repo_count} repos, {midi_object_count} .mid files, {midi_commit_count} commits")

    # ── 4. Code domain repos — imported from real GitHub repos ───────────
    print("\n  💻 Code domain repos (cloning from GitHub…)")
    code_repo_count = 0
    code_object_count = 0
    code_commit_count = 0

    for r in CODE_REPOS:
        repo_id = r["repo_id"]
        print(f"\n    ▶  {r['owner']}/{r['slug']}", flush=True)

        existing = await db.execute(
            text("SELECT 1 FROM musehub_repos WHERE repo_id = :rid"), {"rid": repo_id}
        )
        if existing.fetchone() and not FORCE:
            print(f"    ⏭  exists — skipping")
            continue

        # Create the repo row
        await db.execute(
            text("""
                INSERT INTO musehub_repos
                  (repo_id, owner, owner_user_id, slug, name, description, visibility,
                   tags, domain_id, domain_meta, created_at)
                VALUES
                  (:rid, :owner, :uid, :slug, :name, :desc, :vis,
                   CAST(:tags AS json), :did, CAST(:dmeta AS json), :created)
                ON CONFLICT (repo_id) DO NOTHING
            """),
            {
                "rid": repo_id, "owner": r["owner"], "uid": r["owner_user_id"],
                "slug": r["slug"], "name": r["name"], "desc": r["description"],
                "vis": r["visibility"],
                "did": actual_code_id, "dmeta": json.dumps(r["domain_meta"]),
                "tags": json.dumps(r["tags"]),
                "created": _now(days=r["days_ago"]),
            },
        )
        code_repo_count += 1

        # Clone the real GitHub repo and import its full git history
        n_commits, n_objects = await _import_github_repo(db, r, actual_code_id)
        code_commit_count += n_commits
        code_object_count += n_objects

        # Stars
        for j, uname in enumerate(ALL_CONTRIBUTORS[:min(r["star_count"] % 8 + 2, 8)]):
            uid_num = str(j + 1).zfill(3)
            await db.execute(
                text("INSERT INTO musehub_stars (star_id, repo_id, user_id, created_at) VALUES (:sid, :rid, :uid, now()) ON CONFLICT (star_id) DO NOTHING"),
                {"sid": _uid(f"star-v2-code-{repo_id}-{uname}"), "rid": repo_id,
                 "uid": _uid(f"user-{uname}-{uid_num}")},
            )

    await db.flush()
    print(f"\n  ✅ Code: {code_repo_count} repos, {code_object_count} source files, {code_commit_count} commits")

    # ── 5. Issues for all V2 repos ────────────────────────────────────────
    print("\n  🐛 Issues…")
    issue_count = 0
    all_v2_repos = MIDI_REPOS + CODE_REPOS

    for r in all_v2_repos:
        repo_id = r["repo_id"]
        issue_list = _ISSUES.get(repo_id, [])
        for i, iss in enumerate(issue_list):
            issue_id = _uid(f"issue-v2-{repo_id}-{i}")
            await db.execute(
                text("""
                    INSERT INTO musehub_issues
                      (issue_id, repo_id, number, title, body, state, author, created_at, updated_at)
                    VALUES (:iid, :rid, :num, :title, :body, :state, :author, :ts, :ts)
                    ON CONFLICT (issue_id) DO NOTHING
                """),
                {
                    "iid": issue_id, "rid": repo_id,
                    "num": i + 1, "title": iss["title"],
                    "body": iss["body"], "state": iss["state"],
                    "author": r["owner"],
                    "ts": _now(days=r["days_ago"] - i * 5),
                },
            )
            issue_count += 1

    await db.flush()
    print(f"  ✅ Issues: {issue_count}")

    # ── 6. Pull requests ──────────────────────────────────────────────────
    print("\n  🔀 Pull requests…")
    pr_count = 0

    _PR_TEMPLATES: list[dict[str, str]] = [
        {"title": "feat: add extended 32-bar variation", "body": "Extends the main loop with a contrasting B-section.", "state": "open"},
        {"title": "fix: velocity humanization — beat 1 accent corrected", "body": "Beat 1 was not receiving the +12 velocity boost.", "state": "merged"},
        {"title": "feat: orchestral arrangement variant", "body": "Full orchestra version derived from the solo piano base.", "state": "merged"},
        {"title": "refactor: split into individual track objects", "body": "Separates each instrument into its own .mid file for DAW import.", "state": "open"},
    ]
    for r in all_v2_repos:
        for i, pr_tmpl in enumerate(_PR_TEMPLATES[:3]):
            pr_id = _uid(f"pr-v2-{r['repo_id']}-{i}")
            author = ALL_CONTRIBUTORS[(i + hash(r["repo_id"])) % len(ALL_CONTRIBUTORS)]
            ts = _now(days=r["days_ago"] - i * 7 - 3)
            is_merged = pr_tmpl["state"] == "merged"
            await db.execute(
                text("""
                    INSERT INTO musehub_pull_requests
                      (pr_id, repo_id, title, body, state, author,
                       from_branch, to_branch, created_at, merged_at)
                    VALUES (:pid, :rid, :title, :body, :state, :author,
                            :head, 'main', :ts, :merged_at)
                    ON CONFLICT (pr_id) DO NOTHING
                """),
                {
                    "pid": pr_id, "rid": r["repo_id"],
                    "title": pr_tmpl["title"],
                    "body": pr_tmpl["body"], "state": pr_tmpl["state"],
                    "author": author,
                    "head": f"feat/v2-extension-{i}",
                    "ts": ts,
                    "merged_at": ts if is_merged else None,
                },
            )
            pr_count += 1

    await db.flush()
    print(f"  ✅ Pull requests: {pr_count}")

    # ── 7. Releases ───────────────────────────────────────────────────────
    print("\n  🏷  Releases…")
    rel_count = 0
    for r in all_v2_repos:
        for v_major, v_minor, days_offset in [(1, 0, 10), (1, 1, 5), (2, 0, 1)]:
            rel_id = _uid(f"release-v2-{r['repo_id']}-{v_major}-{v_minor}")
            tag = f"v{v_major}.{v_minor}"
            await db.execute(
                text("""
                    INSERT INTO musehub_releases
                      (release_id, repo_id, tag, title, body, author,
                       is_prerelease, is_draft, created_at)
                    VALUES (:rid, :repo, :tag, :title, :body, :author,
                            false, false, :ts)
                    ON CONFLICT (release_id) DO NOTHING
                """),
                {
                    "rid": rel_id, "repo": r["repo_id"],
                    "tag": tag, "title": f"{r['name']} {tag}",
                    "body": f"Release {tag} — see commit log for changes.",
                    "author": r["owner"],
                    "ts": _now(days=days_offset),
                },
            )
            rel_count += 1

    await db.flush()
    print(f"  ✅ Releases: {rel_count}")

    # ── 8. Muse VCS layer (muse_objects + muse_snapshots + muse_commits) ──
    print("\n  🔗 Muse VCS layer…")
    vcs_commit_count = 0

    for r in all_v2_repos:
        repo_id = r["repo_id"]
        commits = _MIDI_COMMITS.get(repo_id) or []
        prev_muse_id: str | None = None

        for i, (msg, author) in enumerate(commits):
            snap_seed = f"muse-snap-v2-{repo_id}-{i}"
            snap_id = _sha(snap_seed)
            committed_at = _now(days=max(0, r["days_ago"] - i * 2))

            # Snapshot manifest — minimal for VCS graph
            manifest = {f"state/{i:04d}.dat": _sha(f"obj-v2-{repo_id}-{i}")}
            await db.execute(
                text("""
                    INSERT INTO muse_snapshots (snapshot_id, manifest, created_at)
                    VALUES (:sid, :manifest, :ca)
                    ON CONFLICT (snapshot_id) DO NOTHING
                """),
                {"sid": snap_id, "manifest": json.dumps(manifest), "ca": committed_at},
            )

            parent2: str | None = None
            if i >= 7 and i % 7 == 0 and prev_muse_id:
                # Merge commit — grab commit 6 back
                parent2 = _sha(f"muse-c-v2-{_sha(f'muse-snap-v2-{repo_id}-{max(0, i-6)}')}")

            commit_id = _sha(f"muse-c-v2-{snap_id}-{prev_muse_id or ''}-{msg}")
            await db.execute(
                text("""
                    INSERT INTO muse_commits
                      (commit_id, repo_id, branch, parent_commit_id, parent2_commit_id,
                       snapshot_id, message, author, committed_at, created_at, metadata)
                    VALUES
                      (:cid, :rid, 'main', :pid, :p2id,
                       :sid, :msg, :author, :cat, :cat, :meta)
                    ON CONFLICT (commit_id) DO NOTHING
                """),
                {
                    "cid": commit_id, "rid": repo_id, "pid": prev_muse_id, "p2id": parent2,
                    "sid": snap_id, "msg": msg, "author": author, "cat": committed_at,
                    "meta": json.dumps(r.get("domain_meta", {})),
                },
            )
            prev_muse_id = commit_id
            vcs_commit_count += 1

    await db.flush()
    print(f"  ✅ Muse commits: {vcs_commit_count}")

    # ── 9. Domain installs ────────────────────────────────────────────────
    print("\n  📥 Domain installs…")
    install_count = 0
    user_ids = {
        "gabriel": GABRIEL, "sofia": SOFIA, "marcus": MARCUS, "yuki": YUKI,
        "aaliya": AALIYA, "chen": CHEN, "fatou": FATOU, "pierre": PIERRE,
    }
    for r in MIDI_REPOS:
        uid = user_ids.get(r["owner"])
        if uid:
            await db.execute(
                text("""
                    INSERT INTO musehub_domain_installs (install_id, user_id, domain_id, created_at)
                    VALUES (:iid, :uid, :did, now())
                    ON CONFLICT (install_id) DO NOTHING
                """),
                {"iid": _uid(f"install-v2-midi-{uid}"), "uid": uid, "did": actual_midi_id},
            )
            install_count += 1
    for r in CODE_REPOS:
        uid = user_ids.get(r["owner"])
        if uid:
            await db.execute(
                text("""
                    INSERT INTO musehub_domain_installs (install_id, user_id, domain_id, created_at)
                    VALUES (:iid, :uid, :did, now())
                    ON CONFLICT (install_id) DO NOTHING
                """),
                {"iid": _uid(f"install-v2-code-{uid}"), "uid": uid, "did": actual_code_id},
            )
            install_count += 1

    await db.flush()
    print(f"  ✅ Domain installs: {install_count}")

    print("\n" + "=" * 60)
    print("🎉 MuseHub V2 seed complete!")
    print(f"   Domains:       2 (@cgcardona/midi, @cgcardona/code)")
    print(f"   MIDI repos:    {midi_repo_count} (with playable .mid files)")
    print(f"   Code repos:    {code_repo_count} (with real source files)")
    print(f"   VCS commits:   {vcs_commit_count}")
    print(f"   Issues/PRs:    {issue_count}/{pr_count}")
    print(f"   Releases:      {rel_count}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

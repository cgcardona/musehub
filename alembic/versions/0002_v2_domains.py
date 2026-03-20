"""MuseHub V2 — Domain-agnostic paradigm shift.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-18

Adds the Muse domain plugin registry and makes all existing tables
domain-agnostic.

Changes:
  NEW TABLES
  - musehub_domains: Muse domain plugin registry (@author/slug namespace)
  - musehub_domain_installs: User ↔ domain adoption tracking

  MUSEHUB_REPOS
  - ADD domain_id (nullable FK → musehub_domains)
  - ADD domain_meta JSON (replaces key_signature + tempo_bpm)
  - DROP key_signature
  - DROP tempo_bpm

  MUSEHUB_PR_COMMENTS
  - ADD dimension_ref JSON (domain-agnostic replacement for music-specific fields)
  - DROP target_type
  - DROP target_track
  - DROP target_beat_start
  - DROP target_beat_end
  - DROP target_note_pitch

  MUSEHUB_ISSUE_COMMENTS
  - RENAME musical_refs → state_refs

  MUSEHUB_RENDER_JOBS
  - RENAME midi_count → artifact_count
  - RENAME mp3_object_ids → audio_object_ids
  - RENAME image_object_ids → preview_object_ids

  SEED DATA
  - Insert @cgcardona/midi built-in domain (21-dimensional MIDI)
  - Insert @cgcardona/code built-in domain (symbol-graph code)
"""
from __future__ import annotations

import json
import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _manifest_hash(capabilities: dict) -> str:
    """Compute SHA-256 of the capabilities JSON (sorted keys)."""
    blob = json.dumps(capabilities, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# Capability manifests for the two built-in domains
_MIDI_CAPABILITIES = {
    "dimensions": [
        {"name": "harmony", "description": "Chord progressions and tonal centre analysis"},
        {"name": "rhythm", "description": "Rhythmic density, groove, and syncopation"},
        {"name": "melody", "description": "Melodic contour, range, and motif detection"},
        {"name": "dynamics", "description": "Velocity curves and dynamic range"},
        {"name": "structure", "description": "Section form and macro structure"},
        {"name": "tempo", "description": "BPM and tempo map evolution"},
        {"name": "key", "description": "Key signature detection and modulation"},
        {"name": "meter", "description": "Time signature and metric complexity"},
        {"name": "groove", "description": "Swing, feel, and micro-timing"},
        {"name": "emotion", "description": "8-axis valence/arousal emotion map"},
        {"name": "motifs", "description": "Recurring melodic and rhythmic motifs"},
        {"name": "form", "description": "Formal structure (AABA, verse/chorus, etc.)"},
        {"name": "pitch_bend", "description": "Pitch bend envelope per channel"},
        {"name": "aftertouch", "description": "Polyphonic aftertouch per note"},
        {"name": "modulation", "description": "CC1 modulation wheel data"},
        {"name": "volume", "description": "CC7 channel volume envelopes"},
        {"name": "pan", "description": "CC10 stereo panning"},
        {"name": "expression", "description": "CC11 expression controller"},
        {"name": "sustain", "description": "CC64 sustain pedal events"},
        {"name": "reverb", "description": "CC91 reverb send levels"},
        {"name": "chorus", "description": "CC93 chorus send levels"},
    ],
    "viewer_type": "piano_roll",
    "artifact_types": ["audio/midi", "audio/mpeg", "image/webp"],
    "merge_semantics": "ot",
    "supported_commands": [
        "muse analyze", "muse diff", "muse listen", "muse arrange",
        "muse piano-roll", "muse groove-check", "muse emotion-diff",
    ],
}

_CODE_CAPABILITIES = {
    "dimensions": [
        {"name": "symbols", "description": "Function and class symbol graph"},
        {"name": "hotspots", "description": "Most frequently changed symbols"},
        {"name": "coupling", "description": "Symbol-level coupling and cohesion"},
        {"name": "complexity", "description": "Cyclomatic complexity per symbol"},
        {"name": "churn", "description": "Commit frequency per file and symbol"},
        {"name": "coverage", "description": "Test coverage by symbol"},
        {"name": "dependencies", "description": "Import and dependency graph"},
        {"name": "duplicates", "description": "Semantically duplicated code blocks"},
        {"name": "refactors", "description": "Detected rename and move operations"},
        {"name": "types", "description": "Type annotation completeness"},
    ],
    "viewer_type": "symbol_graph",
    "artifact_types": [
        "text/x-python", "text/typescript", "text/javascript",
        "text/x-go", "text/x-rust", "text/x-java",
    ],
    "merge_semantics": "ot",
    "supported_commands": [
        "muse symbols", "muse hotspots", "muse coupling", "muse diff",
        "muse query", "muse refactor",
    ],
}


def upgrade() -> None:
    # ── musehub_domains ───────────────────────────────────────────────────────
    op.create_table(
        "musehub_domains",
        sa.Column("domain_id", sa.String(36), nullable=False),
        sa.Column("author_user_id", sa.String(36), nullable=True),
        sa.Column("author_slug", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("manifest_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("viewer_type", sa.String(64), nullable=False, server_default="generic"),
        sa.Column("install_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_deprecated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("domain_id"),
        sa.UniqueConstraint("author_slug", "slug", name="uq_musehub_domains_author_slug"),
    )
    op.create_index("ix_musehub_domains_author_slug", "musehub_domains", ["author_slug"])
    op.create_index("ix_musehub_domains_slug", "musehub_domains", ["slug"])
    op.create_index("ix_musehub_domains_author_user_id", "musehub_domains", ["author_user_id"])

    # ── musehub_domain_installs ───────────────────────────────────────────────
    op.create_table(
        "musehub_domain_installs",
        sa.Column("install_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("domain_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("install_id"),
        sa.UniqueConstraint("user_id", "domain_id", name="uq_musehub_domain_installs"),
    )
    op.create_index("ix_musehub_domain_installs_user_id", "musehub_domain_installs", ["user_id"])
    op.create_index("ix_musehub_domain_installs_domain_id", "musehub_domain_installs", ["domain_id"])

    # ── musehub_repos: add domain_id + domain_meta, drop key_signature + tempo_bpm ──
    op.add_column("musehub_repos",
        sa.Column("domain_id", sa.String(36), nullable=True))
    op.add_column("musehub_repos",
        sa.Column("domain_meta", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_musehub_repos_domain_id", "musehub_repos", ["domain_id"])
    op.drop_column("musehub_repos", "key_signature")
    op.drop_column("musehub_repos", "tempo_bpm")

    # ── musehub_pr_comments: add dimension_ref, drop music-specific fields ───
    op.add_column("musehub_pr_comments",
        sa.Column("dimension_ref", sa.JSON(), nullable=False, server_default="{}"))
    op.drop_column("musehub_pr_comments", "target_type")
    op.drop_column("musehub_pr_comments", "target_track")
    op.drop_column("musehub_pr_comments", "target_beat_start")
    op.drop_column("musehub_pr_comments", "target_beat_end")
    op.drop_column("musehub_pr_comments", "target_note_pitch")

    # ── musehub_issue_comments: rename musical_refs → state_refs ─────────────
    op.add_column("musehub_issue_comments",
        sa.Column("state_refs", sa.JSON(), nullable=False, server_default="[]"))
    # Copy existing data to new column
    op.execute(
        "UPDATE musehub_issue_comments SET state_refs = musical_refs"
    )
    op.drop_column("musehub_issue_comments", "musical_refs")

    # ── musehub_render_jobs: rename domain-specific column names ──────────────
    op.add_column("musehub_render_jobs",
        sa.Column("artifact_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("musehub_render_jobs",
        sa.Column("audio_object_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("musehub_render_jobs",
        sa.Column("preview_object_ids", sa.JSON(), nullable=False, server_default="[]"))
    # Copy existing data
    op.execute("UPDATE musehub_render_jobs SET artifact_count = midi_count")
    op.execute("UPDATE musehub_render_jobs SET audio_object_ids = mp3_object_ids")
    op.execute("UPDATE musehub_render_jobs SET preview_object_ids = image_object_ids")
    op.drop_column("musehub_render_jobs", "midi_count")
    op.drop_column("musehub_render_jobs", "mp3_object_ids")
    op.drop_column("musehub_render_jobs", "image_object_ids")

    # ── Seed built-in domains ─────────────────────────────────────────────────
    # Use stable IDs so seed_v2.py and other tooling can reference them by
    # known values without querying the DB.  These are NOT real UUIDs but are
    # valid VARCHAR(36) strings that match the DOMAIN_MIDI / DOMAIN_CODE
    # constants in scripts/seed_v2.py.
    _DOMAIN_MIDI_ID = "domain-midi-cgcardona-0001"
    _DOMAIN_CODE_ID = "domain-code-cgcardona-0001"

    midi_caps_json = json.dumps(_MIDI_CAPABILITIES)
    code_caps_json = json.dumps(_CODE_CAPABILITIES)

    op.execute(
        sa.text(
            "INSERT INTO musehub_domains "
            "(domain_id, author_user_id, author_slug, slug, display_name, description, "
            "version, manifest_hash, capabilities, viewer_type, install_count, "
            "is_verified, is_deprecated, created_at, updated_at) "
            "VALUES (:did, NULL, 'cgcardona', 'midi', 'MIDI', "
            "'21-dimensional MIDI state space — notes, pitch bend, 11 CC controllers, "
            "tempo map, time signatures, key signatures, and more. The reference "
            "implementation of the MuseDomainPlugin protocol.', "
            f"'1.0.0', :mhash, CAST('{midi_caps_json.replace(chr(39), chr(39)+chr(39))}' AS json), "
            "'piano_roll', 0, true, false, now(), now()) "
            "ON CONFLICT (author_slug, slug) DO NOTHING"
        ).bindparams(
            did=_DOMAIN_MIDI_ID,
            mhash=_manifest_hash(_MIDI_CAPABILITIES),
        )
    )

    op.execute(
        sa.text(
            "INSERT INTO musehub_domains "
            "(domain_id, author_user_id, author_slug, slug, display_name, description, "
            "version, manifest_hash, capabilities, viewer_type, install_count, "
            "is_verified, is_deprecated, created_at, updated_at) "
            "VALUES (:did, NULL, 'cgcardona', 'code', 'Code', "
            "'Symbol-graph code state space — diff and merge at the level of named "
            "functions, classes, and modules across Python, TypeScript, Go, Rust, "
            "Java, C, C++, C#, Ruby, and Kotlin.', "
            f"'1.0.0', :chash, CAST('{code_caps_json.replace(chr(39), chr(39)+chr(39))}' AS json), "
            "'symbol_graph', 0, true, false, now(), now()) "
            "ON CONFLICT (author_slug, slug) DO NOTHING"
        ).bindparams(
            did=_DOMAIN_CODE_ID,
            chash=_manifest_hash(_CODE_CAPABILITIES),
        )
    )


def downgrade() -> None:
    # Restore musehub_render_jobs original columns
    op.add_column("musehub_render_jobs",
        sa.Column("midi_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("musehub_render_jobs",
        sa.Column("mp3_object_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("musehub_render_jobs",
        sa.Column("image_object_ids", sa.JSON(), nullable=False, server_default="[]"))
    op.execute("UPDATE musehub_render_jobs SET midi_count = artifact_count")
    op.execute("UPDATE musehub_render_jobs SET mp3_object_ids = audio_object_ids")
    op.execute("UPDATE musehub_render_jobs SET image_object_ids = preview_object_ids")
    op.drop_column("musehub_render_jobs", "artifact_count")
    op.drop_column("musehub_render_jobs", "audio_object_ids")
    op.drop_column("musehub_render_jobs", "preview_object_ids")

    # Restore musehub_issue_comments
    op.add_column("musehub_issue_comments",
        sa.Column("musical_refs", sa.JSON(), nullable=False, server_default="[]"))
    op.execute("UPDATE musehub_issue_comments SET musical_refs = state_refs")
    op.drop_column("musehub_issue_comments", "state_refs")

    # Restore musehub_pr_comments
    op.add_column("musehub_pr_comments",
        sa.Column("target_type", sa.String(20), nullable=False, server_default="general"))
    op.add_column("musehub_pr_comments",
        sa.Column("target_track", sa.String(255), nullable=True))
    op.add_column("musehub_pr_comments",
        sa.Column("target_beat_start", sa.Float(), nullable=True))
    op.add_column("musehub_pr_comments",
        sa.Column("target_beat_end", sa.Float(), nullable=True))
    op.add_column("musehub_pr_comments",
        sa.Column("target_note_pitch", sa.Integer(), nullable=True))
    op.drop_column("musehub_pr_comments", "dimension_ref")

    # Restore musehub_repos
    op.drop_index("ix_musehub_repos_domain_id", table_name="musehub_repos")
    op.drop_column("musehub_repos", "domain_id")
    op.drop_column("musehub_repos", "domain_meta")
    op.add_column("musehub_repos",
        sa.Column("key_signature", sa.String(50), nullable=True))
    op.add_column("musehub_repos",
        sa.Column("tempo_bpm", sa.Integer(), nullable=True))

    # Drop new tables
    op.drop_index("ix_musehub_domain_installs_domain_id", table_name="musehub_domain_installs")
    op.drop_index("ix_musehub_domain_installs_user_id", table_name="musehub_domain_installs")
    op.drop_table("musehub_domain_installs")

    op.drop_index("ix_musehub_domains_author_user_id", table_name="musehub_domains")
    op.drop_index("ix_musehub_domains_slug", table_name="musehub_domains")
    op.drop_index("ix_musehub_domains_author_slug", table_name="musehub_domains")
    op.drop_table("musehub_domains")

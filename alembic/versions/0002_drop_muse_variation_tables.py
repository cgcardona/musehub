"""Drop Muse variation tables (muse_variations, muse_phrases, muse_note_changes).

Muse VCS was extracted to cgcardona/muse. These three tables tracked
DAW-level note editing history and are no longer needed in Muse VCS.

Note: muse_commits, muse_snapshots, muse_objects, and muse_tags are
intentionally NOT dropped here — MuseHub reads those tables to display
repository commit history. They will be dropped when MuseHub is extracted.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop child tables first (FK constraints)
    op.drop_index("ix_muse_note_changes_phrase_id", table_name="muse_note_changes")
    op.drop_table("muse_note_changes")

    op.drop_index("ix_muse_phrases_variation_id", table_name="muse_phrases")
    op.drop_table("muse_phrases")

    op.drop_index("ix_muse_variations_parent_variation_id", table_name="muse_variations")
    op.drop_index("ix_muse_variations_project_id", table_name="muse_variations")
    op.drop_table("muse_variations")


def downgrade() -> None:
    op.create_table(
        "muse_variations",
        sa.Column("variation_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("affected_tracks", sa.JSON(), nullable=True),
        sa.Column("affected_regions", sa.JSON(), nullable=True),
        sa.Column("beat_range_start", sa.Float(), nullable=True),
        sa.Column("beat_range_end", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("base_state_id", sa.String(64), nullable=True),
        sa.Column("commit_state_id", sa.String(64), nullable=True),
        sa.Column("is_head", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("parent_variation_id", sa.String(36), nullable=True),
        sa.Column("parent2_variation_id", sa.String(36), nullable=True),
        sa.Column("region_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_variation_id"], ["muse_variations.variation_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent2_variation_id"], ["muse_variations.variation_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("variation_id"),
    )
    op.create_index("ix_muse_variations_project_id", "muse_variations", ["project_id"])
    op.create_index(
        "ix_muse_variations_parent_variation_id", "muse_variations", ["parent_variation_id"]
    )

    op.create_table(
        "muse_phrases",
        sa.Column("phrase_id", sa.String(36), nullable=False),
        sa.Column("variation_id", sa.String(36), nullable=False),
        sa.Column("track_id", sa.String(36), nullable=True),
        sa.Column("region_id", sa.String(36), nullable=True),
        sa.Column("beat_start", sa.Float(), nullable=True),
        sa.Column("beat_end", sa.Float(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("diff_json", sa.JSON(), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("sequence_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["variation_id"], ["muse_variations.variation_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("phrase_id"),
    )
    op.create_index("ix_muse_phrases_variation_id", "muse_phrases", ["variation_id"])

    op.create_table(
        "muse_note_changes",
        sa.Column("change_id", sa.String(36), nullable=False),
        sa.Column("phrase_id", sa.String(36), nullable=False),
        sa.Column("note_id", sa.String(36), nullable=False),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["phrase_id"], ["muse_phrases.phrase_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("change_id"),
    )
    op.create_index("ix_muse_note_changes_phrase_id", "muse_note_changes", ["phrase_id"])

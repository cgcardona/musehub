"""Release system v2 — semver + channel + changelog + wire tags.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-21

Changes:
  MUSEHUB_RELEASES
  - DROP COLUMN is_prerelease (replaced by channel)
  - ADD COLUMN channel VARCHAR(20) NOT NULL DEFAULT 'stable'
  - ADD COLUMN semver_major INT NOT NULL DEFAULT 0
  - ADD COLUMN semver_minor INT NOT NULL DEFAULT 0
  - ADD COLUMN semver_patch INT NOT NULL DEFAULT 0
  - ADD COLUMN semver_pre VARCHAR(255) NOT NULL DEFAULT ''
  - ADD COLUMN semver_build VARCHAR(255) NOT NULL DEFAULT ''
  - ADD COLUMN snapshot_id VARCHAR(128) NULL
  - ADD COLUMN agent_id VARCHAR(255) NOT NULL DEFAULT ''
  - ADD COLUMN model_id VARCHAR(255) NOT NULL DEFAULT ''
  - ADD COLUMN changelog_json TEXT NOT NULL DEFAULT '[]'
  - Make title nullable (default '') — CLI may omit it

  NEW TABLE
  - musehub_wire_tags: lightweight semantic tags pushed via wire protocol
"""
import sqlalchemy as sa
from alembic import op


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── musehub_releases — drop is_prerelease, add rich semver/channel fields ──
    op.drop_column("musehub_releases", "is_prerelease")

    op.add_column(
        "musehub_releases",
        sa.Column("channel", sa.String(20), nullable=False, server_default="stable"),
    )
    op.create_index(
        "ix_musehub_releases_channel",
        "musehub_releases",
        ["channel"],
    )

    op.add_column(
        "musehub_releases",
        sa.Column("semver_major", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("semver_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("semver_patch", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("semver_pre", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("semver_build", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("snapshot_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("agent_id", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("model_id", sa.String(255), nullable=False, server_default=""),
    )
    op.add_column(
        "musehub_releases",
        sa.Column("changelog_json", sa.Text(), nullable=False, server_default="[]"),
    )

    # title was NOT NULL with no default — make it nullable so CLI omitting it works.
    op.alter_column("musehub_releases", "title", server_default="", nullable=False)

    # ── musehub_wire_tags — new table ─────────────────────────────────────────
    op.create_table(
        "musehub_wire_tags",
        sa.Column("tag_id", sa.String(36), primary_key=True),
        sa.Column(
            "repo_id",
            sa.String(36),
            sa.ForeignKey("musehub_repos.repo_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_id", sa.String(64), nullable=False),
        sa.Column("tag", sa.String(500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("repo_id", "tag", name="uq_musehub_wire_tags_repo_tag"),
    )
    op.create_index(
        "ix_musehub_wire_tags_repo_id",
        "musehub_wire_tags",
        ["repo_id"],
    )
    op.create_index(
        "ix_musehub_wire_tags_tag",
        "musehub_wire_tags",
        ["tag"],
    )


def downgrade() -> None:
    op.drop_table("musehub_wire_tags")

    op.drop_column("musehub_releases", "changelog_json")
    op.drop_column("musehub_releases", "model_id")
    op.drop_column("musehub_releases", "agent_id")
    op.drop_column("musehub_releases", "snapshot_id")
    op.drop_column("musehub_releases", "semver_build")
    op.drop_column("musehub_releases", "semver_pre")
    op.drop_column("musehub_releases", "semver_patch")
    op.drop_column("musehub_releases", "semver_minor")
    op.drop_column("musehub_releases", "semver_major")
    op.drop_index("ix_musehub_releases_channel", table_name="musehub_releases")
    op.drop_column("musehub_releases", "channel")

    op.add_column(
        "musehub_releases",
        sa.Column("is_prerelease", sa.Boolean(), nullable=False, server_default="false"),
    )

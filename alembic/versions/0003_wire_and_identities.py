"""Wire protocol support + unified identities table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-19

Changes:
  NEW TABLES
  - musehub_snapshots: Immutable file-tree manifests (path → object_id JSON)
  - musehub_identities: Unified identity table for humans, agents, and orgs

  MUSEHUB_COMMITS
  - ADD commit_meta JSON (stores rich Muse-native fields: sem_ver_bump,
    structured_delta, breaking_changes, agent_id, model_id, etc.)

  MUSEHUB_OBJECTS
  - ADD storage_uri (storage backend URI: "local://..." | "s3://...")

  MUSEHUB_REPOS
  - ADD default_branch VARCHAR(255) DEFAULT 'main'
  - ADD pushed_at TIMESTAMP WITH TIME ZONE (last push time for trending sort)
"""
import sqlalchemy as sa
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── musehub_snapshots ────────────────────────────────────────────────────
    op.create_table(
        "musehub_snapshots",
        sa.Column("snapshot_id", sa.String(128), primary_key=True),
        sa.Column(
            "repo_id",
            sa.String(36),
            sa.ForeignKey("musehub_repos.repo_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("manifest", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_musehub_snapshots_repo_id",
        "musehub_snapshots",
        ["repo_id"],
    )

    # ── musehub_identities ───────────────────────────────────────────────────
    op.create_table(
        "musehub_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("handle", sa.String(64), nullable=False),
        sa.Column("identity_type", sa.String(16), nullable=False, server_default="human"),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("avatar_url", sa.String(2048), nullable=True),
        sa.Column("website_url", sa.String(2048), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("agent_model", sa.String(255), nullable=True),
        sa.Column("agent_capabilities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("legacy_user_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_musehub_identities_handle", "musehub_identities", ["handle"])
    op.create_index("ix_musehub_identities_email", "musehub_identities", ["email"])
    op.create_index("ix_musehub_identities_legacy_user_id", "musehub_identities", ["legacy_user_id"])
    op.create_unique_constraint(
        "uq_musehub_identities_handle", "musehub_identities", ["handle"]
    )

    # ── musehub_commits — add commit_meta ────────────────────────────────────
    op.add_column(
        "musehub_commits",
        sa.Column("commit_meta", sa.JSON(), nullable=False, server_default="{}"),
    )

    # ── musehub_objects — add storage_uri ────────────────────────────────────
    op.add_column(
        "musehub_objects",
        sa.Column("storage_uri", sa.String(2048), nullable=True),
    )

    # ── musehub_repos — add default_branch + pushed_at ───────────────────────
    op.add_column(
        "musehub_repos",
        sa.Column(
            "default_branch",
            sa.String(255),
            nullable=False,
            server_default="main",
        ),
    )
    op.add_column(
        "musehub_repos",
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("musehub_repos", "pushed_at")
    op.drop_column("musehub_repos", "default_branch")
    op.drop_column("musehub_objects", "storage_uri")
    op.drop_column("musehub_commits", "commit_meta")
    op.drop_table("musehub_identities")
    op.drop_table("musehub_snapshots")

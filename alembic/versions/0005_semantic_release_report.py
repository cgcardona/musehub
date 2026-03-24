"""Add semantic_report_json column to musehub_releases.

Stores the SemanticReleaseReport JSON blob computed by the Muse CLI at
``muse release push`` time.  The column is nullable via an empty-string
default so existing rows are unaffected and the server accepts old CLI
clients that don't send the field.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "musehub_releases",
        sa.Column(
            "semantic_report_json",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("musehub_releases", "semantic_report_json")

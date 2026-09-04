"""Add revocable reader refresh sessions.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reader_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_reader_sessions_user_id", "reader_sessions", ["user_id"])
    op.create_index("ix_reader_sessions_expires_at", "reader_sessions", ["expires_at"])
    op.create_index(
        "ix_reader_sessions_refresh_token_hash",
        "reader_sessions",
        ["refresh_token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("reader_sessions")

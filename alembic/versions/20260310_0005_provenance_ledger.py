"""Add provenance_ledger table for Phase H direct provenance foundation."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260310_0005"
down_revision = "20260309_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provenance_ledger",
        sa.Column("provenance_id", sa.Text(), nullable=False),
        sa.Column("bound_object_id", sa.Text(), nullable=False),
        sa.Column("bound_object_type", sa.Text(), nullable=False),
        sa.Column("producer_kind", sa.Text(), nullable=False),
        sa.Column("producer_id", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.Text(), nullable=False),
        sa.Column("source_channel", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("retention_class", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("model_provider", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("ip_addr", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("machine_fingerprint", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.Text(), nullable=True),
        sa.Column("episode_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("provenance_id"),
        sa.UniqueConstraint("bound_object_id"),
    )


def downgrade() -> None:
    op.drop_table("provenance_ledger")

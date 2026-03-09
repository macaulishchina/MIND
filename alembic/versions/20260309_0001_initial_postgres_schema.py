"""Initial PostgreSQL schema for Phase D storage."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260309_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "object_versions",
        sa.Column("object_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_refs_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("object_id", "version"),
    )
    op.create_index("idx_object_versions_object_id", "object_versions", ["object_id"])
    op.create_index("idx_object_versions_type", "object_versions", ["type"])

    op.create_table(
        "primitive_call_logs",
        sa.Column("call_id", sa.Text(), nullable=False),
        sa.Column("primitive", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("target_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("call_id"),
    )
    op.create_index("idx_primitive_call_logs_timestamp", "primitive_call_logs", ["timestamp"])

    op.create_table(
        "budget_events",
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("call_id", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("primitive", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("cost_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_budget_events_call_id", "budget_events", ["call_id"])
    op.create_index("idx_budget_events_scope_id", "budget_events", ["scope_id"])


def downgrade() -> None:
    op.drop_index("idx_budget_events_scope_id", table_name="budget_events")
    op.drop_index("idx_budget_events_call_id", table_name="budget_events")
    op.drop_table("budget_events")

    op.drop_index("idx_primitive_call_logs_timestamp", table_name="primitive_call_logs")
    op.drop_table("primitive_call_logs")

    op.drop_index("idx_object_versions_type", table_name="object_versions")
    op.drop_index("idx_object_versions_object_id", table_name="object_versions")
    op.drop_table("object_versions")

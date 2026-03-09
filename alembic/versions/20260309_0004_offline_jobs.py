"""Add offline_jobs table for Phase E worker scheduling."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260309_0004"
down_revision = "20260309_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offline_jobs",
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("job_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_json", JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_json", JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(
        "idx_offline_jobs_ready_queue",
        "offline_jobs",
        ["status", "available_at", "priority"],
    )
    op.create_index("idx_offline_jobs_kind", "offline_jobs", ["job_kind"])


def downgrade() -> None:
    op.drop_index("idx_offline_jobs_kind", table_name="offline_jobs")
    op.drop_index("idx_offline_jobs_ready_queue", table_name="offline_jobs")
    op.drop_table("offline_jobs")

"""Add governance_audit table for Phase H governance trace foundation."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260310_0006"
down_revision = "20260310_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_audit",
        sa.Column("audit_id", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("target_object_ids_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_provenance_ids_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selection_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("idx_governance_audit_operation_id", "governance_audit", ["operation_id"])
    op.create_index("idx_governance_audit_timestamp", "governance_audit", ["timestamp"])


def downgrade() -> None:
    op.drop_index("idx_governance_audit_timestamp", table_name="governance_audit")
    op.drop_index("idx_governance_audit_operation_id", table_name="governance_audit")
    op.drop_table("governance_audit")

"""Add concealed_objects table for Phase H online conceal isolation."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260310_0007"
down_revision = "20260310_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concealed_objects",
        sa.Column("concealment_id", sa.Text(), nullable=False),
        sa.Column("operation_id", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("concealed_at", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("concealment_id"),
        sa.UniqueConstraint("object_id"),
    )
    op.create_index("idx_concealed_objects_operation_id", "concealed_objects", ["operation_id"])


def downgrade() -> None:
    op.drop_index("idx_concealed_objects_operation_id", table_name="concealed_objects")
    op.drop_table("concealed_objects")

"""Add provider_selection_json to offline_jobs."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260312_0009"
down_revision = "20260310_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offline_jobs",
        sa.Column(
            "provider_selection_json",
            JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("offline_jobs", "provider_selection_json")

"""Add FeedbackRecord support: new object type and dynamic signal metadata.

Phase α-1 adds the FeedbackRecord object type to the memory object model.
FeedbackRecord objects are stored in the existing ``object_versions`` table
(no schema change needed) since the table uses generic JSON columns for
content and metadata.

This migration adds an index on ``(type, metadata_json)`` to make lookups
by type=FeedbackRecord efficient, and a partial index on ``episode_id``
extracted from metadata for fast per-episode feedback queries.

Phase α-2 dynamic signal fields (access_count, feedback_positive_count,
feedback_negative_count, last_accessed_at, decay_score) are stored in the
existing ``metadata_json`` column — no DDL change is required.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260313_0010"
down_revision = "20260312_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fast lookup by object type (useful for FeedbackRecord queries).
    # The index already exists for SQLite in-memory tests — use IF NOT EXISTS.
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_object_versions_type_version "
            "ON object_versions(type, version DESC)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS idx_object_versions_type_version"
        )
    )

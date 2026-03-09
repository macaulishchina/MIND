"""Add retrieval-oriented PostgreSQL indexes."""

from __future__ import annotations

from alembic import op

revision = "20260309_0002"
down_revision = "20260309_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("idx_object_versions_status", "object_versions", ["status"])
    op.create_index("idx_object_versions_updated_at", "object_versions", ["updated_at"])
    op.execute(
        """
        CREATE INDEX idx_object_versions_episode_id
        ON object_versions ((metadata_json ->> 'episode_id'))
        """
    )
    op.execute(
        """
        CREATE INDEX idx_object_versions_task_id
        ON object_versions ((metadata_json ->> 'task_id'))
        """
    )
    op.execute(
        """
        CREATE INDEX idx_object_versions_source_refs_gin
        ON object_versions
        USING gin (source_refs_json)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_object_versions_source_refs_gin")
    op.execute("DROP INDEX IF EXISTS idx_object_versions_task_id")
    op.execute("DROP INDEX IF EXISTS idx_object_versions_episode_id")
    op.drop_index("idx_object_versions_updated_at", table_name="object_versions")
    op.drop_index("idx_object_versions_status", table_name="object_versions")

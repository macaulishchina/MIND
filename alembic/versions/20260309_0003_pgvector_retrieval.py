"""Add pg_trgm search text and pgvector object embeddings."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260309_0003"
down_revision = "20260309_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "object_versions",
        sa.Column("search_text", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE object_versions
        SET search_text = lower(
            object_id
            || ' '
            || replace(object_id, '-', ' ')
            || ' '
            || type
            || ' '
            || content_json::text
            || ' '
            || metadata_json::text
        )
        """
    )
    op.alter_column("object_versions", "search_text", nullable=False)
    op.execute(
        """
        CREATE INDEX idx_object_versions_search_text_trgm
        ON object_versions
        USING gin (search_text gin_trgm_ops)
        """
    )

    op.execute(
        """
        CREATE TABLE object_embeddings (
            object_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding VECTOR(64) NOT NULL,
            inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (object_id, version),
            FOREIGN KEY (object_id, version)
                REFERENCES object_versions (object_id, version)
                ON DELETE CASCADE
        )
        """
    )
    op.create_index("idx_object_embeddings_model", "object_embeddings", ["embedding_model"])


def downgrade() -> None:
    op.drop_index("idx_object_embeddings_model", table_name="object_embeddings")
    op.drop_table("object_embeddings")
    op.execute("DROP INDEX IF EXISTS idx_object_versions_search_text_trgm")
    op.drop_column("object_versions", "search_text")

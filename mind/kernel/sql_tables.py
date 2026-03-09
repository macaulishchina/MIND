"""Shared SQLAlchemy table metadata for the PostgreSQL backend."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

postgres_metadata = sa.MetaData()

object_versions_table = sa.Table(
    "object_versions",
    postgres_metadata,
    sa.Column("object_id", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("type", sa.Text(), nullable=False),
    sa.Column("content_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("source_refs_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("created_at", sa.Text(), nullable=False),
    sa.Column("updated_at", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("priority", sa.Float(), nullable=False),
    sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column(
        "inserted_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.PrimaryKeyConstraint("object_id", "version"),
)

sa.Index("idx_object_versions_object_id", object_versions_table.c.object_id)
sa.Index("idx_object_versions_type", object_versions_table.c.type)

primitive_call_logs_table = sa.Table(
    "primitive_call_logs",
    postgres_metadata,
    sa.Column("call_id", sa.Text(), primary_key=True),
    sa.Column("primitive", sa.Text(), nullable=False),
    sa.Column("actor", sa.Text(), nullable=False),
    sa.Column("timestamp", sa.Text(), nullable=False),
    sa.Column("target_ids_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("cost_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("outcome", sa.Text(), nullable=False),
    sa.Column("request_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("response_json", JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("error_json", JSONB(astext_type=sa.Text()), nullable=True),
)

sa.Index("idx_primitive_call_logs_timestamp", primitive_call_logs_table.c.timestamp)

budget_events_table = sa.Table(
    "budget_events",
    postgres_metadata,
    sa.Column("event_id", sa.Text(), primary_key=True),
    sa.Column("call_id", sa.Text(), nullable=False),
    sa.Column("scope_id", sa.Text(), nullable=False),
    sa.Column("primitive", sa.Text(), nullable=False),
    sa.Column("actor", sa.Text(), nullable=False),
    sa.Column("timestamp", sa.Text(), nullable=False),
    sa.Column("outcome", sa.Text(), nullable=False),
    sa.Column("cost_json", JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False),
)

sa.Index("idx_budget_events_call_id", budget_events_table.c.call_id)
sa.Index("idx_budget_events_scope_id", budget_events_table.c.scope_id)

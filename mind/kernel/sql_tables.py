"""Shared SQLAlchemy table metadata for the PostgreSQL backend."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from .pgvector import Vector
from .retrieval import EMBEDDING_DIM

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
    sa.Column("search_text", sa.Text(), nullable=False),
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
sa.Index("idx_object_versions_status", object_versions_table.c.status)
sa.Index("idx_object_versions_updated_at", object_versions_table.c.updated_at)
sa.Index(
    "idx_object_versions_search_text_trgm",
    object_versions_table.c.search_text,
    postgresql_using="gin",
    postgresql_ops={"search_text": "gin_trgm_ops"},
)
sa.Index(
    "idx_object_versions_episode_id",
    object_versions_table.c.metadata_json.op("->>")("episode_id"),
)
sa.Index(
    "idx_object_versions_task_id",
    object_versions_table.c.metadata_json.op("->>")("task_id"),
)
sa.Index(
    "idx_object_versions_source_refs_gin",
    object_versions_table.c.source_refs_json,
    postgresql_using="gin",
)

object_embeddings_table = sa.Table(
    "object_embeddings",
    postgres_metadata,
    sa.Column("object_id", sa.Text(), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("embedding_model", sa.Text(), nullable=False),
    sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
    sa.Column(
        "inserted_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.ForeignKeyConstraint(
        ["object_id", "version"],
        ["object_versions.object_id", "object_versions.version"],
        ondelete="CASCADE",
    ),
    sa.PrimaryKeyConstraint("object_id", "version"),
)

sa.Index("idx_object_embeddings_model", object_embeddings_table.c.embedding_model)

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

provenance_ledger_table = sa.Table(
    "provenance_ledger",
    postgres_metadata,
    sa.Column("provenance_id", sa.Text(), primary_key=True),
    sa.Column("bound_object_id", sa.Text(), nullable=False, unique=True),
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
)

governance_audit_table = sa.Table(
    "governance_audit",
    postgres_metadata,
    sa.Column("audit_id", sa.Text(), primary_key=True),
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
)

sa.Index("idx_governance_audit_operation_id", governance_audit_table.c.operation_id)
sa.Index("idx_governance_audit_timestamp", governance_audit_table.c.timestamp)

concealed_objects_table = sa.Table(
    "concealed_objects",
    postgres_metadata,
    sa.Column("concealment_id", sa.Text(), primary_key=True),
    sa.Column("operation_id", sa.Text(), nullable=False),
    sa.Column("object_id", sa.Text(), nullable=False, unique=True),
    sa.Column("actor", sa.Text(), nullable=False),
    sa.Column("concealed_at", sa.Text(), nullable=False),
    sa.Column("reason", sa.Text(), nullable=True),
)

sa.Index("idx_concealed_objects_operation_id", concealed_objects_table.c.operation_id)

offline_jobs_table = sa.Table(
    "offline_jobs",
    postgres_metadata,
    sa.Column("job_id", sa.Text(), primary_key=True),
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
)

sa.Index(
    "idx_offline_jobs_ready_queue",
    offline_jobs_table.c.status,
    offline_jobs_table.c.available_at,
    offline_jobs_table.c.priority,
)
sa.Index("idx_offline_jobs_kind", offline_jobs_table.c.job_kind)

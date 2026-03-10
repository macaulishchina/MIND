"""Add product user-state tables for principals, sessions, and namespaces."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260310_0008"
down_revision = "20260310_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("principal_id", sa.Text(), nullable=False),
        sa.Column("principal_kind", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("roles_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capabilities_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("preferences_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("principal_id"),
    )
    op.create_index("idx_principals_tenant_id", "principals", ["tenant_id"])

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("principal_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.principal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("idx_sessions_principal_id", "sessions", ["principal_id"])
    op.create_index("idx_sessions_last_active_at", "sessions", ["last_active_at"])

    op.create_table(
        "namespaces",
        sa.Column("namespace_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.Text(), nullable=True),
        sa.Column("visibility_policy", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("namespace_id"),
    )
    op.create_index("idx_namespaces_tenant_id", "namespaces", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("idx_namespaces_tenant_id", table_name="namespaces")
    op.drop_table("namespaces")
    op.drop_index("idx_sessions_last_active_at", table_name="sessions")
    op.drop_index("idx_sessions_principal_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("idx_principals_tenant_id", table_name="principals")
    op.drop_table("principals")

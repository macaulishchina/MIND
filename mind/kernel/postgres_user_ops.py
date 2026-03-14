"""PostgreSQL user-state, session, namespace, and offline-job operations."""

# mypy: disable-error-code="attr-defined"
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping

from mind.offline_jobs import OfflineJob, OfflineJobKind, OfflineJobStatus

from .sql_tables import (
    namespaces_table,
    offline_jobs_table,
    principals_table,
    sessions_table,
)
from .store import StoreError


class _PostgresUserOpsMixin:
    """User-state, session, namespace, and offline-job mixin for PostgresMemoryStore."""

    def insert_principal(self, principal: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_principal_payload(principal)
        with self.engine.begin() as connection:
            connection.execute(
                pg_insert(principals_table)
                .values(
                    principal_id=payload["principal_id"],
                    principal_kind=payload["principal_kind"],
                    tenant_id=payload["tenant_id"],
                    user_id=payload["user_id"],
                    roles_json=payload["roles"],
                    capabilities_json=payload["capabilities"],
                    preferences_json=payload["preferences"],
                    created_at=_parse_datetime(payload["created_at"]),
                    updated_at=_parse_datetime(payload["updated_at"]),
                )
                .on_conflict_do_update(
                    index_elements=[principals_table.c.principal_id],
                    set_={
                        "principal_kind": payload["principal_kind"],
                        "tenant_id": payload["tenant_id"],
                        "user_id": payload["user_id"],
                        "roles_json": payload["roles"],
                        "capabilities_json": payload["capabilities"],
                        "preferences_json": payload["preferences"],
                        "updated_at": _parse_datetime(payload["updated_at"]),
                    },
                )
            )
        return self.read_principal(str(payload["principal_id"]))

    def read_principal(self, principal_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(principals_table)
                    .where(principals_table.c.principal_id == principal_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StoreError(f"principal '{principal_id}' not found")
        return self._decode_principal_row(row)

    def list_principals(self, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        statement = sa.select(principals_table)
        if tenant_id is not None:
            statement = statement.where(principals_table.c.tenant_id == tenant_id)
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement.order_by(
                    principals_table.c.created_at.asc(),
                    principals_table.c.principal_id.asc(),
                )
            ).mappings()
            return [self._decode_principal_row(row) for row in rows]

    def insert_session(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_session_payload(session)
        with self.engine.begin() as connection:
            connection.execute(
                pg_insert(sessions_table)
                .values(
                    session_id=payload["session_id"],
                    principal_id=payload["principal_id"],
                    conversation_id=payload["conversation_id"],
                    channel=payload["channel"],
                    client_id=payload["client_id"],
                    device_id=payload["device_id"],
                    started_at=_parse_datetime(payload["started_at"]),
                    last_active_at=_parse_datetime(payload["last_active_at"]),
                    metadata_json=payload["metadata"],
                )
                .on_conflict_do_update(
                    index_elements=[sessions_table.c.session_id],
                    set_={
                        "principal_id": payload["principal_id"],
                        "conversation_id": payload["conversation_id"],
                        "channel": payload["channel"],
                        "client_id": payload["client_id"],
                        "device_id": payload["device_id"],
                        "last_active_at": _parse_datetime(payload["last_active_at"]),
                        "metadata_json": payload["metadata"],
                    },
                )
            )
        return self.read_session(str(payload["session_id"]))

    def read_session(self, session_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(sessions_table)
                    .where(sessions_table.c.session_id == session_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StoreError(f"session '{session_id}' not found")
        return self._decode_session_row(row)

    def update_session(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.read_session(session_id)
        merged: dict[str, Any] = {
            **current,
            **updates,
        }
        merged_metadata = dict(current.get("metadata", {}))
        merged_metadata.update(dict(updates.get("metadata", {})))
        merged["metadata"] = merged_metadata
        if "started_at" not in updates:
            merged["started_at"] = current["started_at"]
        if "last_active_at" not in updates:
            merged["last_active_at"] = _utc_now_iso()
        return self.insert_session(merged)

    def list_sessions(self, *, principal_id: str | None = None) -> list[dict[str, Any]]:
        statement = sa.select(sessions_table)
        if principal_id is not None:
            statement = statement.where(sessions_table.c.principal_id == principal_id)
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement.order_by(
                    sessions_table.c.started_at.asc(),
                    sessions_table.c.session_id.asc(),
                )
            ).mappings()
            return [self._decode_session_row(row) for row in rows]

    def insert_namespace(self, namespace: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_namespace_payload(namespace)
        with self.engine.begin() as connection:
            connection.execute(
                pg_insert(namespaces_table)
                .values(
                    namespace_id=payload["namespace_id"],
                    tenant_id=payload["tenant_id"],
                    project_id=payload["project_id"],
                    workspace_id=payload["workspace_id"],
                    visibility_policy=payload["visibility_policy"],
                    created_at=_parse_datetime(payload["created_at"]),
                )
                .on_conflict_do_update(
                    index_elements=[namespaces_table.c.namespace_id],
                    set_={
                        "tenant_id": payload["tenant_id"],
                        "project_id": payload["project_id"],
                        "workspace_id": payload["workspace_id"],
                        "visibility_policy": payload["visibility_policy"],
                    },
                )
            )
        return self.read_namespace(str(payload["namespace_id"]))

    def read_namespace(self, namespace_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.select(namespaces_table)
                    .where(namespaces_table.c.namespace_id == namespace_id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if row is None:
            raise StoreError(f"namespace '{namespace_id}' not found")
        return self._decode_namespace_row(row)

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        with self.engine.begin() as connection:
            connection.execute(
                sa.insert(offline_jobs_table).values(
                    job_id=validated.job_id,
                    job_kind=validated.job_kind.value,
                    status=validated.status.value,
                    payload_json=validated.payload,
                    provider_selection_json=validated.provider_selection,
                    priority=float(validated.priority),
                    available_at=validated.available_at,
                    created_at=validated.created_at,
                    updated_at=validated.updated_at,
                    attempt_count=validated.attempt_count,
                    max_attempts=validated.max_attempts,
                    locked_by=validated.locked_by,
                    locked_at=validated.locked_at,
                    completed_at=validated.completed_at,
                    result_json=validated.result,
                    error_json=validated.error,
                )
            )

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]:
        with self.engine.connect() as connection:
            statement = sa.select(offline_jobs_table)
            status_values = [status.value for status in statuses]
            if status_values:
                statement = statement.where(offline_jobs_table.c.status.in_(status_values))
            rows = connection.execute(
                statement.order_by(
                    offline_jobs_table.c.created_at.asc(),
                    offline_jobs_table.c.job_id.asc(),
                )
            ).mappings()
            return [self._decode_offline_job(row) for row in rows]

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        kind_values = [job_kind.value for job_kind in job_kinds]
        kind_filter = "AND job_kind = ANY(:job_kinds)" if kind_values else ""
        bindparams: list[sa.BindParameter[Any]] = [
            sa.bindparam("worker_id", type_=sa.Text()),
            sa.bindparam("now", type_=sa.DateTime(timezone=True)),
        ]
        if kind_values:
            bindparams.append(sa.bindparam("job_kinds", type_=sa.ARRAY(sa.Text())))

        statement = sa.text(
            f"""
            WITH candidate AS (
                SELECT job_id
                FROM offline_jobs
                WHERE status = 'pending'
                  AND available_at <= :now
                  AND attempt_count < max_attempts
                  {kind_filter}
                ORDER BY priority DESC, available_at ASC, created_at ASC, job_id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            ),
            locked AS (
                SELECT job_id
                FROM candidate
                WHERE pg_try_advisory_xact_lock(hashtext(job_id))
            )
            UPDATE offline_jobs AS jobs
            SET status = 'running',
                locked_by = :worker_id,
                locked_at = :now,
                updated_at = :now,
                attempt_count = jobs.attempt_count + 1
            FROM locked
            WHERE jobs.job_id = locked.job_id
            RETURNING jobs.*
            """
        ).bindparams(*bindparams)
        params: dict[str, Any] = {
            "worker_id": worker_id,
            "now": now,
        }
        if kind_values:
            params["job_kinds"] = kind_values
        with self.engine.begin() as connection:
            row = connection.execute(statement, params).mappings().first()
        if row is None:
            return None
        return self._decode_offline_job(row)

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        with self.engine.begin() as connection:
            updated = connection.execute(
                sa.update(offline_jobs_table)
                .where(offline_jobs_table.c.job_id == job_id)
                .where(offline_jobs_table.c.status == OfflineJobStatus.RUNNING.value)
                .where(offline_jobs_table.c.locked_by == worker_id)
                .values(
                    status=OfflineJobStatus.SUCCEEDED.value,
                    completed_at=completed_at,
                    updated_at=completed_at,
                    result_json=result,
                    error_json=None,
                )
            )
            if updated.rowcount != 1:
                raise StoreError(f"unable to complete offline job '{job_id}'")

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        with self.engine.begin() as connection:
            updated = connection.execute(
                sa.update(offline_jobs_table)
                .where(offline_jobs_table.c.job_id == job_id)
                .where(offline_jobs_table.c.status == OfflineJobStatus.RUNNING.value)
                .where(offline_jobs_table.c.locked_by == worker_id)
                .values(
                    status=OfflineJobStatus.FAILED.value,
                    completed_at=failed_at,
                    updated_at=failed_at,
                    result_json=None,
                    error_json=error,
                )
            )
            if updated.rowcount != 1:
                raise StoreError(f"unable to fail offline job '{job_id}'")

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        with self.engine.begin() as connection:
            updated = connection.execute(
                sa.update(offline_jobs_table)
                .where(offline_jobs_table.c.job_id == job_id)
                .where(
                    offline_jobs_table.c.status.in_(
                        [
                            OfflineJobStatus.PENDING.value,
                            OfflineJobStatus.RUNNING.value,
                        ]
                    )
                )
                .values(
                    status=OfflineJobStatus.FAILED.value,
                    completed_at=cancelled_at,
                    updated_at=cancelled_at,
                    result_json=None,
                    error_json=error,
                    locked_by=sa.func.coalesce(offline_jobs_table.c.locked_by, "cancel"),
                    locked_at=sa.func.coalesce(offline_jobs_table.c.locked_at, cancelled_at),
                )
            )
            if updated.rowcount != 1:
                raise StoreError(f"unable to cancel offline job '{job_id}'")

    @staticmethod
    def _decode_principal_row(row: RowMapping) -> dict[str, Any]:
        return {
            "principal_id": row["principal_id"],
            "principal_kind": row["principal_kind"],
            "tenant_id": row["tenant_id"],
            "user_id": row["user_id"],
            "roles": list(row["roles_json"]),
            "capabilities": list(row["capabilities_json"]),
            "preferences": dict(row["preferences_json"]),
            "created_at": _encode_datetime(row["created_at"]),
            "updated_at": _encode_datetime(row["updated_at"]),
        }

    @staticmethod
    def _decode_session_row(row: RowMapping) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "principal_id": row["principal_id"],
            "conversation_id": row["conversation_id"],
            "channel": row["channel"],
            "client_id": row["client_id"],
            "device_id": row["device_id"],
            "started_at": _encode_datetime(row["started_at"]),
            "last_active_at": _encode_datetime(row["last_active_at"]),
            "metadata": dict(row["metadata_json"]),
        }

    @staticmethod
    def _decode_namespace_row(row: RowMapping) -> dict[str, Any]:
        return {
            "namespace_id": row["namespace_id"],
            "tenant_id": row["tenant_id"],
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "visibility_policy": row["visibility_policy"],
            "created_at": _encode_datetime(row["created_at"]),
        }

    @staticmethod
    def _decode_offline_job(row: RowMapping) -> OfflineJob:
        payload: dict[str, Any] = {
            "job_id": row["job_id"],
            "job_kind": row["job_kind"],
            "status": row["status"],
            "payload": row["payload_json"],
            "provider_selection": row["provider_selection_json"],
            "priority": float(row["priority"]),
            "available_at": row["available_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "attempt_count": int(row["attempt_count"]),
            "max_attempts": int(row["max_attempts"]),
            "locked_by": row["locked_by"],
            "locked_at": row["locked_at"],
            "completed_at": row["completed_at"],
            "result": row["result_json"],
            "error": row["error_json"],
        }
        return OfflineJob.model_validate(payload)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stringify_enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _encode_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalized_principal_payload(principal: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "principal_id": str(principal["principal_id"]),
        "principal_kind": str(_stringify_enum(principal.get("principal_kind", "user"))),
        "tenant_id": str(principal.get("tenant_id", "default")),
        "user_id": principal.get("user_id"),
        "roles": [str(role) for role in principal.get("roles", [])],
        "capabilities": [
            str(_stringify_enum(capability)) for capability in principal.get("capabilities", [])
        ],
        "preferences": dict(principal.get("preferences", {})),
        "created_at": str(principal.get("created_at", now)),
        "updated_at": str(principal.get("updated_at", now)),
    }


def _normalized_session_payload(session: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "session_id": str(session["session_id"]),
        "principal_id": str(session["principal_id"]),
        "conversation_id": session.get("conversation_id"),
        "channel": str(_stringify_enum(session.get("channel", "internal"))),
        "client_id": session.get("client_id"),
        "device_id": session.get("device_id"),
        "started_at": str(session.get("started_at", now)),
        "last_active_at": str(session.get("last_active_at", now)),
        "metadata": dict(session.get("metadata", {})),
    }


def _normalized_namespace_payload(namespace: dict[str, Any]) -> dict[str, Any]:
    return {
        "namespace_id": str(namespace["namespace_id"]),
        "tenant_id": str(namespace.get("tenant_id", "default")),
        "project_id": namespace.get("project_id"),
        "workspace_id": namespace.get("workspace_id"),
        "visibility_policy": str(namespace.get("visibility_policy", "default")),
        "created_at": str(namespace.get("created_at", _utc_now_iso())),
    }



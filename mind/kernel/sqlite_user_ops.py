"""SQLite store user state & offline job operations."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from mind.kernel.store import StoreError
from mind.offline_jobs import OfflineJob, OfflineJobKind, OfflineJobStatus


class _SQLiteUserOpsMixin:
    """Mixin: principal, session, namespace, and offline job operations."""

    connection: sqlite3.Connection
    _transaction_open: bool

    def insert_principal(self, principal: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_principal_payload(principal)
        self.connection.execute(
            """
            INSERT INTO principals (
                principal_id,
                principal_kind,
                tenant_id,
                user_id,
                roles_json,
                capabilities_json,
                preferences_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(principal_id) DO UPDATE SET
                principal_kind = excluded.principal_kind,
                tenant_id = excluded.tenant_id,
                user_id = excluded.user_id,
                roles_json = excluded.roles_json,
                capabilities_json = excluded.capabilities_json,
                preferences_json = excluded.preferences_json,
                created_at = principals.created_at,
                updated_at = excluded.updated_at
            """,
            (
                payload["principal_id"],
                payload["principal_kind"],
                payload["tenant_id"],
                payload["user_id"],
                json.dumps(payload["roles"], ensure_ascii=True, sort_keys=True),
                json.dumps(payload["capabilities"], ensure_ascii=True, sort_keys=True),
                json.dumps(payload["preferences"], ensure_ascii=True, sort_keys=True),
                payload["created_at"],
                payload["updated_at"],
            ),
        )
        self.connection.commit()
        return self.read_principal(str(payload["principal_id"]))

    def read_principal(self, principal_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT *
            FROM principals
            WHERE principal_id = ?
            """,
            (principal_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"principal '{principal_id}' not found")
        return self._decode_principal_row(row)

    def list_principals(self, *, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if tenant_id is None:
            rows = self.connection.execute(
                """
                SELECT *
                FROM principals
                ORDER BY created_at ASC, principal_id ASC
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT *
                FROM principals
                WHERE tenant_id = ?
                ORDER BY created_at ASC, principal_id ASC
                """,
                (tenant_id,),
            ).fetchall()
        return [self._decode_principal_row(row) for row in rows]

    def insert_session(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_session_payload(session)
        self.connection.execute(
            """
            INSERT INTO sessions (
                session_id,
                principal_id,
                conversation_id,
                channel,
                client_id,
                device_id,
                started_at,
                last_active_at,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                principal_id = excluded.principal_id,
                conversation_id = excluded.conversation_id,
                channel = excluded.channel,
                client_id = excluded.client_id,
                device_id = excluded.device_id,
                started_at = sessions.started_at,
                last_active_at = excluded.last_active_at,
                metadata_json = excluded.metadata_json
            """,
            (
                payload["session_id"],
                payload["principal_id"],
                payload["conversation_id"],
                payload["channel"],
                payload["client_id"],
                payload["device_id"],
                payload["started_at"],
                payload["last_active_at"],
                json.dumps(payload["metadata"], ensure_ascii=True, sort_keys=True),
            ),
        )
        self.connection.commit()
        return self.read_session(str(payload["session_id"]))

    def read_session(self, session_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT *
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
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
        if principal_id is None:
            rows = self.connection.execute(
                """
                SELECT *
                FROM sessions
                ORDER BY started_at ASC, session_id ASC
                """
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT *
                FROM sessions
                WHERE principal_id = ?
                ORDER BY started_at ASC, session_id ASC
                """,
                (principal_id,),
            ).fetchall()
        return [self._decode_session_row(row) for row in rows]

    def insert_namespace(self, namespace: dict[str, Any]) -> dict[str, Any]:
        payload = _normalized_namespace_payload(namespace)
        self.connection.execute(
            """
            INSERT INTO namespaces (
                namespace_id,
                tenant_id,
                project_id,
                workspace_id,
                visibility_policy,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(namespace_id) DO UPDATE SET
                tenant_id = excluded.tenant_id,
                project_id = excluded.project_id,
                workspace_id = excluded.workspace_id,
                visibility_policy = excluded.visibility_policy,
                created_at = namespaces.created_at
            """,
            (
                payload["namespace_id"],
                payload["tenant_id"],
                payload["project_id"],
                payload["workspace_id"],
                payload["visibility_policy"],
                payload["created_at"],
            ),
        )
        self.connection.commit()
        return self.read_namespace(str(payload["namespace_id"]))

    def read_namespace(self, namespace_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT *
            FROM namespaces
            WHERE namespace_id = ?
            """,
            (namespace_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"namespace '{namespace_id}' not found")
        return self._decode_namespace_row(row)

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        self.connection.execute(
            """
            INSERT INTO offline_jobs (
                job_id,
                job_kind,
                status,
                payload_json,
                provider_selection_json,
                priority,
                available_at,
                created_at,
                updated_at,
                attempt_count,
                max_attempts,
                locked_by,
                locked_at,
                completed_at,
                result_json,
                error_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validated.job_id,
                validated.job_kind.value,
                validated.status.value,
                json.dumps(validated.payload, ensure_ascii=True, sort_keys=True),
                (
                    json.dumps(validated.provider_selection, ensure_ascii=True, sort_keys=True)
                    if validated.provider_selection is not None
                    else None
                ),
                float(validated.priority),
                validated.available_at.isoformat(),
                validated.created_at.isoformat(),
                validated.updated_at.isoformat(),
                validated.attempt_count,
                validated.max_attempts,
                validated.locked_by,
                validated.locked_at.isoformat() if validated.locked_at is not None else None,
                (
                    validated.completed_at.isoformat()
                    if validated.completed_at is not None
                    else None
                ),
                (
                    json.dumps(validated.result, ensure_ascii=True, sort_keys=True)
                    if validated.result is not None
                    else None
                ),
                (
                    json.dumps(validated.error, ensure_ascii=True, sort_keys=True)
                    if validated.error is not None
                    else None
                ),
            ),
        )
        self.connection.commit()

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]:
        status_values = [status.value for status in statuses]
        if status_values:
            placeholders = ", ".join("?" for _ in status_values)
            rows = self.connection.execute(
                f"""
                SELECT *
                FROM offline_jobs
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC, job_id ASC
                """,
                tuple(status_values),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT *
                FROM offline_jobs
                ORDER BY created_at ASC, job_id ASC
                """
            ).fetchall()
        return [self._decode_offline_job_row(row) for row in rows]

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        jobs = self.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING])
        allowed_kinds = {job_kind.value for job_kind in job_kinds}
        candidates = [
            job
            for job in jobs
            if job.available_at <= now
            and job.attempt_count < job.max_attempts
            and (not allowed_kinds or job.job_kind.value in allowed_kinds)
        ]
        candidates.sort(
            key=lambda item: (-item.priority, item.available_at, item.created_at, item.job_id)
        )
        if not candidates:
            return None

        chosen = candidates[0]
        claimed = chosen.model_copy(
            update={
                "status": OfflineJobStatus.RUNNING,
                "locked_by": worker_id,
                "locked_at": now,
                "updated_at": now,
                "attempt_count": chosen.attempt_count + 1,
            }
        )
        self.connection.execute(
            """
            UPDATE offline_jobs
            SET status = ?,
                locked_by = ?,
                locked_at = ?,
                updated_at = ?,
                attempt_count = ?
            WHERE job_id = ?
            """,
            (
                claimed.status.value,
                claimed.locked_by,
                claimed.locked_at.isoformat() if claimed.locked_at is not None else None,
                claimed.updated_at.isoformat(),
                claimed.attempt_count,
                claimed.job_id,
            ),
        )
        self.connection.commit()
        return claimed

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        updated = self.connection.execute(
            """
            UPDATE offline_jobs
            SET status = ?,
                completed_at = ?,
                updated_at = ?,
                result_json = ?,
                error_json = NULL
            WHERE job_id = ?
              AND status = ?
              AND locked_by = ?
            """,
            (
                OfflineJobStatus.SUCCEEDED.value,
                completed_at.isoformat(),
                completed_at.isoformat(),
                json.dumps(result, ensure_ascii=True, sort_keys=True),
                job_id,
                OfflineJobStatus.RUNNING.value,
                worker_id,
            ),
        )
        if updated.rowcount != 1:
            raise StoreError(f"unable to complete offline job '{job_id}'")
        self.connection.commit()

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        updated = self.connection.execute(
            """
            UPDATE offline_jobs
            SET status = ?,
                completed_at = ?,
                updated_at = ?,
                result_json = NULL,
                error_json = ?
            WHERE job_id = ?
              AND status = ?
              AND locked_by = ?
            """,
            (
                OfflineJobStatus.FAILED.value,
                failed_at.isoformat(),
                failed_at.isoformat(),
                json.dumps(error, ensure_ascii=True, sort_keys=True),
                job_id,
                OfflineJobStatus.RUNNING.value,
                worker_id,
            ),
        )
        if updated.rowcount != 1:
            raise StoreError(f"unable to fail offline job '{job_id}'")
        self.connection.commit()

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        updated = self.connection.execute(
            """
            UPDATE offline_jobs
            SET status = ?,
                completed_at = ?,
                updated_at = ?,
                result_json = NULL,
                error_json = ?,
                locked_by = COALESCE(locked_by, 'cancel'),
                locked_at = COALESCE(locked_at, ?)
            WHERE job_id = ?
              AND status IN (?, ?)
            """,
            (
                OfflineJobStatus.FAILED.value,
                cancelled_at.isoformat(),
                cancelled_at.isoformat(),
                json.dumps(error, ensure_ascii=True, sort_keys=True),
                cancelled_at.isoformat(),
                job_id,
                OfflineJobStatus.PENDING.value,
                OfflineJobStatus.RUNNING.value,
            ),
        )
        if updated.rowcount != 1:
            raise StoreError(f"unable to cancel offline job '{job_id}'")
        self.connection.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_principal_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "principal_id": row["principal_id"],
            "principal_kind": row["principal_kind"],
            "tenant_id": row["tenant_id"],
            "user_id": row["user_id"],
            "roles": json.loads(row["roles_json"]),
            "capabilities": json.loads(row["capabilities_json"]),
            "preferences": json.loads(row["preferences_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _decode_session_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "principal_id": row["principal_id"],
            "conversation_id": row["conversation_id"],
            "channel": row["channel"],
            "client_id": row["client_id"],
            "device_id": row["device_id"],
            "started_at": row["started_at"],
            "last_active_at": row["last_active_at"],
            "metadata": json.loads(row["metadata_json"]),
        }

    @staticmethod
    def _decode_namespace_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "namespace_id": row["namespace_id"],
            "tenant_id": row["tenant_id"],
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "visibility_policy": row["visibility_policy"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _decode_offline_job_row(row: sqlite3.Row) -> OfflineJob:
        payload: dict[str, Any] = {
            "job_id": row["job_id"],
            "job_kind": row["job_kind"],
            "status": row["status"],
            "payload": json.loads(row["payload_json"]),
            "provider_selection": (
                json.loads(row["provider_selection_json"])
                if row["provider_selection_json"]
                else None
            ),
            "priority": float(row["priority"]),
            "available_at": row["available_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "attempt_count": int(row["attempt_count"]),
            "max_attempts": int(row["max_attempts"]),
            "locked_by": row["locked_by"],
            "locked_at": row["locked_at"],
            "completed_at": row["completed_at"],
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }
        return OfflineJob.model_validate(payload)


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _stringify_enum(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


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

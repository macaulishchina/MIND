"""SQLite store implementation details (schema, write, decode)."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mind.kernel.contracts import BudgetEvent, PrimitiveCallLog
from mind.kernel.governance import ConcealmentRecord, GovernanceAuditRecord
from mind.kernel.provenance import DirectProvenanceRecord
from mind.kernel.store import StoreError


class _SQLiteImplMixin:
    """Mixin: schema init, internal write/decode helpers for SQLiteMemoryStore."""

    connection: sqlite3.Connection
    _transaction_open: bool

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS object_versions (
                object_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                priority REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (object_id, version)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_object_versions_object_id ON object_versions(object_id)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_object_versions_type ON object_versions(type)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS primitive_call_logs (
                call_id TEXT PRIMARY KEY,
                primitive TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                target_ids_json TEXT NOT NULL,
                cost_json TEXT NOT NULL,
                outcome TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT,
                error_json TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_primitive_call_logs_timestamp
            ON primitive_call_logs(timestamp)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_events (
                event_id TEXT PRIMARY KEY,
                call_id TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                primitive TEXT NOT NULL,
                actor TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                outcome TEXT NOT NULL,
                cost_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_budget_events_call_id ON budget_events(call_id)"
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS provenance_ledger (
                provenance_id TEXT PRIMARY KEY,
                bound_object_id TEXT NOT NULL UNIQUE,
                bound_object_type TEXT NOT NULL,
                producer_kind TEXT NOT NULL,
                producer_id TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                source_channel TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                retention_class TEXT NOT NULL,
                user_id TEXT,
                model_id TEXT,
                model_provider TEXT,
                model_version TEXT,
                ip_addr TEXT,
                device_id TEXT,
                machine_fingerprint TEXT,
                session_id TEXT,
                request_id TEXT,
                conversation_id TEXT,
                episode_id TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_provenance_ledger_bound_object
            ON provenance_ledger(bound_object_id)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_audit (
                audit_id TEXT PRIMARY KEY,
                operation_id TEXT NOT NULL,
                action TEXT NOT NULL,
                stage TEXT NOT NULL,
                actor TEXT NOT NULL,
                capability TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                outcome TEXT NOT NULL,
                scope TEXT,
                reason TEXT,
                target_object_ids_json TEXT NOT NULL,
                target_provenance_ids_json TEXT NOT NULL,
                selection_json TEXT NOT NULL,
                summary_json TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_governance_audit_operation_id
            ON governance_audit(operation_id)
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_governance_audit_timestamp
            ON governance_audit(timestamp)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS concealed_objects (
                concealment_id TEXT PRIMARY KEY,
                operation_id TEXT NOT NULL,
                object_id TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                concealed_at TEXT NOT NULL,
                reason TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_concealed_objects_operation_id
            ON concealed_objects(operation_id)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS principals (
                principal_id TEXT PRIMARY KEY,
                principal_kind TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                user_id TEXT,
                roles_json TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                preferences_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_principals_tenant_id
            ON principals(tenant_id)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                conversation_id TEXT,
                channel TEXT NOT NULL,
                client_id TEXT,
                device_id TEXT,
                started_at TEXT NOT NULL,
                last_active_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY (principal_id) REFERENCES principals(principal_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sessions_principal_id
            ON sessions(principal_id)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS namespaces (
                namespace_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project_id TEXT,
                workspace_id TEXT,
                visibility_policy TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_namespaces_tenant_id
            ON namespaces(tenant_id)
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS offline_jobs (
                job_id TEXT PRIMARY KEY,
                job_kind TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                provider_selection_json TEXT,
                priority REAL NOT NULL,
                available_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                locked_by TEXT,
                locked_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                error_json TEXT
            )
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_offline_jobs_ready_queue
            ON offline_jobs(status, available_at, priority)
            """
        )
        self.connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_offline_jobs_kind
            ON offline_jobs(job_kind)
            """
        )
        self._ensure_sqlite_column(
            "offline_jobs",
            "provider_selection_json",
            "TEXT",
        )
        self.connection.commit()

    def _ensure_sqlite_column(
        self,
        table_name: str,
        column_name: str,
        column_sql: str,
    ) -> None:
        rows = self.connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        if any(row["name"] == column_name for row in rows):
            return
        self.connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
    def _begin_transaction(self) -> None:
        if self._transaction_open:
            raise StoreError("nested primitive transactions are not supported")
        self.connection.execute("BEGIN")
        self._transaction_open = True

    def _commit_transaction(self) -> None:
        if not self._transaction_open:
            raise StoreError("no active transaction to commit")
        self.connection.commit()
        self._transaction_open = False

    def _rollback_transaction(self) -> None:
        if not self._transaction_open:
            return
        self.connection.rollback()
        self._transaction_open = False

    def _write_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None:
        validated = PrimitiveCallLog.model_validate(log)
        self.connection.execute(
            """
            INSERT INTO primitive_call_logs (
                call_id,
                primitive,
                actor,
                timestamp,
                target_ids_json,
                cost_json,
                outcome,
                request_json,
                response_json,
                error_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validated.call_id,
                validated.primitive.value,
                validated.actor,
                validated.timestamp.isoformat(),
                json.dumps(validated.target_ids, ensure_ascii=True),
                json.dumps(
                    [item.model_dump(mode="json") for item in validated.cost],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                validated.outcome.value,
                json.dumps(validated.request, ensure_ascii=True, sort_keys=True),
                (
                    json.dumps(validated.response, ensure_ascii=True, sort_keys=True)
                    if validated.response is not None
                    else None
                ),
                (
                    json.dumps(
                        validated.error.model_dump(mode="json"),
                        ensure_ascii=True,
                        sort_keys=True,
                    )
                    if validated.error is not None
                    else None
                ),
            ),
        )

    def _write_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None:
        validated = BudgetEvent.model_validate(event)
        self.connection.execute(
            """
            INSERT INTO budget_events (
                event_id,
                call_id,
                scope_id,
                primitive,
                actor,
                timestamp,
                outcome,
                cost_json,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validated.event_id,
                validated.call_id,
                validated.scope_id,
                validated.primitive.value,
                validated.actor,
                validated.timestamp.isoformat(),
                validated.outcome.value,
                json.dumps(
                    [item.model_dump(mode="json") for item in validated.cost],
                    ensure_ascii=True,
                    sort_keys=True,
                ),
                json.dumps(validated.metadata, ensure_ascii=True, sort_keys=True),
            ),
        )

    def _write_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        validated = DirectProvenanceRecord.model_validate(record)
        if self.connection.execute(
            """
            SELECT 1
            FROM provenance_ledger
            WHERE bound_object_id = ?
            LIMIT 1
            """,
            (validated.bound_object_id,),
        ).fetchone():
            raise StoreError(
                f"direct provenance already exists for object '{validated.bound_object_id}'"
            )

        try:
            bound_object = self.read_object(validated.bound_object_id)
        except StoreError as exc:
            raise StoreError(
                f"cannot bind direct provenance to missing object '{validated.bound_object_id}'"
            ) from exc
        if bound_object["type"] != validated.bound_object_type:
            raise StoreError(
                "direct provenance bound_object_type mismatch: "
                f"expected '{bound_object['type']}', got '{validated.bound_object_type}'"
            )

        payload = validated.model_dump(mode="json")
        self.connection.execute(
            """
            INSERT INTO provenance_ledger (
                provenance_id,
                bound_object_id,
                bound_object_type,
                producer_kind,
                producer_id,
                captured_at,
                ingested_at,
                source_channel,
                tenant_id,
                retention_class,
                user_id,
                model_id,
                model_provider,
                model_version,
                ip_addr,
                device_id,
                machine_fingerprint,
                session_id,
                request_id,
                conversation_id,
                episode_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["provenance_id"],
                payload["bound_object_id"],
                payload["bound_object_type"],
                payload["producer_kind"],
                payload["producer_id"],
                payload["captured_at"],
                payload["ingested_at"],
                payload["source_channel"],
                payload["tenant_id"],
                payload["retention_class"],
                payload.get("user_id"),
                payload.get("model_id"),
                payload.get("model_provider"),
                payload.get("model_version"),
                payload.get("ip_addr"),
                payload.get("device_id"),
                payload.get("machine_fingerprint"),
                payload.get("session_id"),
                payload.get("request_id"),
                payload.get("conversation_id"),
                payload.get("episode_id"),
            ),
        )

    def _write_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None:
        validated = ConcealmentRecord.model_validate(record)
        if not self.has_object(validated.object_id):
            raise StoreError(f"cannot conceal missing object '{validated.object_id}'")
        self.connection.execute(
            """
            INSERT INTO concealed_objects (
                concealment_id,
                operation_id,
                object_id,
                actor,
                concealed_at,
                reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                validated.concealment_id,
                validated.operation_id,
                validated.object_id,
                validated.actor,
                validated.concealed_at.isoformat(),
                validated.reason,
            ),
        )

    def _write_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        validated = GovernanceAuditRecord.model_validate(record)
        payload = validated.model_dump(mode="json")
        self.connection.execute(
            """
            INSERT INTO governance_audit (
                audit_id,
                operation_id,
                action,
                stage,
                actor,
                capability,
                timestamp,
                outcome,
                scope,
                reason,
                target_object_ids_json,
                target_provenance_ids_json,
                selection_json,
                summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["audit_id"],
                payload["operation_id"],
                payload["action"],
                payload["stage"],
                payload["actor"],
                payload["capability"],
                payload["timestamp"],
                payload["outcome"],
                payload.get("scope"),
                payload.get("reason"),
                json.dumps(payload["target_object_ids"], ensure_ascii=True),
                json.dumps(payload["target_provenance_ids"], ensure_ascii=True),
                json.dumps(payload["selection"], ensure_ascii=True, sort_keys=True),
                json.dumps(payload["summary"], ensure_ascii=True, sort_keys=True),
            ),
        )

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["object_id"],
            "type": row["type"],
            "content": json.loads(row["content_json"]),
            "source_refs": json.loads(row["source_refs_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": int(row["version"]),
            "status": row["status"],
            "priority": float(row["priority"]),
            "metadata": json.loads(row["metadata_json"]),
        }

    @staticmethod
    def _decode_primitive_call_log(row: sqlite3.Row) -> PrimitiveCallLog:
        payload: dict[str, Any] = {
            "call_id": row["call_id"],
            "primitive": row["primitive"],
            "actor": row["actor"],
            "timestamp": row["timestamp"],
            "target_ids": json.loads(row["target_ids_json"]),
            "cost": json.loads(row["cost_json"]),
            "outcome": row["outcome"],
            "request": json.loads(row["request_json"]),
            "response": json.loads(row["response_json"]) if row["response_json"] else None,
            "error": json.loads(row["error_json"]) if row["error_json"] else None,
        }
        return PrimitiveCallLog.model_validate(payload)

    @staticmethod
    def _decode_budget_event(row: sqlite3.Row) -> BudgetEvent:
        payload: dict[str, Any] = {
            "event_id": row["event_id"],
            "call_id": row["call_id"],
            "scope_id": row["scope_id"],
            "primitive": row["primitive"],
            "actor": row["actor"],
            "timestamp": row["timestamp"],
            "outcome": row["outcome"],
            "cost": json.loads(row["cost_json"]),
            "metadata": json.loads(row["metadata_json"]),
        }
        return BudgetEvent.model_validate(payload)

    @staticmethod
    def _decode_direct_provenance_row(row: sqlite3.Row) -> DirectProvenanceRecord:
        payload: dict[str, Any] = {
            "provenance_id": row["provenance_id"],
            "bound_object_id": row["bound_object_id"],
            "bound_object_type": row["bound_object_type"],
            "producer_kind": row["producer_kind"],
            "producer_id": row["producer_id"],
            "captured_at": row["captured_at"],
            "ingested_at": row["ingested_at"],
            "source_channel": row["source_channel"],
            "tenant_id": row["tenant_id"],
            "retention_class": row["retention_class"],
            "user_id": row["user_id"],
            "model_id": row["model_id"],
            "model_provider": row["model_provider"],
            "model_version": row["model_version"],
            "ip_addr": row["ip_addr"],
            "device_id": row["device_id"],
            "machine_fingerprint": row["machine_fingerprint"],
            "session_id": row["session_id"],
            "request_id": row["request_id"],
            "conversation_id": row["conversation_id"],
            "episode_id": row["episode_id"],
        }
        return DirectProvenanceRecord.model_validate(payload)

    @staticmethod
    def _decode_governance_audit_row(row: sqlite3.Row) -> GovernanceAuditRecord:
        payload: dict[str, Any] = {
            "audit_id": row["audit_id"],
            "operation_id": row["operation_id"],
            "action": row["action"],
            "stage": row["stage"],
            "actor": row["actor"],
            "capability": row["capability"],
            "timestamp": row["timestamp"],
            "outcome": row["outcome"],
            "scope": row["scope"],
            "reason": row["reason"],
            "target_object_ids": json.loads(row["target_object_ids_json"]),
            "target_provenance_ids": json.loads(row["target_provenance_ids_json"]),
            "selection": json.loads(row["selection_json"]),
            "summary": json.loads(row["summary_json"]),
        }
        return GovernanceAuditRecord.model_validate(payload)

    @staticmethod
    def _decode_concealment_row(row: sqlite3.Row) -> ConcealmentRecord:
        payload: dict[str, Any] = {
            "concealment_id": row["concealment_id"],
            "operation_id": row["operation_id"],
            "object_id": row["object_id"],
            "actor": row["actor"],
            "concealed_at": row["concealed_at"],
            "reason": row["reason"],
        }
        return ConcealmentRecord.model_validate(payload)


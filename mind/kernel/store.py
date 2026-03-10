"""Append-only SQLite-backed memory storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from mind.kernel.governance import ConcealmentRecord, GovernanceAuditRecord
from mind.kernel.provenance import DirectProvenanceRecord
from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog, RetrieveQueryMode

from .retrieval import RetrievalMatch, latest_objects, matches_retrieval_filters, search_objects
from .schema import ensure_valid_object


class StoreError(RuntimeError):
    """Raised when a store operation cannot be completed safely."""


class MemoryStore(Protocol):
    """Minimal store contract shared by Phase B/C kernel code."""

    def insert_object(self, obj: dict[str, Any]) -> None: ...

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None: ...

    def transaction(self) -> PrimitiveTransactionContextManager: ...

    def has_object(self, object_id: str) -> bool: ...

    def versions_for_object(self, object_id: str) -> list[int]: ...

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]: ...

    def iter_objects(self) -> list[dict[str, Any]]: ...

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None: ...

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord: ...

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord: ...

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]: ...

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None: ...

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord: ...

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]: ...

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]: ...

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None: ...

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord: ...

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord: ...

    def is_object_concealed(self, object_id: str) -> bool: ...

    def iter_concealments(self) -> list[ConcealmentRecord]: ...

    def iter_latest_objects(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def search_latest_objects(
        self,
        *,
        query: str | dict[str, Any],
        query_modes: Iterable[RetrieveQueryMode],
        max_candidates: int,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
        query_embedding: tuple[float, ...] | None = None,
    ) -> list[RetrievalMatch]: ...

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]: ...

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None: ...

    def iter_primitive_call_logs(self) -> list[PrimitiveCallLog]: ...

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None: ...

    def iter_budget_events(self) -> list[BudgetEvent]: ...


class PrimitiveTransaction(Protocol):
    """Primitive-scoped transaction contract for atomic write paths."""

    def insert_object(self, obj: dict[str, Any]) -> None: ...

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None: ...

    def has_object(self, object_id: str) -> bool: ...

    def versions_for_object(self, object_id: str) -> list[int]: ...

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]: ...

    def iter_objects(self) -> list[dict[str, Any]]: ...

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None: ...

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord: ...

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord: ...

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]: ...

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None: ...

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord: ...

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]: ...

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]: ...

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None: ...

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord: ...

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord: ...

    def is_object_concealed(self, object_id: str) -> bool: ...

    def iter_concealments(self) -> list[ConcealmentRecord]: ...

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]: ...

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None: ...

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None: ...


type MemoryStoreContextManager = AbstractContextManager[MemoryStore]
type PrimitiveTransactionContextManager = AbstractContextManager[PrimitiveTransaction]
type MemoryStoreFactory = Callable[[Path], MemoryStoreContextManager]


class SQLiteMemoryStore:
    """A minimal append-only memory store for Phase B."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._transaction_open = False
        self._init_schema()

    def close(self) -> None:
        if self._transaction_open:
            self.connection.rollback()
            self._transaction_open = False
        self.connection.close()

    def __enter__(self) -> SQLiteMemoryStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

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
        self.connection.commit()

    def insert_object(self, obj: dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.insert_object(obj)

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None:
        with self.transaction() as transaction:
            transaction.insert_objects(objects)

    def transaction(self) -> PrimitiveTransactionContextManager:
        return _SQLiteStoreTransaction(self)

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_primitive_call(log)

    def iter_primitive_call_logs(self) -> list[PrimitiveCallLog]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM primitive_call_logs
            ORDER BY timestamp ASC, call_id ASC
            """
        ).fetchall()
        return [self._decode_primitive_call_log(row) for row in rows]

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_budget_event(event)

    def iter_budget_events(self) -> list[BudgetEvent]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM budget_events
            ORDER BY timestamp ASC, event_id ASC
            """
        ).fetchall()
        return [self._decode_budget_event(row) for row in rows]

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        with self.transaction() as transaction:
            transaction.insert_direct_provenance(record)

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord:
        row = self.connection.execute(
            """
            SELECT *
            FROM provenance_ledger
            WHERE provenance_id = ?
            """,
            (provenance_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"direct provenance '{provenance_id}' not found")
        return self._decode_direct_provenance_row(row)

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord:
        row = self.connection.execute(
            """
            SELECT *
            FROM provenance_ledger
            WHERE bound_object_id = ?
            """,
            (object_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"direct provenance for object '{object_id}' not found")
        return self._decode_direct_provenance_row(row)

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM provenance_ledger
            ORDER BY ingested_at ASC, provenance_id ASC
            """
        ).fetchall()
        return [self._decode_direct_provenance_row(row) for row in rows]

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        with self.transaction() as transaction:
            transaction.record_governance_audit(record)

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord:
        row = self.connection.execute(
            """
            SELECT *
            FROM governance_audit
            WHERE audit_id = ?
            """,
            (audit_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"governance audit '{audit_id}' not found")
        return self._decode_governance_audit_row(row)

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM governance_audit
            ORDER BY timestamp ASC, audit_id ASC
            """
        ).fetchall()
        return [self._decode_governance_audit_row(row) for row in rows]

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM governance_audit
            WHERE operation_id = ?
            ORDER BY timestamp ASC, audit_id ASC
            """,
            (operation_id,),
        ).fetchall()
        return [self._decode_governance_audit_row(row) for row in rows]

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_concealment(record)

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord:
        row = self.connection.execute(
            """
            SELECT *
            FROM concealed_objects
            WHERE concealment_id = ?
            """,
            (concealment_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"concealment '{concealment_id}' not found")
        return self._decode_concealment_row(row)

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord:
        row = self.connection.execute(
            """
            SELECT *
            FROM concealed_objects
            WHERE object_id = ?
            """,
            (object_id,),
        ).fetchone()
        if row is None:
            raise StoreError(f"concealment for object '{object_id}' not found")
        return self._decode_concealment_row(row)

    def is_object_concealed(self, object_id: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM concealed_objects
            WHERE object_id = ?
            LIMIT 1
            """,
            (object_id,),
        ).fetchone()
        return row is not None

    def iter_concealments(self) -> list[ConcealmentRecord]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM concealed_objects
            ORDER BY concealed_at ASC, concealment_id ASC
            """
        ).fetchall()
        return [self._decode_concealment_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_and_insert(self, obj: dict[str, Any]) -> None:
        """Check store-level invariants and execute the INSERT.

        Does **not** commit — the caller is responsible for commit/rollback.
        """
        object_id = obj["id"]
        version = obj["version"]
        existing_versions = self.versions_for_object(object_id)

        if version == 1 and existing_versions:
            raise StoreError(f"object '{object_id}' version 1 already exists")
        if version > 1 and not existing_versions:
            raise StoreError(f"object '{object_id}' version {version} missing prior versions")
        if version > 1 and version != max(existing_versions) + 1:
            raise StoreError(f"object '{object_id}' version chain must be contiguous")

        # I-2 fix: enforce type consistency across versions
        if version > 1:
            prev = self.read_object(object_id, max(existing_versions))
            if prev["type"] != obj["type"]:
                raise StoreError(
                    f"object '{object_id}' type changed from "
                    f"'{prev['type']}' to '{obj['type']}' across versions"
                )

        missing_refs = [ref for ref in obj["source_refs"] if not self.has_object(ref)]
        if missing_refs:
            raise StoreError(f"object '{object_id}' has dangling source refs: {missing_refs}")

        try:
            self.connection.execute(
                """
                INSERT INTO object_versions (
                    object_id,
                    version,
                    type,
                    content_json,
                    source_refs_json,
                    created_at,
                    updated_at,
                    status,
                    priority,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    version,
                    obj["type"],
                    json.dumps(obj["content"], ensure_ascii=True, sort_keys=True),
                    json.dumps(obj["source_refs"], ensure_ascii=True),
                    obj["created_at"],
                    obj["updated_at"],
                    obj["status"],
                    float(obj["priority"]),
                    json.dumps(obj["metadata"], ensure_ascii=True, sort_keys=True),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError(str(exc)) from exc

    def has_object(self, object_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM object_versions WHERE object_id = ? LIMIT 1", (object_id,)
        ).fetchone()
        return row is not None

    def versions_for_object(self, object_id: str) -> list[int]:
        rows = self.connection.execute(
            "SELECT version FROM object_versions WHERE object_id = ? ORDER BY version ASC",
            (object_id,),
        ).fetchall()
        return [int(row["version"]) for row in rows]

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        if version is None:
            row = self.connection.execute(
                """
                SELECT * FROM object_versions
                WHERE object_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (object_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM object_versions WHERE object_id = ? AND version = ?",
                (object_id, version),
            ).fetchone()

        if row is None:
            raise StoreError(f"object '{object_id}' not found")
        return self._decode_row(row)

    def iter_objects(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM object_versions
            ORDER BY inserted_at ASC, object_id ASC, version ASC
            """
        ).fetchall()
        return [self._decode_row(row) for row in rows]

    def iter_latest_objects(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        latest_objects = _latest_objects(self.iter_objects())
        return [
            obj
            for obj in latest_objects
            if not self.is_object_concealed(obj["id"])
            and _matches_retrieval_filters(
                obj,
                object_types=object_types,
                statuses=statuses,
                episode_id=episode_id,
                task_id=task_id,
            )
        ]

    def search_latest_objects(
        self,
        *,
        query: str | dict[str, Any],
        query_modes: Iterable[RetrieveQueryMode],
        max_candidates: int,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
        query_embedding: tuple[float, ...] | None = None,
    ) -> list[RetrievalMatch]:
        latest_candidates = self.iter_latest_objects(
            object_types=object_types,
            statuses=statuses,
            episode_id=episode_id,
            task_id=task_id,
        )
        return search_objects(
            latest_candidates,
            query=query,
            query_modes=list(query_modes),
            max_candidates=max_candidates,
            object_types=[],
            statuses=[],
            episode_id=None,
            task_id=None,
            query_embedding=query_embedding,
        )

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        records = [
            obj
            for obj in self.iter_objects()
            if obj["type"] == "RawRecord"
            and obj["metadata"]["episode_id"] == episode_id
            and not self.is_object_concealed(obj["id"])
        ]
        return sorted(records, key=lambda item: item["metadata"]["timestamp_order"])

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


class _SQLiteStoreTransaction:
    """Explicit transaction wrapper used by Phase C write paths."""

    def __init__(self, store: SQLiteMemoryStore) -> None:
        self._store = store

    def __enter__(self) -> _SQLiteStoreTransaction:
        self._store._begin_transaction()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            try:
                self._store._commit_transaction()
            except Exception:
                self._store._rollback_transaction()
                raise
            return
        self._store._rollback_transaction()

    def insert_object(self, obj: dict[str, Any]) -> None:
        ensure_valid_object(obj)
        self._store._validate_and_insert(obj)

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None:
        obj_list = list(objects)
        for obj in obj_list:
            ensure_valid_object(obj)
        for obj in obj_list:
            self._store._validate_and_insert(obj)

    def has_object(self, object_id: str) -> bool:
        return self._store.has_object(object_id)

    def versions_for_object(self, object_id: str) -> list[int]:
        return self._store.versions_for_object(object_id)

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        return self._store.read_object(object_id, version)

    def iter_objects(self) -> list[dict[str, Any]]:
        return self._store.iter_objects()

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        self._store._write_direct_provenance(record)

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord:
        return self._store.read_direct_provenance(provenance_id)

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord:
        return self._store.direct_provenance_for_object(object_id)

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]:
        return self._store.iter_direct_provenance()

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        self._store._write_governance_audit(record)

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord:
        return self._store.read_governance_audit(audit_id)

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]:
        return self._store.iter_governance_audit()

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]:
        return self._store.iter_governance_audit_for_operation(operation_id)

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None:
        self._store._write_concealment(record)

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord:
        return self._store.read_concealment(concealment_id)

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord:
        return self._store.concealment_for_object(object_id)

    def is_object_concealed(self, object_id: str) -> bool:
        return self._store.is_object_concealed(object_id)

    def iter_concealments(self) -> list[ConcealmentRecord]:
        return self._store.iter_concealments()

    def iter_latest_objects(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._store.iter_latest_objects(
            object_types=object_types,
            statuses=statuses,
            episode_id=episode_id,
            task_id=task_id,
        )

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        return self._store.raw_records_for_episode(episode_id)

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None:
        self._store._write_primitive_call(log)

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None:
        self._store._write_budget_event(event)


def _latest_objects(objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return latest_objects(list(objects))


def _matches_retrieval_filters(
    obj: dict[str, Any],
    *,
    object_types: Iterable[str] = (),
    statuses: Iterable[str] = (),
    episode_id: str | None = None,
    task_id: str | None = None,
) -> bool:
    return matches_retrieval_filters(
        obj,
        object_types=list(object_types),
        statuses=list(statuses),
        episode_id=episode_id,
        task_id=task_id,
    )

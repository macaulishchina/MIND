"""Append-only SQLite-backed memory storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

from mind.kernel.contracts import BudgetEvent, PrimitiveCallLog, RetrieveQueryMode
from mind.kernel.governance import ConcealmentRecord, GovernanceAuditRecord
from mind.kernel.provenance import DirectProvenanceRecord

from .retrieval import RetrievalMatch, latest_objects, matches_retrieval_filters, search_objects
from .schema import ensure_valid_object


class StoreError(RuntimeError):
    """Raised when a store operation cannot be completed safely."""


class MemoryStore(Protocol):
    """Minimal store contract shared by kernel and primitive code."""

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


@runtime_checkable
class UserStateStore(Protocol):
    """Optional store surface for product user/session state."""

    def insert_principal(self, principal: dict[str, Any]) -> dict[str, Any]: ...

    def read_principal(self, principal_id: str) -> dict[str, Any]: ...

    def list_principals(self, *, tenant_id: str | None = None) -> list[dict[str, Any]]: ...

    def insert_session(self, session: dict[str, Any]) -> dict[str, Any]: ...

    def read_session(self, session_id: str) -> dict[str, Any]: ...

    def update_session(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]: ...

    def list_sessions(self, *, principal_id: str | None = None) -> list[dict[str, Any]]: ...

    def insert_namespace(self, namespace: dict[str, Any]) -> dict[str, Any]: ...

    def read_namespace(self, namespace_id: str) -> dict[str, Any]: ...


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


from .sqlite_impl import _SQLiteImplMixin  # noqa: E402
from .sqlite_user_ops import _SQLiteUserOpsMixin  # noqa: E402


class SQLiteMemoryStore(_SQLiteImplMixin, _SQLiteUserOpsMixin):
    """A minimal append-only memory store."""

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



class _SQLiteStoreTransaction:
    """Explicit transaction wrapper used by write paths."""

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





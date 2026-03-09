"""Append-only SQLite-backed memory storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

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
            if _matches_retrieval_filters(
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
        return search_objects(
            self.iter_objects(),
            query=query,
            query_modes=list(query_modes),
            max_candidates=max_candidates,
            object_types=list(object_types),
            statuses=list(statuses),
            episode_id=episode_id,
            task_id=task_id,
            query_embedding=query_embedding,
        )

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        records = [
            obj
            for obj in self.iter_objects()
            if obj["type"] == "RawRecord" and obj["metadata"]["episode_id"] == episode_id
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

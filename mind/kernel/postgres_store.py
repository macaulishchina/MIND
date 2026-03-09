"""PostgreSQL-backed MemoryStore implementation and migration helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import Connection, RootTransaction, RowMapping
from sqlalchemy.engine.url import URL, make_url

from alembic import command
from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog

from .schema import ensure_valid_object
from .sql_tables import (
    budget_events_table,
    object_versions_table,
    primitive_call_logs_table,
)
from .store import MemoryStoreFactory, PrimitiveTransactionContextManager, StoreError


class PostgresMemoryStore:
    """Append-only PostgreSQL memory store built on SQLAlchemy Core."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.engine = sa.create_engine(dsn)
        self._transaction_open = False

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> PostgresMemoryStore:
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
        return _PostgresStoreTransaction(self)

    def has_object(self, object_id: str) -> bool:
        with self.engine.connect() as connection:
            return self._has_object(connection, object_id)

    def versions_for_object(self, object_id: str) -> list[int]:
        with self.engine.connect() as connection:
            return self._versions_for_object(connection, object_id)

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        with self.engine.connect() as connection:
            return self._read_object(connection, object_id, version)

    def iter_objects(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(object_versions_table).order_by(
                    object_versions_table.c.inserted_at.asc(),
                    object_versions_table.c.object_id.asc(),
                    object_versions_table.c.version.asc(),
                )
            ).mappings()
            return [self._decode_object_row(row) for row in rows]

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        episode_expr = object_versions_table.c.metadata_json.op("->>")("episode_id")
        timestamp_order_expr = sa.cast(
            object_versions_table.c.metadata_json.op("->>")("timestamp_order"),
            sa.Integer(),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(object_versions_table)
                .where(object_versions_table.c.type == "RawRecord")
                .where(episode_expr == episode_id)
                .order_by(timestamp_order_expr.asc(), object_versions_table.c.object_id.asc())
            ).mappings()
            return [self._decode_object_row(row) for row in rows]

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_primitive_call(log)

    def iter_primitive_call_logs(self) -> list[PrimitiveCallLog]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(primitive_call_logs_table).order_by(
                    primitive_call_logs_table.c.timestamp.asc(),
                    primitive_call_logs_table.c.call_id.asc(),
                )
            ).mappings()
            return [self._decode_primitive_call_log(row) for row in rows]

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_budget_event(event)

    def iter_budget_events(self) -> list[BudgetEvent]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(budget_events_table).order_by(
                    budget_events_table.c.timestamp.asc(),
                    budget_events_table.c.event_id.asc(),
                )
            ).mappings()
            return [self._decode_budget_event(row) for row in rows]

    def _begin_transaction(self) -> tuple[Connection, RootTransaction]:
        if self._transaction_open:
            raise StoreError("nested primitive transactions are not supported")
        connection = self.engine.connect()
        transaction = connection.begin()
        self._transaction_open = True
        return connection, transaction

    def _commit_transaction(
        self,
        connection: Connection,
        transaction: RootTransaction,
    ) -> None:
        if not self._transaction_open:
            raise StoreError("no active transaction to commit")
        transaction.commit()
        connection.close()
        self._transaction_open = False

    def _rollback_transaction(
        self,
        connection: Connection | None,
        transaction: RootTransaction | None,
    ) -> None:
        try:
            if transaction is not None:
                transaction.rollback()
        finally:
            if connection is not None:
                connection.close()
        self._transaction_open = False

    def _validate_and_insert(self, connection: Connection, obj: dict[str, Any]) -> None:
        object_id = obj["id"]
        version = obj["version"]
        existing_versions = self._versions_for_object(connection, object_id)

        if version == 1 and existing_versions:
            raise StoreError(f"object '{object_id}' version 1 already exists")
        if version > 1 and not existing_versions:
            raise StoreError(f"object '{object_id}' version {version} missing prior versions")
        if version > 1 and version != max(existing_versions) + 1:
            raise StoreError(f"object '{object_id}' version chain must be contiguous")

        if version > 1:
            previous = self._read_object(connection, object_id, max(existing_versions))
            if previous["type"] != obj["type"]:
                raise StoreError(
                    f"object '{object_id}' type changed from "
                    f"'{previous['type']}' to '{obj['type']}' across versions"
                )

        missing_refs = [ref for ref in obj["source_refs"] if not self._has_object(connection, ref)]
        if missing_refs:
            raise StoreError(f"object '{object_id}' has dangling source refs: {missing_refs}")

        try:
            connection.execute(
                sa.insert(object_versions_table).values(
                    object_id=object_id,
                    version=version,
                    type=obj["type"],
                    content_json=obj["content"],
                    source_refs_json=obj["source_refs"],
                    created_at=obj["created_at"],
                    updated_at=obj["updated_at"],
                    status=obj["status"],
                    priority=float(obj["priority"]),
                    metadata_json=obj["metadata"],
                )
            )
        except sa.exc.IntegrityError as exc:
            raise StoreError(str(exc.orig)) from exc

    def _has_object(self, connection: Connection, object_id: str) -> bool:
        row = connection.execute(
            sa.select(object_versions_table.c.object_id)
            .where(object_versions_table.c.object_id == object_id)
            .limit(1)
        ).first()
        return row is not None

    def _versions_for_object(self, connection: Connection, object_id: str) -> list[int]:
        rows = connection.execute(
            sa.select(object_versions_table.c.version)
            .where(object_versions_table.c.object_id == object_id)
            .order_by(object_versions_table.c.version.asc())
        )
        return [int(row.version) for row in rows]

    def _read_object(
        self,
        connection: Connection,
        object_id: str,
        version: int | None = None,
    ) -> dict[str, Any]:
        statement = sa.select(object_versions_table).where(
            object_versions_table.c.object_id == object_id
        )
        if version is None:
            statement = statement.order_by(object_versions_table.c.version.desc()).limit(1)
        else:
            statement = statement.where(object_versions_table.c.version == version)

        row = connection.execute(statement).mappings().first()
        if row is None:
            raise StoreError(f"object '{object_id}' not found")
        return self._decode_object_row(row)

    def _write_primitive_call(
        self,
        connection: Connection,
        log: PrimitiveCallLog | dict[str, Any],
    ) -> None:
        validated = PrimitiveCallLog.model_validate(log)
        connection.execute(
            sa.insert(primitive_call_logs_table).values(
                call_id=validated.call_id,
                primitive=validated.primitive.value,
                actor=validated.actor,
                timestamp=validated.timestamp.isoformat(),
                target_ids_json=validated.target_ids,
                cost_json=[item.model_dump(mode="json") for item in validated.cost],
                outcome=validated.outcome.value,
                request_json=validated.request,
                response_json=validated.response,
                error_json=(
                    validated.error.model_dump(mode="json")
                    if validated.error is not None
                    else None
                ),
            )
        )

    def _write_budget_event(
        self,
        connection: Connection,
        event: BudgetEvent | dict[str, Any],
    ) -> None:
        validated = BudgetEvent.model_validate(event)
        connection.execute(
            sa.insert(budget_events_table).values(
                event_id=validated.event_id,
                call_id=validated.call_id,
                scope_id=validated.scope_id,
                primitive=validated.primitive.value,
                actor=validated.actor,
                timestamp=validated.timestamp.isoformat(),
                outcome=validated.outcome.value,
                cost_json=[item.model_dump(mode="json") for item in validated.cost],
                metadata_json=validated.metadata,
            )
        )

    @staticmethod
    def _decode_object_row(row: RowMapping) -> dict[str, Any]:
        return {
            "id": row["object_id"],
            "type": row["type"],
            "content": row["content_json"],
            "source_refs": row["source_refs_json"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": int(row["version"]),
            "status": row["status"],
            "priority": float(row["priority"]),
            "metadata": row["metadata_json"],
        }

    @staticmethod
    def _decode_primitive_call_log(row: RowMapping) -> PrimitiveCallLog:
        payload: dict[str, Any] = {
            "call_id": row["call_id"],
            "primitive": row["primitive"],
            "actor": row["actor"],
            "timestamp": row["timestamp"],
            "target_ids": row["target_ids_json"],
            "cost": row["cost_json"],
            "outcome": row["outcome"],
            "request": row["request_json"],
            "response": row["response_json"],
            "error": row["error_json"],
        }
        return PrimitiveCallLog.model_validate(payload)

    @staticmethod
    def _decode_budget_event(row: RowMapping) -> BudgetEvent:
        payload: dict[str, Any] = {
            "event_id": row["event_id"],
            "call_id": row["call_id"],
            "scope_id": row["scope_id"],
            "primitive": row["primitive"],
            "actor": row["actor"],
            "timestamp": row["timestamp"],
            "outcome": row["outcome"],
            "cost": row["cost_json"],
            "metadata": row["metadata_json"],
        }
        return BudgetEvent.model_validate(payload)


class _PostgresStoreTransaction:
    """Explicit transaction wrapper used by PostgreSQL write paths."""

    def __init__(self, store: PostgresMemoryStore) -> None:
        self._store = store
        self._connection: Connection | None = None
        self._transaction: RootTransaction | None = None

    def __enter__(self) -> _PostgresStoreTransaction:
        self._connection, self._transaction = self._store._begin_transaction()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            assert self._connection is not None
            assert self._transaction is not None
            try:
                self._store._commit_transaction(self._connection, self._transaction)
            except Exception:
                self._store._rollback_transaction(self._connection, self._transaction)
                raise
            finally:
                self._connection = None
                self._transaction = None
            return

        self._store._rollback_transaction(self._connection, self._transaction)
        self._connection = None
        self._transaction = None

    def insert_object(self, obj: dict[str, Any]) -> None:
        ensure_valid_object(obj)
        self._store._validate_and_insert(self._require_connection(), obj)

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None:
        obj_list = list(objects)
        for obj in obj_list:
            ensure_valid_object(obj)
        connection = self._require_connection()
        for obj in obj_list:
            self._store._validate_and_insert(connection, obj)

    def has_object(self, object_id: str) -> bool:
        return self._store._has_object(self._require_connection(), object_id)

    def versions_for_object(self, object_id: str) -> list[int]:
        return self._store._versions_for_object(self._require_connection(), object_id)

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        return self._store._read_object(self._require_connection(), object_id, version)

    def iter_objects(self) -> list[dict[str, Any]]:
        rows = self._require_connection().execute(
            sa.select(object_versions_table).order_by(
                object_versions_table.c.inserted_at.asc(),
                object_versions_table.c.object_id.asc(),
                object_versions_table.c.version.asc(),
            )
        ).mappings()
        return [self._store._decode_object_row(row) for row in rows]

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        episode_expr = object_versions_table.c.metadata_json.op("->>")("episode_id")
        timestamp_order_expr = sa.cast(
            object_versions_table.c.metadata_json.op("->>")("timestamp_order"),
            sa.Integer(),
        )
        rows = self._require_connection().execute(
            sa.select(object_versions_table)
            .where(object_versions_table.c.type == "RawRecord")
            .where(episode_expr == episode_id)
            .order_by(timestamp_order_expr.asc(), object_versions_table.c.object_id.asc())
        ).mappings()
        return [self._store._decode_object_row(row) for row in rows]

    def record_primitive_call(self, log: PrimitiveCallLog | dict[str, Any]) -> None:
        self._store._write_primitive_call(self._require_connection(), log)

    def record_budget_event(self, event: BudgetEvent | dict[str, Any]) -> None:
        self._store._write_budget_event(self._require_connection(), event)

    def _require_connection(self) -> Connection:
        if self._connection is None:
            raise StoreError("no active PostgreSQL transaction")
        return self._connection


def build_postgres_store_factory(dsn: str) -> MemoryStoreFactory:
    """Return a gate-compatible store factory bound to a PostgreSQL DSN."""

    def factory(_: Path) -> PostgresMemoryStore:
        return PostgresMemoryStore(dsn)

    return factory


def run_postgres_migrations(dsn: str, revision: str = "head") -> None:
    """Apply Alembic migrations to the target PostgreSQL database."""

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", dsn)
    config.set_main_option("script_location", str(repo_root / "alembic"))
    command.upgrade(config, revision)


@contextmanager
def temporary_postgres_database(
    base_dsn: str,
    prefix: str = "mind_regression",
) -> Iterator[str]:
    """Create and clean up a throwaway PostgreSQL database."""

    base_url = make_url(base_dsn)
    admin_url = _admin_url_for(base_url)
    temp_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    temp_url = base_url.set(database=temp_name)
    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        with admin_engine.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{temp_name}"'))
        yield temp_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.execute(
                sa.text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name
                      AND pid <> pg_backend_pid()
                    """
                ),
                {"database_name": temp_name},
            )
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{temp_name}"'))
        admin_engine.dispose()


def _admin_url_for(base_url: URL) -> URL:
    if base_url.database == "postgres":
        return base_url
    return base_url.set(database="postgres")

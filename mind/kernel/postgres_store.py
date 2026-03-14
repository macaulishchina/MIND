"""PostgreSQL-backed MemoryStore implementation and migration helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RootTransaction
from sqlalchemy.engine.url import URL, make_url

from alembic import command
from alembic.config import Config
from mind.kernel.contracts import BudgetEvent, PrimitiveCallLog, RetrieveQueryMode
from mind.kernel.governance import ConcealmentRecord, GovernanceAuditRecord
from mind.kernel.provenance import DirectProvenanceRecord

from .postgres_impl import _PostgresImplMixin  # noqa: E402
from .postgres_user_ops import _PostgresUserOpsMixin  # noqa: E402
from .retrieval import RetrievalMatch, build_object_embedding, build_search_text
from .schema import ensure_valid_object
from .sql_tables import (
    budget_events_table,
    concealed_objects_table,
    governance_audit_table,
    object_embeddings_table,
    object_versions_table,
    primitive_call_logs_table,
    provenance_ledger_table,
)
from .store import MemoryStoreFactory, PrimitiveTransactionContextManager, StoreError


class PostgresMemoryStore(_PostgresImplMixin, _PostgresUserOpsMixin):
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

    def iter_latest_objects(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                self._latest_objects_statement(
                    object_types=object_types,
                    statuses=statuses,
                    episode_id=episode_id,
                    task_id=task_id,
                )
            ).mappings()
            return [self._decode_object_row(row) for row in rows]

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
        with self.engine.connect() as connection:
            return self._search_latest_objects(
                connection,
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
        episode_expr = object_versions_table.c.metadata_json.op("->>")("episode_id")
        timestamp_order_expr = sa.cast(
            object_versions_table.c.metadata_json.op("->>")("timestamp_order"),
            sa.Integer(),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(object_versions_table)
                .outerjoin(
                    concealed_objects_table,
                    concealed_objects_table.c.object_id == object_versions_table.c.object_id,
                )
                .where(object_versions_table.c.type == "RawRecord")
                .where(episode_expr == episode_id)
                .where(concealed_objects_table.c.object_id.is_(None))
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

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        with self.transaction() as transaction:
            transaction.insert_direct_provenance(record)

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord:
        with self.engine.connect() as connection:
            return self._read_direct_provenance(connection, provenance_id)

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord:
        with self.engine.connect() as connection:
            return self._direct_provenance_for_object(connection, object_id)

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(provenance_ledger_table).order_by(
                    provenance_ledger_table.c.ingested_at.asc(),
                    provenance_ledger_table.c.provenance_id.asc(),
                )
            ).mappings()
            return [self._decode_direct_provenance_row(row) for row in rows]

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        with self.transaction() as transaction:
            transaction.record_governance_audit(record)

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord:
        with self.engine.connect() as connection:
            return self._read_governance_audit(connection, audit_id)

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(governance_audit_table).order_by(
                    governance_audit_table.c.timestamp.asc(),
                    governance_audit_table.c.audit_id.asc(),
                )
            ).mappings()
            return [self._decode_governance_audit_row(row) for row in rows]

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(governance_audit_table)
                .where(governance_audit_table.c.operation_id == operation_id)
                .order_by(
                    governance_audit_table.c.timestamp.asc(),
                    governance_audit_table.c.audit_id.asc(),
                )
            ).mappings()
            return [self._decode_governance_audit_row(row) for row in rows]

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None:
        with self.transaction() as transaction:
            transaction.record_concealment(record)

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord:
        with self.engine.connect() as connection:
            return self._read_concealment(connection, concealment_id)

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord:
        with self.engine.connect() as connection:
            return self._concealment_for_object(connection, object_id)

    def is_object_concealed(self, object_id: str) -> bool:
        with self.engine.connect() as connection:
            row = connection.execute(
                sa.select(concealed_objects_table.c.concealment_id)
                .where(concealed_objects_table.c.object_id == object_id)
                .limit(1)
            ).first()
        return row is not None

    def iter_concealments(self) -> list[ConcealmentRecord]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                sa.select(concealed_objects_table).order_by(
                    concealed_objects_table.c.concealed_at.asc(),
                    concealed_objects_table.c.concealment_id.asc(),
                )
            ).mappings()
            return [self._decode_concealment_row(row) for row in rows]


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
        rows = (
            self._require_connection()
            .execute(
                sa.select(object_versions_table).order_by(
                    object_versions_table.c.inserted_at.asc(),
                    object_versions_table.c.object_id.asc(),
                    object_versions_table.c.version.asc(),
                )
            )
            .mappings()
        )
        return [self._store._decode_object_row(row) for row in rows]

    def insert_direct_provenance(
        self,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        self._store._write_direct_provenance(self._require_connection(), record)

    def read_direct_provenance(self, provenance_id: str) -> DirectProvenanceRecord:
        return self._store._read_direct_provenance(self._require_connection(), provenance_id)

    def direct_provenance_for_object(self, object_id: str) -> DirectProvenanceRecord:
        return self._store._direct_provenance_for_object(self._require_connection(), object_id)

    def iter_direct_provenance(self) -> list[DirectProvenanceRecord]:
        rows = (
            self._require_connection()
            .execute(
                sa.select(provenance_ledger_table).order_by(
                    provenance_ledger_table.c.ingested_at.asc(),
                    provenance_ledger_table.c.provenance_id.asc(),
                )
            )
            .mappings()
        )
        return [self._store._decode_direct_provenance_row(row) for row in rows]

    def record_governance_audit(
        self,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        self._store._write_governance_audit(self._require_connection(), record)

    def read_governance_audit(self, audit_id: str) -> GovernanceAuditRecord:
        return self._store._read_governance_audit(self._require_connection(), audit_id)

    def iter_governance_audit(self) -> list[GovernanceAuditRecord]:
        rows = (
            self._require_connection()
            .execute(
                sa.select(governance_audit_table).order_by(
                    governance_audit_table.c.timestamp.asc(),
                    governance_audit_table.c.audit_id.asc(),
                )
            )
            .mappings()
        )
        return [self._store._decode_governance_audit_row(row) for row in rows]

    def iter_governance_audit_for_operation(
        self,
        operation_id: str,
    ) -> list[GovernanceAuditRecord]:
        rows = (
            self._require_connection()
            .execute(
                sa.select(governance_audit_table)
                .where(governance_audit_table.c.operation_id == operation_id)
                .order_by(
                    governance_audit_table.c.timestamp.asc(),
                    governance_audit_table.c.audit_id.asc(),
                )
            )
            .mappings()
        )
        return [self._store._decode_governance_audit_row(row) for row in rows]

    def record_concealment(self, record: ConcealmentRecord | dict[str, Any]) -> None:
        self._store._write_concealment(self._require_connection(), record)

    def read_concealment(self, concealment_id: str) -> ConcealmentRecord:
        return self._store._read_concealment(self._require_connection(), concealment_id)

    def concealment_for_object(self, object_id: str) -> ConcealmentRecord:
        return self._store._concealment_for_object(self._require_connection(), object_id)

    def is_object_concealed(self, object_id: str) -> bool:
        row = (
            self._require_connection()
            .execute(
                sa.select(concealed_objects_table.c.concealment_id)
                .where(concealed_objects_table.c.object_id == object_id)
                .limit(1)
            )
            .first()
        )
        return row is not None

    def iter_concealments(self) -> list[ConcealmentRecord]:
        rows = (
            self._require_connection()
            .execute(
                sa.select(concealed_objects_table).order_by(
                    concealed_objects_table.c.concealed_at.asc(),
                    concealed_objects_table.c.concealment_id.asc(),
                )
            )
            .mappings()
        )
        return [self._store._decode_concealment_row(row) for row in rows]

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        episode_expr = object_versions_table.c.metadata_json.op("->>")("episode_id")
        timestamp_order_expr = sa.cast(
            object_versions_table.c.metadata_json.op("->>")("timestamp_order"),
            sa.Integer(),
        )
        rows = (
            self._require_connection()
            .execute(
                sa.select(object_versions_table)
                .where(object_versions_table.c.type == "RawRecord")
                .where(episode_expr == episode_id)
                .order_by(timestamp_order_expr.asc(), object_versions_table.c.object_id.asc())
            )
            .mappings()
        )
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
    _backfill_retrieval_artifacts(dsn)


def _backfill_retrieval_artifacts(dsn: str) -> None:
    engine = sa.create_engine(dsn)
    try:
        with engine.begin() as connection:
            rows = connection.execute(
                sa.select(object_versions_table).order_by(
                    object_versions_table.c.object_id.asc(),
                    object_versions_table.c.version.asc(),
                )
            ).mappings()
            for row in rows:
                obj = PostgresMemoryStore._decode_object_row(row)
                search_text = build_search_text(obj)
                connection.execute(
                    sa.update(object_versions_table)
                    .where(object_versions_table.c.object_id == obj["id"])
                    .where(object_versions_table.c.version == obj["version"])
                    .values(search_text=search_text)
                )
                embedding_exists = connection.execute(
                    sa.select(object_embeddings_table.c.object_id)
                    .where(object_embeddings_table.c.object_id == obj["id"])
                    .where(object_embeddings_table.c.version == obj["version"])
                    .limit(1)
                ).first()
                if embedding_exists is None:
                    connection.execute(
                        sa.insert(object_embeddings_table).values(
                            object_id=obj["id"],
                            version=obj["version"],
                            embedding_model="mind.local-hash.v1",
                            embedding=build_object_embedding(obj),
                        )
                    )
    finally:
        engine.dispose()


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



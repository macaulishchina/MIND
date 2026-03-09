"""PostgreSQL-backed MemoryStore implementation and migration helpers."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RootTransaction, RowMapping
from sqlalchemy.engine.url import URL, make_url

from alembic import command
from alembic.config import Config
from mind.offline.jobs import OfflineJob, OfflineJobKind, OfflineJobStatus
from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog, RetrieveQueryMode

from .pgvector import Vector
from .retrieval import EMBEDDING_DIM, RetrievalMatch, build_object_embedding, build_search_text
from .schema import ensure_valid_object
from .sql_tables import (
    budget_events_table,
    object_embeddings_table,
    object_versions_table,
    offline_jobs_table,
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

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        with self.engine.begin() as connection:
            connection.execute(
                sa.insert(offline_jobs_table).values(
                    job_id=validated.job_id,
                    job_kind=validated.job_kind.value,
                    status=validated.status.value,
                    payload_json=validated.payload,
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
                    search_text=build_search_text(obj),
                )
            )
            connection.execute(
                sa.insert(object_embeddings_table).values(
                    object_id=object_id,
                    version=version,
                    embedding_model="mind.local-hash.v1",
                    embedding=build_object_embedding(obj),
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

    @staticmethod
    def _decode_offline_job(row: RowMapping) -> OfflineJob:
        payload: dict[str, Any] = {
            "job_id": row["job_id"],
            "job_kind": row["job_kind"],
            "status": row["status"],
            "payload": row["payload_json"],
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

    def _latest_objects_statement(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> sa.Select[tuple[Any]]:
        latest_objects = self._latest_objects_subquery(
            object_types=object_types,
            statuses=statuses,
            episode_id=episode_id,
            task_id=task_id,
        )
        return sa.select(latest_objects).order_by(
            latest_objects.c.updated_at.desc(),
            latest_objects.c.object_id.asc(),
        )

    def _latest_objects_subquery(
        self,
        *,
        object_types: Iterable[str] = (),
        statuses: Iterable[str] = (),
        episode_id: str | None = None,
        task_id: str | None = None,
    ) -> sa.Subquery:
        latest_versions = (
            sa.select(
                object_versions_table.c.object_id.label("object_id"),
                sa.func.max(object_versions_table.c.version).label("version"),
            )
            .group_by(object_versions_table.c.object_id)
            .subquery()
        )

        statement = (
            sa.select(object_versions_table)
            .join(
                latest_versions,
                sa.and_(
                    object_versions_table.c.object_id == latest_versions.c.object_id,
                    object_versions_table.c.version == latest_versions.c.version,
                ),
            )
        )

        status_list = list(statuses)
        if status_list:
            statement = statement.where(object_versions_table.c.status.in_(status_list))
        else:
            statement = statement.where(object_versions_table.c.status != "invalid")

        type_list = list(object_types)
        if type_list:
            statement = statement.where(object_versions_table.c.type.in_(type_list))

        if task_id is not None:
            task_expr = object_versions_table.c.metadata_json.op("->>")("task_id")
            statement = statement.where(task_expr == task_id)

        if episode_id is not None:
            episode_expr = object_versions_table.c.metadata_json.op("->>")("episode_id")
            statement = statement.where(
                sa.or_(
                    episode_expr == episode_id,
                    object_versions_table.c.object_id == episode_id,
                    object_versions_table.c.source_refs_json.contains([episode_id]),
                )
            )

        return statement.subquery()

    def _search_latest_objects(
        self,
        connection: Connection,
        *,
        query: str | dict[str, Any],
        query_modes: list[RetrieveQueryMode],
        max_candidates: int,
        object_types: list[str],
        statuses: list[str],
        episode_id: str | None,
        task_id: str | None,
        query_embedding: tuple[float, ...] | None,
    ) -> list[RetrievalMatch]:
        latest_objects = self._latest_objects_subquery(
            object_types=object_types,
            statuses=statuses,
            episode_id=episode_id,
            task_id=task_id,
        )
        from_clause: sa.FromClause = latest_objects
        score_terms: list[sa.ColumnElement[float]] = []

        if RetrieveQueryMode.KEYWORD in query_modes:
            if isinstance(query, str):
                keyword_value = query.lower()
            else:
                keyword_value = json.dumps(query, ensure_ascii=True, sort_keys=True).lower()
            similarity = sa.func.similarity(
                latest_objects.c.search_text,
                sa.bindparam("keyword_query", value=keyword_value, type_=sa.Text()),
            )
            exact_phrase_boost = sa.case(
                (
                    latest_objects.c.search_text.like(
                        sa.bindparam(
                            "keyword_pattern",
                            value=_like_pattern(keyword_value),
                            type_=sa.Text(),
                        ),
                        escape="\\",
                    ),
                    1.0,
                ),
                else_=0.0,
            )
            score_terms.append(exact_phrase_boost + sa.func.greatest(similarity, 0.0))

        if RetrieveQueryMode.TIME_WINDOW in query_modes and isinstance(query, dict):
            created_at = sa.cast(latest_objects.c.created_at, sa.DateTime(timezone=True))
            conditions: list[sa.ColumnElement[bool]] = []
            if query.get("start") is not None:
                conditions.append(
                    created_at
                    >= sa.bindparam(
                        "window_start",
                        value=datetime.fromisoformat(str(query["start"])),
                        type_=sa.DateTime(timezone=True),
                    )
                )
            if query.get("end") is not None:
                conditions.append(
                    created_at
                    <= sa.bindparam(
                        "window_end",
                        value=datetime.fromisoformat(str(query["end"])),
                        type_=sa.DateTime(timezone=True),
                    )
                )
            if conditions:
                score_terms.append(sa.case((sa.and_(*conditions), 1.0), else_=0.0))

        if RetrieveQueryMode.VECTOR in query_modes:
            if query_embedding is None:
                raise StoreError("vector query embedding required for vector retrieval")
            from_clause = latest_objects.outerjoin(
                object_embeddings_table,
                sa.and_(
                    latest_objects.c.object_id == object_embeddings_table.c.object_id,
                    latest_objects.c.version == object_embeddings_table.c.version,
                ),
            )
            vector_distance = object_embeddings_table.c.embedding.op("<=>")(
                sa.bindparam(
                    "query_embedding",
                    value=query_embedding,
                    type_=Vector(EMBEDDING_DIM),
                )
            )
            vector_similarity = sa.func.greatest(
                0.0,
                1.0 - sa.type_coerce(vector_distance, sa.Float()),
            )
            score_terms.append(
                sa.case(
                    (object_embeddings_table.c.embedding.is_not(None), vector_similarity),
                    else_=0.0,
                )
            )

        if not score_terms:
            return []

        total_score = score_terms[0]
        for term in score_terms[1:]:
            total_score = total_score + term

        rows = connection.execute(
            sa.select(latest_objects, total_score.label("retrieval_score"))
            .select_from(from_clause)
            .where(total_score > 0)
            .order_by(
                total_score.desc(),
                latest_objects.c.updated_at.desc(),
                latest_objects.c.object_id.asc(),
            )
            .limit(max_candidates)
        ).mappings()
        return [
            RetrievalMatch(
                object=self._decode_object_row(row),
                score=round(float(row["retrieval_score"]), 6),
            )
            for row in rows
        ]


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


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

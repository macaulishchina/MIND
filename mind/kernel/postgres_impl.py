"""PostgreSQL internal write, decode, and search operations."""

# mypy: disable-error-code="attr-defined,has-type"
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, RootTransaction, RowMapping

from mind.kernel.contracts import BudgetEvent, PrimitiveCallLog, RetrieveQueryMode
from mind.kernel.governance import ConcealmentRecord, GovernanceAuditRecord
from mind.kernel.provenance import DirectProvenanceRecord

from .pgvector import Vector
from .retrieval import EMBEDDING_DIM, RetrievalMatch, build_object_embedding, build_search_text
from .sql_tables import (
    budget_events_table,
    concealed_objects_table,
    governance_audit_table,
    object_embeddings_table,
    object_versions_table,
    primitive_call_logs_table,
    provenance_ledger_table,
)
from .store import StoreError


class _PostgresImplMixin:
    """Internal write, decode, and search mixin for PostgresMemoryStore."""

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
                    validated.error.model_dump(mode="json") if validated.error is not None else None
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

    def _write_direct_provenance(
        self,
        connection: Connection,
        record: DirectProvenanceRecord | dict[str, Any],
    ) -> None:
        validated = DirectProvenanceRecord.model_validate(record)
        existing_row = connection.execute(
            sa.select(provenance_ledger_table.c.provenance_id)
            .where(provenance_ledger_table.c.bound_object_id == validated.bound_object_id)
            .limit(1)
        ).first()
        if existing_row is not None:
            raise StoreError(
                f"direct provenance already exists for object '{validated.bound_object_id}'"
            )

        try:
            bound_object = self._read_object(connection, validated.bound_object_id)
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
        connection.execute(sa.insert(provenance_ledger_table).values(**payload))

    def _write_governance_audit(
        self,
        connection: Connection,
        record: GovernanceAuditRecord | dict[str, Any],
    ) -> None:
        validated = GovernanceAuditRecord.model_validate(record)
        payload = validated.model_dump(mode="json")
        connection.execute(
            sa.insert(governance_audit_table).values(
                audit_id=payload["audit_id"],
                operation_id=payload["operation_id"],
                action=payload["action"],
                stage=payload["stage"],
                actor=payload["actor"],
                capability=payload["capability"],
                timestamp=payload["timestamp"],
                outcome=payload["outcome"],
                scope=payload.get("scope"),
                reason=payload.get("reason"),
                target_object_ids_json=payload["target_object_ids"],
                target_provenance_ids_json=payload["target_provenance_ids"],
                selection_json=payload["selection"],
                summary_json=payload["summary"],
            )
        )

    def _write_concealment(
        self,
        connection: Connection,
        record: ConcealmentRecord | dict[str, Any],
    ) -> None:
        validated = ConcealmentRecord.model_validate(record)
        if not self._has_object(connection, validated.object_id):
            raise StoreError(f"cannot conceal missing object '{validated.object_id}'")
        connection.execute(
            sa.insert(concealed_objects_table).values(
                concealment_id=validated.concealment_id,
                operation_id=validated.operation_id,
                object_id=validated.object_id,
                actor=validated.actor,
                concealed_at=validated.concealed_at.isoformat(),
                reason=validated.reason,
            )
        )

    def _read_direct_provenance(
        self,
        connection: Connection,
        provenance_id: str,
    ) -> DirectProvenanceRecord:
        row = (
            connection.execute(
                sa.select(provenance_ledger_table)
                .where(provenance_ledger_table.c.provenance_id == provenance_id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StoreError(f"direct provenance '{provenance_id}' not found")
        return self._decode_direct_provenance_row(row)

    def _read_governance_audit(
        self,
        connection: Connection,
        audit_id: str,
    ) -> GovernanceAuditRecord:
        row = (
            connection.execute(
                sa.select(governance_audit_table)
                .where(governance_audit_table.c.audit_id == audit_id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StoreError(f"governance audit '{audit_id}' not found")
        return self._decode_governance_audit_row(row)

    def _read_concealment(
        self,
        connection: Connection,
        concealment_id: str,
    ) -> ConcealmentRecord:
        row = (
            connection.execute(
                sa.select(concealed_objects_table)
                .where(concealed_objects_table.c.concealment_id == concealment_id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StoreError(f"concealment '{concealment_id}' not found")
        return self._decode_concealment_row(row)

    def _direct_provenance_for_object(
        self,
        connection: Connection,
        object_id: str,
    ) -> DirectProvenanceRecord:
        row = (
            connection.execute(
                sa.select(provenance_ledger_table)
                .where(provenance_ledger_table.c.bound_object_id == object_id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StoreError(f"direct provenance for object '{object_id}' not found")
        return self._decode_direct_provenance_row(row)

    def _concealment_for_object(
        self,
        connection: Connection,
        object_id: str,
    ) -> ConcealmentRecord:
        row = (
            connection.execute(
                sa.select(concealed_objects_table)
                .where(concealed_objects_table.c.object_id == object_id)
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise StoreError(f"concealment for object '{object_id}' not found")
        return self._decode_concealment_row(row)

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
    def _decode_direct_provenance_row(row: RowMapping) -> DirectProvenanceRecord:
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
    def _decode_governance_audit_row(row: RowMapping) -> GovernanceAuditRecord:
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
            "target_object_ids": row["target_object_ids_json"],
            "target_provenance_ids": row["target_provenance_ids_json"],
            "selection": row["selection_json"],
            "summary": row["summary_json"],
        }
        return GovernanceAuditRecord.model_validate(payload)

    @staticmethod
    def _decode_concealment_row(row: RowMapping) -> ConcealmentRecord:
        payload: dict[str, Any] = {
            "concealment_id": row["concealment_id"],
            "operation_id": row["operation_id"],
            "object_id": row["object_id"],
            "actor": row["actor"],
            "concealed_at": row["concealed_at"],
            "reason": row["reason"],
        }
        return ConcealmentRecord.model_validate(payload)


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

        statement = sa.select(object_versions_table).join(
            latest_versions,
            sa.and_(
                object_versions_table.c.object_id == latest_versions.c.object_id,
                object_versions_table.c.version == latest_versions.c.version,
            ),
        )
        statement = statement.outerjoin(
            concealed_objects_table,
            concealed_objects_table.c.object_id == object_versions_table.c.object_id,
        ).where(concealed_objects_table.c.object_id.is_(None))

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
            keyword_variants = _keyword_query_variants(query)
            similarity_terms = [
                sa.func.greatest(
                    sa.func.similarity(
                        latest_objects.c.search_text,
                        sa.bindparam(
                            f"keyword_query_{index}",
                            value=keyword_value,
                            type_=sa.Text(),
                        ),
                    ),
                    0.0,
                )
                for index, keyword_value in enumerate(keyword_variants)
            ]
            exact_phrase_terms = [
                sa.case(
                    (
                        latest_objects.c.search_text.like(
                            sa.bindparam(
                                f"keyword_pattern_{index}",
                                value=_like_pattern(keyword_value),
                                type_=sa.Text(),
                            ),
                            escape="\\",
                        ),
                        1.0,
                    ),
                    else_=0.0,
                )
                for index, keyword_value in enumerate(keyword_variants)
            ]
            similarity = (
                sa.func.greatest(*similarity_terms)
                if len(similarity_terms) > 1
                else similarity_terms[0]
            )
            exact_phrase_boost = (
                sa.func.greatest(*exact_phrase_terms)
                if len(exact_phrase_terms) > 1
                else exact_phrase_terms[0]
            )
            score_terms.append(exact_phrase_boost + similarity)

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



def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _keyword_query_variants(query: str | dict[str, Any]) -> list[str]:
    if isinstance(query, str):
        raw = query.lower()
    else:
        raw = json.dumps(query, ensure_ascii=False, sort_keys=True).lower()
    ascii_escaped = json.dumps(query, ensure_ascii=True, sort_keys=True).lower()
    if isinstance(query, str):
        ascii_escaped = ascii_escaped.strip('"')
    variants: list[str] = []
    for candidate in (raw, ascii_escaped):
        candidate = candidate.strip()
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants

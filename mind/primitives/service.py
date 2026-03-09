"""Phase C primitive service object implementations."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mind.kernel.store import MemoryStore, PrimitiveTransaction, StoreError

from .contracts import (
    BudgetCost,
    BudgetEvent,
    LinkRequest,
    LinkResponse,
    MemoryObject,
    PrimitiveCostCategory,
    PrimitiveError,
    PrimitiveErrorCode,
    PrimitiveExecutionContext,
    PrimitiveExecutionResult,
    PrimitiveName,
    PrimitiveOutcome,
    ReadRequest,
    ReadResponse,
    ReflectRequest,
    ReflectResponse,
    ReorganizeOperation,
    ReorganizeSimpleRequest,
    ReorganizeSimpleResponse,
    RetrieveQueryMode,
    RetrieveRequest,
    RetrieveResponse,
    SummarizeRequest,
    SummarizeResponse,
    WriteRawRequest,
    WriteRawResponse,
)
from .runtime import PrimitiveHandlerResult, PrimitiveRejectedError, PrimitiveRuntime

SummaryScope = {"episode", "task", "object_set"}
InaccessibleStatuses = {"invalid"}
PositiveReasonHints = ("boost", "increase", "raise", "up", "urgent")
type VectorRetriever = Callable[[str | dict[str, Any], list[dict[str, Any]]], dict[str, float]]


class PrimitiveService:
    """Library-first Phase C primitive surface."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        vector_retriever: VectorRetriever | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._runtime = PrimitiveRuntime(store, clock=self._clock)
        self._vector_retriever = vector_retriever

    def write_raw(
        self,
        request: WriteRawRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: WriteRawRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[WriteRawResponse]:
            return self._write_raw(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.WRITE_RAW,
            actor=execution_context.actor,
            request_model=WriteRawRequest,
            response_model=WriteRawResponse,
            request_payload=request,
            handler=handler,
        )

    def read(
        self,
        request: ReadRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: ReadRequest,
            store: MemoryStore,
        ) -> PrimitiveHandlerResult[ReadResponse]:
            return self._read(validated_request, execution_context, store)

        return self._runtime.execute_read(
            primitive=PrimitiveName.READ,
            actor=execution_context.actor,
            request_model=ReadRequest,
            response_model=ReadResponse,
            request_payload=request,
            handler=handler,
        )

    def retrieve(
        self,
        request: RetrieveRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: RetrieveRequest,
            store: MemoryStore,
        ) -> PrimitiveHandlerResult[RetrieveResponse]:
            return self._retrieve(validated_request, execution_context, store)

        return self._runtime.execute_read(
            primitive=PrimitiveName.RETRIEVE,
            actor=execution_context.actor,
            request_model=RetrieveRequest,
            response_model=RetrieveResponse,
            request_payload=request,
            handler=handler,
        )

    def summarize(
        self,
        request: SummarizeRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: SummarizeRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[SummarizeResponse]:
            return self._summarize(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.SUMMARIZE,
            actor=execution_context.actor,
            request_model=SummarizeRequest,
            response_model=SummarizeResponse,
            request_payload=request,
            handler=handler,
        )

    def link(
        self,
        request: LinkRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: LinkRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[LinkResponse]:
            return self._link(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.LINK,
            actor=execution_context.actor,
            request_model=LinkRequest,
            response_model=LinkResponse,
            request_payload=request,
            handler=handler,
        )

    def reflect(
        self,
        request: ReflectRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: ReflectRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[ReflectResponse]:
            return self._reflect(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.REFLECT,
            actor=execution_context.actor,
            request_model=ReflectRequest,
            response_model=ReflectResponse,
            request_payload=request,
            handler=handler,
        )

    def reorganize_simple(
        self,
        request: ReorganizeSimpleRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: ReorganizeSimpleRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[ReorganizeSimpleResponse]:
            return self._reorganize_simple(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.REORGANIZE_SIMPLE,
            actor=execution_context.actor,
            request_model=ReorganizeSimpleRequest,
            response_model=ReorganizeSimpleResponse,
            request_payload=request,
            handler=handler,
        )

    def _write_raw(
        self,
        request: WriteRawRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[WriteRawResponse]:
        costs = [
            BudgetCost(category=PrimitiveCostCategory.WRITE, amount=1.0),
            BudgetCost(category=PrimitiveCostCategory.STORAGE, amount=0.25),
        ]
        self._enforce_budget(context, costs)

        created_at = self._clock().isoformat()
        object_id = self._new_object_id(f"raw-{request.episode_id}")
        raw_object: dict[str, Any] = {
            "id": object_id,
            "type": "RawRecord",
            "content": request.content,
            "source_refs": [],
            "created_at": created_at,
            "updated_at": created_at,
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "record_kind": request.record_kind,
                "episode_id": request.episode_id,
                "timestamp_order": request.timestamp_order,
            },
        }
        transaction.insert_object(raw_object)
        return PrimitiveHandlerResult(
            response=WriteRawResponse(object_id=object_id, version=1),
            target_ids=(object_id,),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.WRITE_RAW,
                    costs=costs,
                    metadata={"episode_id": request.episode_id},
                ),
            ),
        )

    def _read(
        self,
        request: ReadRequest,
        context: PrimitiveExecutionContext,
        store: MemoryStore,
    ) -> PrimitiveHandlerResult[ReadResponse]:
        costs = [
            BudgetCost(
                category=PrimitiveCostCategory.READ,
                amount=float(len(request.object_ids)),
            )
        ]
        self._enforce_budget(context, costs)

        objects: list[MemoryObject] = []
        for object_id in request.object_ids:
            try:
                obj = store.read_object(object_id)
            except StoreError as exc:
                raise self._reject(
                    PrimitiveErrorCode.OBJECT_NOT_FOUND,
                    f"object '{object_id}' not found",
                    details={"object_id": object_id},
                ) from exc

            if obj["status"] in InaccessibleStatuses:
                raise self._reject(
                    PrimitiveErrorCode.OBJECT_INACCESSIBLE,
                    f"object '{object_id}' is inaccessible",
                    details={"object_id": object_id, "status": obj["status"]},
                )
            objects.append(MemoryObject.model_validate(obj))

        return PrimitiveHandlerResult(
            response=ReadResponse(objects=objects),
            target_ids=tuple(request.object_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.READ,
                    costs=costs,
                    metadata={"object_count": len(request.object_ids)},
                ),
            ),
        )

    def _retrieve(
        self,
        request: RetrieveRequest,
        context: PrimitiveExecutionContext,
        store: MemoryStore,
    ) -> PrimitiveHandlerResult[RetrieveResponse]:
        latest_objects = self._latest_objects(store.iter_objects())
        filtered_objects = [
            obj
            for obj in latest_objects
            if self._matches_filters(obj, request.filters.model_dump())
        ]

        if RetrieveQueryMode.VECTOR in request.query_modes and self._vector_retriever is None:
            raise self._reject(
                PrimitiveErrorCode.RETRIEVAL_BACKEND_UNAVAILABLE,
                "vector retrieval backend unavailable",
            )

        scores: list[tuple[dict[str, Any], float]] = []
        vector_scores = (
            self._vector_retriever(request.query, filtered_objects)
            if (
                RetrieveQueryMode.VECTOR in request.query_modes
                and self._vector_retriever is not None
            )
            else {}
        )
        for obj in filtered_objects:
            score = 0.0
            if RetrieveQueryMode.KEYWORD in request.query_modes:
                score += self._keyword_score(request.query, obj)
            if RetrieveQueryMode.TIME_WINDOW in request.query_modes:
                score += self._time_window_score(request.query, obj)
            if RetrieveQueryMode.VECTOR in request.query_modes:
                score += vector_scores.get(obj["id"], 0.0)
            if score > 0:
                scores.append((obj, score))

        scores.sort(key=lambda item: (item[1], item[0]["updated_at"]), reverse=True)
        max_candidates = request.budget.max_candidates or len(scores)
        selected = scores[:max_candidates]
        retrieval_cost = [
            BudgetCost(
                category=PrimitiveCostCategory.RETRIEVAL,
                amount=max(0.5, 0.1 * float(len(filtered_objects) or 1)),
            )
        ]
        self._enforce_budget(context, retrieval_cost, request.budget.max_cost)

        candidate_ids = [item[0]["id"] for item in selected]
        candidate_scores = [round(item[1], 4) for item in selected]
        evidence_summary = {
            "matched_modes": [mode.value for mode in request.query_modes],
            "filtered_count": len(filtered_objects),
            "returned_count": len(candidate_ids),
        }
        return PrimitiveHandlerResult(
            response=RetrieveResponse(
                candidate_ids=candidate_ids,
                scores=candidate_scores,
                evidence_summary=evidence_summary,
            ),
            target_ids=tuple(candidate_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.RETRIEVE,
                    costs=retrieval_cost,
                    metadata=evidence_summary,
                ),
            ),
        )

    def _summarize(
        self,
        request: SummarizeRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[SummarizeResponse]:
        if request.summary_scope not in SummaryScope:
            raise self._reject(
                PrimitiveErrorCode.UNSUPPORTED_SCOPE,
                f"unsupported summary_scope '{request.summary_scope}'",
                details={"summary_scope": request.summary_scope},
            )

        source_objects = self._read_existing_objects(request.input_refs, transaction)
        combined_text = " ".join(self._object_text(obj) for obj in source_objects)
        summary_text = self._summarize_text(combined_text)
        costs = [
            BudgetCost(category=PrimitiveCostCategory.GENERATION, amount=2.0),
            BudgetCost(category=PrimitiveCostCategory.MAINTENANCE, amount=0.5),
        ]
        self._enforce_budget(context, costs)

        created_at = self._clock().isoformat()
        summary_object_id = self._new_object_id("summary")
        summary_object = {
            "id": summary_object_id,
            "type": "SummaryNote",
            "content": {
                "summary": summary_text,
                "target_kind": request.target_kind,
            },
            "source_refs": list(request.input_refs),
            "created_at": created_at,
            "updated_at": created_at,
            "version": 1,
            "status": "active",
            "priority": 0.6,
            "metadata": {
                "summary_scope": request.summary_scope,
                "input_refs": list(request.input_refs),
                "compression_ratio_estimate": self._compression_ratio(summary_text, combined_text),
                "target_kind": request.target_kind,
            },
        }
        try:
            transaction.insert_object(summary_object)
        except Exception as exc:
            raise self._reject(
                PrimitiveErrorCode.SUMMARY_VALIDATION_FAILED,
                "summary validation failed",
                details={"input_refs": list(request.input_refs)},
            ) from exc

        return PrimitiveHandlerResult(
            response=SummarizeResponse(summary_object_id=summary_object_id),
            target_ids=(summary_object_id,),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.SUMMARIZE,
                    costs=costs,
                    metadata={"input_count": len(request.input_refs)},
                ),
            ),
        )

    def _link(
        self,
        request: LinkRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[LinkResponse]:
        if request.src_id == request.dst_id:
            raise self._reject(
                PrimitiveErrorCode.SELF_LINK_NOT_ALLOWED,
                "self-link not allowed",
                details={"src_id": request.src_id, "dst_id": request.dst_id},
            )

        self._ensure_refs_exist([request.src_id, request.dst_id], transaction)
        self._ensure_refs_exist(
            request.evidence_refs,
            transaction,
            error_code=PrimitiveErrorCode.EVIDENCE_MISSING,
        )

        costs = [BudgetCost(category=PrimitiveCostCategory.WRITE, amount=1.0)]
        self._enforce_budget(context, costs)

        created_at = self._clock().isoformat()
        link_object_id = self._new_object_id("link")
        link_object = {
            "id": link_object_id,
            "type": "LinkEdge",
            "content": {
                "src_id": request.src_id,
                "dst_id": request.dst_id,
                "relation_type": request.relation_type,
            },
            "source_refs": list(request.evidence_refs),
            "created_at": created_at,
            "updated_at": created_at,
            "version": 1,
            "status": "active",
            "priority": 0.55,
            "metadata": {
                "confidence": min(1.0, 0.5 + 0.1 * len(request.evidence_refs)),
                "evidence_refs": list(request.evidence_refs),
            },
        }
        transaction.insert_object(link_object)

        return PrimitiveHandlerResult(
            response=LinkResponse(link_object_id=link_object_id),
            target_ids=(request.src_id, request.dst_id, link_object_id),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.LINK,
                    costs=costs,
                    metadata={"relation_type": request.relation_type},
                ),
            ),
        )

    def _reflect(
        self,
        request: ReflectRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[ReflectResponse]:
        try:
            episode_object = transaction.read_object(request.episode_id)
        except StoreError as exc:
            raise self._reject(
                PrimitiveErrorCode.EPISODE_MISSING,
                f"episode '{request.episode_id}' not found",
                details={"episode_id": request.episode_id},
            ) from exc

        raw_records = transaction.raw_records_for_episode(request.episode_id)
        if len(raw_records) < 2:
            raise self._reject(
                PrimitiveErrorCode.INSUFFICIENT_EVIDENCE,
                "insufficient evidence for reflection",
                details={"episode_id": request.episode_id, "record_count": len(raw_records)},
            )

        costs = [BudgetCost(category=PrimitiveCostCategory.GENERATION, amount=2.0)]
        self._enforce_budget(context, costs)

        created_at = self._clock().isoformat()
        reflection_object_id = self._new_object_id("reflection")
        success = bool(episode_object.get("metadata", {}).get("success"))
        reflection_object = {
            "id": reflection_object_id,
            "type": "ReflectionNote",
            "content": {
                "summary": self._reflection_summary(request.focus, success),
            },
            "source_refs": [request.episode_id] + [record["id"] for record in raw_records[-2:]],
            "created_at": created_at,
            "updated_at": created_at,
            "version": 1,
            "status": "active",
            "priority": 0.7,
            "metadata": {
                "episode_id": request.episode_id,
                "reflection_kind": "success" if success else "failure",
                "claims": self._reflection_claims(request.focus, raw_records, success),
            },
        }
        try:
            transaction.insert_object(reflection_object)
        except Exception as exc:
            raise self._reject(
                PrimitiveErrorCode.REFLECTION_VALIDATION_FAILED,
                "reflection validation failed",
                details={"episode_id": request.episode_id},
            ) from exc

        return PrimitiveHandlerResult(
            response=ReflectResponse(reflection_object_id=reflection_object_id),
            target_ids=(request.episode_id, reflection_object_id),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.REFLECT,
                    costs=costs,
                    metadata={"episode_id": request.episode_id},
                ),
            ),
        )

    def _reorganize_simple(
        self,
        request: ReorganizeSimpleRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[ReorganizeSimpleResponse]:
        target_objects = self._read_existing_objects(request.target_refs, transaction)
        costs = [
            BudgetCost(
                category=PrimitiveCostCategory.MAINTENANCE,
                amount=max(1.0, 0.5 * float(len(request.target_refs))),
            )
        ]
        self._enforce_budget(context, costs)

        updated_ids: list[str] = []
        new_object_ids: list[str] = []

        if request.operation is ReorganizeOperation.SYNTHESIZE_SCHEMA:
            schema_object_id = self._new_object_id("schema")
            created_at = self._clock().isoformat()
            schema_object = {
                "id": schema_object_id,
                "type": "SchemaNote",
                "content": {"rule": request.reason},
                "source_refs": list(request.target_refs),
                "created_at": created_at,
                "updated_at": created_at,
                "version": 1,
                "status": "active",
                "priority": 0.65,
                "metadata": {
                    "kind": "semantic",
                    "evidence_refs": list(request.target_refs),
                    "stability_score": 0.5,
                    "promotion_source_refs": list(request.target_refs),
                },
            }
            transaction.insert_object(schema_object)
            new_object_ids.append(schema_object_id)
        else:
            for target_object in target_objects:
                next_version = self._reorganized_version(target_object, request)
                transaction.insert_object(next_version)
                updated_ids.append(target_object["id"])

        return PrimitiveHandlerResult(
            response=ReorganizeSimpleResponse(
                updated_ids=updated_ids,
                new_object_ids=new_object_ids,
            ),
            target_ids=tuple(updated_ids + new_object_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.REORGANIZE_SIMPLE,
                    costs=costs,
                    metadata={"operation": request.operation.value},
                ),
            ),
        )

    def _read_existing_objects(
        self,
        object_ids: Iterable[str],
        store: PrimitiveTransaction | MemoryStore,
    ) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        for object_id in object_ids:
            try:
                obj = store.read_object(object_id)
            except StoreError as exc:
                raise self._reject(
                    PrimitiveErrorCode.INVALID_REFS,
                    "invalid target refs",
                    details={"object_id": object_id},
                ) from exc
            objects.append(obj)
        return objects

    def _ensure_refs_exist(
        self,
        refs: Iterable[str],
        store: PrimitiveTransaction | MemoryStore,
        *,
        error_code: PrimitiveErrorCode = PrimitiveErrorCode.INVALID_REFS,
    ) -> None:
        for ref in refs:
            if not store.has_object(ref):
                raise self._reject(
                    error_code,
                    "missing required refs",
                    details={"ref": ref},
                )

    def _reorganized_version(
        self,
        target_object: dict[str, Any],
        request: ReorganizeSimpleRequest,
    ) -> dict[str, Any]:
        next_object = copy.deepcopy(target_object)
        next_object["version"] = int(target_object["version"]) + 1
        next_object["updated_at"] = self._clock().isoformat()
        metadata = dict(next_object["metadata"])
        metadata["reorganize_reason"] = request.reason
        metadata["reorganize_operation"] = request.operation.value
        next_object["metadata"] = metadata

        if request.operation is ReorganizeOperation.ARCHIVE:
            if target_object["status"] != "active":
                raise self._reject(
                    PrimitiveErrorCode.UNSAFE_STATE_TRANSITION,
                    "archive only allowed from active state",
                    details={"object_id": target_object["id"], "status": target_object["status"]},
                )
            next_object["status"] = "archived"
            return next_object

        if request.operation is ReorganizeOperation.DEPRECATE:
            if target_object["status"] not in {"active", "archived"}:
                raise self._reject(
                    PrimitiveErrorCode.UNSAFE_STATE_TRANSITION,
                    "deprecate only allowed from active or archived state",
                    details={"object_id": target_object["id"], "status": target_object["status"]},
                )
            next_object["status"] = "deprecated"
            return next_object

        if request.operation is ReorganizeOperation.REPRIORITIZE:
            if target_object["status"] in InaccessibleStatuses:
                raise self._reject(
                    PrimitiveErrorCode.UNSAFE_STATE_TRANSITION,
                    "reprioritize not allowed for inaccessible objects",
                    details={"object_id": target_object["id"], "status": target_object["status"]},
                )
            next_object["priority"] = self._reprioritized_value(
                float(target_object["priority"]),
                request.reason,
            )
            return next_object

        raise self._reject(
            PrimitiveErrorCode.UNSUPPORTED_OPERATION,
            f"unsupported operation '{request.operation.value}'",
            details={"operation": request.operation.value},
        )

    def _enforce_budget(
        self,
        context: PrimitiveExecutionContext,
        costs: list[BudgetCost],
        request_limit: float | None = None,
    ) -> None:
        limit = _effective_budget_limit(context.budget_limit, request_limit)
        if limit is None:
            return

        spent = sum(
            cost.amount
            for event in self.store.iter_budget_events()
            if (
                event.scope_id == context.budget_scope_id
                and event.outcome is PrimitiveOutcome.SUCCESS
            )
            for cost in event.cost
        )
        projected = spent + sum(cost.amount for cost in costs)
        if projected > limit:
            raise self._reject(
                PrimitiveErrorCode.BUDGET_EXHAUSTED,
                f"budget exhausted for scope '{context.budget_scope_id}'",
                details={
                    "scope_id": context.budget_scope_id,
                    "spent": round(spent, 4),
                    "projected": round(projected, 4),
                    "limit": round(limit, 4),
                },
            )

    def _budget_event(
        self,
        *,
        context: PrimitiveExecutionContext,
        primitive: PrimitiveName,
        costs: list[BudgetCost],
        metadata: dict[str, Any] | None = None,
    ) -> BudgetEvent:
        return BudgetEvent(
            event_id=self._new_object_id(f"budget-{primitive.value}"),
            call_id="pending",
            scope_id=context.budget_scope_id,
            primitive=primitive,
            actor=context.actor,
            timestamp=self._clock(),
            outcome=PrimitiveOutcome.SUCCESS,
            cost=costs,
            metadata=metadata or {},
        )

    @staticmethod
    def _latest_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest_by_id: dict[str, dict[str, Any]] = {}
        for obj in objects:
            existing = latest_by_id.get(obj["id"])
            if existing is None or int(obj["version"]) > int(existing["version"]):
                latest_by_id[obj["id"]] = obj
        return list(latest_by_id.values())

    @staticmethod
    def _matches_filters(obj: dict[str, Any], filters: dict[str, Any]) -> bool:
        statuses: list[str] = filters.get("statuses", [])
        if statuses:
            if obj["status"] not in statuses:
                return False
        elif obj["status"] in InaccessibleStatuses:
            return False

        object_types: list[str] = filters.get("object_types", [])
        if object_types and obj["type"] not in object_types:
            return False

        episode_id = filters.get("episode_id")
        if episode_id is not None and not PrimitiveService._matches_episode(obj, episode_id):
            return False

        task_id = filters.get("task_id")
        if task_id is not None and obj.get("metadata", {}).get("task_id") != task_id:
            return False

        return True

    @staticmethod
    def _matches_episode(obj: dict[str, Any], episode_id: str) -> bool:
        metadata = obj.get("metadata", {})
        if metadata.get("episode_id") == episode_id:
            return True
        if obj["id"] == episode_id:
            return True
        return episode_id in obj.get("source_refs", [])

    @staticmethod
    def _keyword_score(query: str | dict[str, Any], obj: dict[str, Any]) -> float:
        query_text = PrimitiveService._query_text(query)
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return 0.0
        object_tokens = _tokenize(PrimitiveService._object_text(obj))
        overlap = len(query_tokens & object_tokens)
        if overlap == 0:
            return 0.0
        return overlap / float(len(query_tokens))

    @staticmethod
    def _time_window_score(query: str | dict[str, Any], obj: dict[str, Any]) -> float:
        if not isinstance(query, dict):
            return 0.0
        start = query.get("start")
        end = query.get("end")
        if start is None and end is None:
            return 0.0
        try:
            created_at = _parse_iso_datetime(obj["created_at"])
        except ValueError:
            return 0.0
        if start is not None and created_at < _parse_iso_datetime(start):
            return 0.0
        if end is not None and created_at > _parse_iso_datetime(end):
            return 0.0
        return 1.0

    @staticmethod
    def _query_text(query: str | dict[str, Any]) -> str:
        return (
            query
            if isinstance(query, str)
            else json.dumps(query, ensure_ascii=True, sort_keys=True)
        )

    @staticmethod
    def _object_text(obj: dict[str, Any]) -> str:
        return json.dumps(
            {
                "id": obj["id"],
                "type": obj["type"],
                "content": obj["content"],
                "metadata": obj["metadata"],
            },
            ensure_ascii=True,
            sort_keys=True,
        ).lower()

    @staticmethod
    def _summarize_text(text: str) -> str:
        if not text:
            return "No source material available."
        words = text.split()
        excerpt = " ".join(words[:24])
        return excerpt if excerpt else text[:160]

    @staticmethod
    def _compression_ratio(summary_text: str, source_text: str) -> float:
        source_length = max(len(source_text), 1)
        return round(min(1.0, len(summary_text) / source_length), 4)

    @staticmethod
    def _reflection_summary(focus: str | dict[str, Any], success: bool) -> str:
        focus_text = PrimitiveService._query_text(focus)
        prefix = "Episode succeeded" if success else "Episode failed"
        return f"{prefix}; reflection focus: {focus_text[:120]}"

    @staticmethod
    def _reflection_claims(
        focus: str | dict[str, Any],
        raw_records: list[dict[str, Any]],
        success: bool,
    ) -> list[str]:
        focus_text = PrimitiveService._query_text(focus)
        claims = ["success" if success else "failure", f"focus:{focus_text[:40]}"]
        claims.append(f"record_count:{len(raw_records)}")
        return claims

    @staticmethod
    def _reprioritized_value(current_priority: float, reason: str) -> float:
        lowered_reason = reason.lower()
        delta = 0.2 if any(hint in lowered_reason for hint in PositiveReasonHints) else -0.2
        return round(min(1.0, max(0.0, current_priority + delta)), 4)

    @staticmethod
    def _reject(
        code: PrimitiveErrorCode,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> PrimitiveRejectedError:
        return PrimitiveRejectedError(
            PrimitiveError(
                code=code,
                message=message,
                details=details or {},
            )
        )

    @staticmethod
    def _new_object_id(prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _effective_budget_limit(
    context_limit: float | None,
    request_limit: float | None,
) -> float | None:
    limits = [limit for limit in (context_limit, request_limit) if limit is not None]
    return min(limits) if limits else None


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)

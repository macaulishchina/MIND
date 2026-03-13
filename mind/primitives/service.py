"""Primitive service object implementations."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mind.capabilities import (
    CapabilityService,
    resolve_capability_provider_config,
)
from mind.capabilities import (
    ReflectRequest as CapabilityReflectRequest,
)
from mind.capabilities import (
    SummarizeRequest as CapabilitySummarizeRequest,
)
from mind.kernel.provenance import build_direct_provenance_record, build_provenance_summary
from mind.kernel.retrieval import (
    build_query_embedding,
    build_search_text,
    canonical_query_text,
    tokenize,
)
from mind.kernel.schema import public_object_view
from mind.kernel.store import MemoryStore, PrimitiveTransaction, StoreError
from mind.telemetry import TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .contracts import (
    BudgetCost,
    BudgetEvent,
    Capability,
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
    RecordFeedbackRequest,
    RecordFeedbackResponse,
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
from .runtime import (
    PrimitiveHandlerResult,
    PrimitiveRejectedError,
    PrimitiveRuntime,
    PrimitiveTelemetryEmission,
)

SummaryScope = {"episode", "task", "object_set"}
InaccessibleStatuses = {"invalid"}
PositiveReasonHints = ("boost", "increase", "raise", "up", "urgent")
type VectorRetriever = Callable[[str | dict[str, Any], list[dict[str, Any]]], dict[str, float]]
type QueryEmbedder = Callable[[str | dict[str, Any]], tuple[float, ...]]
type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


class PrimitiveService:
    """Library-first primitive surface."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        vector_retriever: VectorRetriever | None = None,
        query_embedder: QueryEmbedder | None = None,
        capability_service: CapabilityService | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
        provider_env_resolver: ProviderEnvResolver | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._runtime = PrimitiveRuntime(
            store,
            clock=self._clock,
            telemetry_recorder=telemetry_recorder,
        )
        self._vector_retriever = vector_retriever
        self._query_embedder = query_embedder
        self._capability_service = capability_service or CapabilityService(clock=self._clock)
        self._provider_env_resolver = provider_env_resolver

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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
            request_model=ReadRequest,
            response_model=ReadResponse,
            request_payload=request,
            handler=handler,
        )

    def read_with_provenance(
        self,
        request: ReadRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        payload = (
            request.model_dump(mode="json") if isinstance(request, ReadRequest) else dict(request)
        )
        payload["include_provenance"] = True
        return self.read(payload, context)

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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
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
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
            request_model=ReorganizeSimpleRequest,
            response_model=ReorganizeSimpleResponse,
            request_payload=request,
            handler=handler,
        )

    def record_feedback(
        self,
        request: RecordFeedbackRequest | dict[str, Any],
        context: PrimitiveExecutionContext | dict[str, Any],
    ) -> PrimitiveExecutionResult:
        execution_context = PrimitiveExecutionContext.model_validate(context)

        def handler(
            validated_request: RecordFeedbackRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[RecordFeedbackResponse]:
            return self._record_feedback(validated_request, execution_context, transaction)

        return self._runtime.execute_write(
            primitive=PrimitiveName.RECORD_FEEDBACK,
            actor=execution_context.actor,
            dev_mode=execution_context.dev_mode,
            telemetry_run_id=execution_context.telemetry_run_id,
            telemetry_operation_id=execution_context.telemetry_operation_id,
            telemetry_parent_event_id=execution_context.telemetry_parent_event_id,
            request_model=RecordFeedbackRequest,
            response_model=RecordFeedbackResponse,
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

        now = self._clock()
        created_at = now.isoformat()
        object_id = self._new_object_id(f"raw-{request.episode_id}")
        provenance_id = self._new_object_id(f"prov-{request.episode_id}")
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

        try:
            direct_provenance = build_direct_provenance_record(
                provenance_id=provenance_id,
                bound_object_id=object_id,
                bound_object_type="RawRecord",
                direct_provenance=request.direct_provenance,
                actor=context.actor,
                ingested_at=now,
                episode_id=request.episode_id,
            )
        except ValueError as exc:
            raise self._reject(
                PrimitiveErrorCode.SCHEMA_INVALID,
                str(exc),
                details={"episode_id": request.episode_id},
            ) from exc

        transaction.insert_object(raw_object)
        transaction.insert_direct_provenance(direct_provenance)
        self._after_write_operation(PrimitiveName.WRITE_RAW)
        return PrimitiveHandlerResult(
            response=WriteRawResponse(
                object_id=object_id,
                version=1,
                provenance_id=provenance_id,
            ),
            target_ids=(object_id,),
            mutated_ids=(object_id,),
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
        self._require_capability(
            context,
            Capability.MEMORY_READ,
            action="read memory objects",
        )
        if request.include_provenance:
            self._require_capability(
                context,
                Capability.MEMORY_READ_WITH_PROVENANCE,
                action="read provenance summaries",
            )

        costs = [
            BudgetCost(
                category=PrimitiveCostCategory.READ,
                amount=float(len(request.object_ids)),
            )
        ]
        self._enforce_budget(context, costs)

        objects: list[MemoryObject] = []
        provenance_summaries: dict[str, Any] = {}
        for object_id in request.object_ids:
            try:
                obj = store.read_object(object_id)
            except StoreError as exc:
                raise self._reject(
                    PrimitiveErrorCode.OBJECT_NOT_FOUND,
                    f"object '{object_id}' not found",
                    details={"object_id": object_id},
                ) from exc

            if self._is_object_concealed(store, object_id):
                raise self._reject(
                    PrimitiveErrorCode.OBJECT_INACCESSIBLE,
                    f"object '{object_id}' is concealed",
                    details={"object_id": object_id, "visibility": "concealed"},
                )
            if obj["status"] in InaccessibleStatuses:
                raise self._reject(
                    PrimitiveErrorCode.OBJECT_INACCESSIBLE,
                    f"object '{object_id}' is inaccessible",
                    details={"object_id": object_id, "status": obj["status"]},
                )
            objects.append(MemoryObject.model_validate(public_object_view(obj)))
            if request.include_provenance and obj["type"] in {"RawRecord", "ImportedRawRecord"}:
                try:
                    provenance_record = store.direct_provenance_for_object(object_id)
                except StoreError:
                    continue
                provenance_summaries[object_id] = build_provenance_summary(
                    provenance_record
                ).model_dump(mode="json")

        return PrimitiveHandlerResult(
            response=ReadResponse(
                objects=objects,
                provenance_summaries=provenance_summaries,
            ),
            target_ids=tuple(request.object_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.READ,
                    costs=costs,
                    metadata={
                        "object_count": len(request.object_ids),
                        "include_provenance": request.include_provenance,
                    },
                ),
            ),
        )

    def _retrieve(
        self,
        request: RetrieveRequest,
        context: PrimitiveExecutionContext,
        store: MemoryStore,
    ) -> PrimitiveHandlerResult[RetrieveResponse]:
        self._require_capability(
            context,
            Capability.MEMORY_READ,
            action="retrieve memory objects",
        )
        filtered_objects = store.iter_latest_objects(
            object_types=request.filters.object_types,
            statuses=request.filters.statuses,
            episode_id=request.filters.episode_id,
            task_id=request.filters.task_id,
        )

        if (
            RetrieveQueryMode.VECTOR in request.query_modes
            and self._vector_retriever is None
            and self._query_embedder is None
        ):
            raise self._reject(
                PrimitiveErrorCode.RETRIEVAL_BACKEND_UNAVAILABLE,
                "vector retrieval backend unavailable",
            )

        max_candidates = request.budget.max_candidates or max(len(filtered_objects), 1)
        if RetrieveQueryMode.VECTOR in request.query_modes and self._vector_retriever is not None:
            scores: list[tuple[dict[str, Any], float]] = []
            vector_scores = self._vector_retriever(request.query, filtered_objects)
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
            selected = scores[:max_candidates]
            candidate_ids = [item[0]["id"] for item in selected]
            candidate_scores = [round(item[1], 4) for item in selected]
            candidate_summaries = [
                self._object_summary(item[0], score=round(item[1], 4)) for item in selected
            ]
            retrieval_backend = "legacy_vector_override"
        else:
            query_embedding = (
                (self._query_embedder or build_query_embedding)(request.query)
                if RetrieveQueryMode.VECTOR in request.query_modes
                else None
            )
            matches = store.search_latest_objects(
                query=request.query,
                query_modes=request.query_modes,
                max_candidates=max_candidates,
                object_types=request.filters.object_types,
                statuses=request.filters.statuses,
                episode_id=request.filters.episode_id,
                task_id=request.filters.task_id,
                query_embedding=query_embedding,
            )
            candidate_ids = [match.object["id"] for match in matches]
            candidate_scores = [round(match.score, 4) for match in matches]
            candidate_summaries = [
                self._object_summary(match.object, score=round(match.score, 4))
                for match in matches
            ]
            retrieval_backend = "store_search"

        retrieval_cost = [
            BudgetCost(
                category=PrimitiveCostCategory.RETRIEVAL,
                amount=max(0.5, 0.1 * float(len(filtered_objects) or 1)),
            )
        ]
        self._enforce_budget(context, retrieval_cost, request.budget.max_cost)

        evidence_summary = {
            "matched_modes": [mode.value for mode in request.query_modes],
            "filtered_count": len(filtered_objects),
            "returned_count": len(candidate_ids),
            "retrieval_backend": retrieval_backend,
        }
        return PrimitiveHandlerResult(
            response=RetrieveResponse(
                candidate_ids=candidate_ids,
                scores=candidate_scores,
                candidate_summaries=candidate_summaries,
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
            telemetry_emissions=(
                PrimitiveTelemetryEmission(
                    scope=TelemetryScope.RETRIEVAL,
                    kind=TelemetryEventKind.ENTRY,
                    payload={
                        "query_modes": [mode.value for mode in request.query_modes],
                        "filters": request.filters.model_dump(mode="json"),
                        "budget": request.budget.model_dump(mode="json"),
                    },
                    debug_fields={
                        "max_candidates": max_candidates,
                        "filtered_count": len(filtered_objects),
                    },
                ),
                PrimitiveTelemetryEmission(
                    scope=TelemetryScope.RETRIEVAL,
                    kind=TelemetryEventKind.DECISION,
                    payload={
                        "retrieval_backend": retrieval_backend,
                        "candidate_ids": candidate_ids,
                        "candidate_scores": candidate_scores,
                    },
                    debug_fields={
                        "returned_count": len(candidate_ids),
                        "used_vector_override": retrieval_backend == "legacy_vector_override",
                    },
                ),
                PrimitiveTelemetryEmission(
                    scope=TelemetryScope.RETRIEVAL,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    payload={
                        "evidence_summary": evidence_summary,
                        "candidate_summaries": candidate_summaries,
                    },
                    debug_fields={
                        "top_candidate_id": candidate_ids[0] if candidate_ids else None,
                        "top_score": candidate_scores[0] if candidate_scores else None,
                    },
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
        provider_config = self._capability_provider_config(context)
        summary_text = self._capability_service.summarize(
            CapabilitySummarizeRequest(
                request_id=f"primitive-summarize-{uuid4().hex[:8]}",
                source_text=combined_text,
                source_refs=list(request.input_refs),
                instruction=f"summary_scope={request.summary_scope};target_kind={request.target_kind}",
            ),
            provider_config=provider_config,
        ).summary_text
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
        self._after_write_operation(PrimitiveName.SUMMARIZE)

        return PrimitiveHandlerResult(
            response=SummarizeResponse(summary_object_id=summary_object_id),
            target_ids=(summary_object_id,),
            mutated_ids=(summary_object_id,),
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
        self._after_write_operation(PrimitiveName.LINK)

        return PrimitiveHandlerResult(
            response=LinkResponse(link_object_id=link_object_id),
            target_ids=(request.src_id, request.dst_id, link_object_id),
            mutated_ids=(link_object_id,),
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
        source_refs = [request.episode_id] + [record["id"] for record in raw_records[-2:]]
        evidence_text = " ".join(self._object_text(record) for record in raw_records[-2:])
        provider_config = self._capability_provider_config(context)
        reflection_summary = self._capability_service.reflect(
            CapabilityReflectRequest(
                request_id=f"primitive-reflect-{uuid4().hex[:8]}",
                focus=request.focus,
                evidence_text=evidence_text,
                episode_id=request.episode_id,
                outcome_hint="success" if success else "failure",
                evidence_refs=source_refs,
            ),
            provider_config=provider_config,
        ).reflection_text
        reflection_object = {
            "id": reflection_object_id,
            "type": "ReflectionNote",
            "content": {
                "summary": reflection_summary,
            },
            "source_refs": source_refs,
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
        self._after_write_operation(PrimitiveName.REFLECT)

        return PrimitiveHandlerResult(
            response=ReflectResponse(reflection_object_id=reflection_object_id),
            target_ids=(request.episode_id, reflection_object_id),
            mutated_ids=(reflection_object_id,),
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
            supporting_episode_ids = self._supporting_episode_ids(target_objects)
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
                    "stability_score": self._schema_stability_score(
                        target_objects,
                        supporting_episode_ids,
                    ),
                    "promotion_source_refs": list(request.target_refs),
                    "supporting_episode_ids": supporting_episode_ids,
                },
            }
            transaction.insert_object(schema_object)
            new_object_ids.append(schema_object_id)
        else:
            for target_object in target_objects:
                next_version = self._reorganized_version(target_object, request)
                transaction.insert_object(next_version)
                updated_ids.append(target_object["id"])
        self._after_write_operation(PrimitiveName.REORGANIZE_SIMPLE)

        return PrimitiveHandlerResult(
            response=ReorganizeSimpleResponse(
                updated_ids=updated_ids,
                new_object_ids=new_object_ids,
            ),
            target_ids=tuple(updated_ids + new_object_ids),
            mutated_ids=tuple(updated_ids + new_object_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.REORGANIZE_SIMPLE,
                    costs=costs,
                    metadata={"operation": request.operation.value},
                ),
            ),
        )

    def _record_feedback(
        self,
        request: RecordFeedbackRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[RecordFeedbackResponse]:
        costs = [BudgetCost(category=PrimitiveCostCategory.WRITE, amount=0.5)]
        self._enforce_budget(context, costs)

        now = self._clock()
        created_at = now.isoformat()
        feedback_object_id = self._new_object_id(f"feedback-{request.episode_id}")
        query_text = self._query_text(request.query)
        feedback_object: dict[str, Any] = {
            "id": feedback_object_id,
            "type": "FeedbackRecord",
            "content": {"query": query_text},
            "source_refs": list(request.used_object_ids) if request.used_object_ids else [],
            "created_at": created_at,
            "updated_at": created_at,
            "version": 1,
            "status": "active",
            "priority": max(0.0, min(1.0, 0.5 + 0.25 * request.quality_signal)),
            "metadata": {
                "task_id": request.task_id,
                "episode_id": request.episode_id,
                "query": query_text,
                "used_object_ids": list(request.used_object_ids),
                "helpful_object_ids": list(request.helpful_object_ids),
                "unhelpful_object_ids": list(request.unhelpful_object_ids),
                "quality_signal": request.quality_signal,
                "cost": request.cost,
            },
        }
        transaction.insert_object(feedback_object)

        # Update dynamic signal counters on the referenced objects
        all_used = set(request.used_object_ids)
        helpful = set(request.helpful_object_ids)
        unhelpful = set(request.unhelpful_object_ids)
        mutated_ids = [feedback_object_id]

        for object_id in all_used:
            if not transaction.has_object(object_id):
                continue
            try:
                target_obj = transaction.read_object(object_id)
            except StoreError:
                continue
            updated_obj = self._apply_feedback_signals(
                target_obj,
                is_helpful=object_id in helpful,
                is_unhelpful=object_id in unhelpful,
                now_iso=created_at,
            )
            transaction.insert_object(updated_obj)
            mutated_ids.append(object_id)

        self._after_write_operation(PrimitiveName.RECORD_FEEDBACK)
        return PrimitiveHandlerResult(
            response=RecordFeedbackResponse(feedback_object_id=feedback_object_id),
            target_ids=tuple(mutated_ids),
            mutated_ids=tuple(mutated_ids),
            budget_events=(
                self._budget_event(
                    context=context,
                    primitive=PrimitiveName.RECORD_FEEDBACK,
                    costs=costs,
                    metadata={
                        "episode_id": request.episode_id,
                        "used_count": len(request.used_object_ids),
                        "helpful_count": len(request.helpful_object_ids),
                        "unhelpful_count": len(request.unhelpful_object_ids),
                    },
                ),
            ),
        )

    @staticmethod
    def _apply_feedback_signals(
        obj: dict[str, Any],
        *,
        is_helpful: bool,
        is_unhelpful: bool,
        now_iso: str,
    ) -> dict[str, Any]:
        """Return a new version of the object with updated dynamic signal metadata."""
        updated = copy.deepcopy(obj)
        updated["version"] = int(obj["version"]) + 1
        updated["updated_at"] = now_iso
        metadata = dict(updated.get("metadata", {}))
        metadata["access_count"] = int(metadata.get("access_count", 0)) + 1
        metadata["last_accessed_at"] = now_iso
        if is_helpful:
            metadata["feedback_positive_count"] = (
                int(metadata.get("feedback_positive_count", 0)) + 1
            )
        if is_unhelpful:
            metadata["feedback_negative_count"] = (
                int(metadata.get("feedback_negative_count", 0)) + 1
            )
        updated["metadata"] = metadata
        return updated

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
        return canonical_query_text(query)

    @staticmethod
    def _object_text(obj: dict[str, Any]) -> str:
        return build_search_text(obj)

    @staticmethod
    def _object_summary(obj: dict[str, Any], *, score: float | None = None) -> dict[str, Any]:
        metadata = obj.get("metadata", {})
        summary = {
            "object_id": obj.get("id"),
            "type": obj.get("type"),
            "status": obj.get("status"),
            "episode_id": metadata.get("episode_id"),
            "content_preview": PrimitiveService._preview_text(obj.get("content")),
        }
        if score is not None:
            summary["score"] = score
        return summary

    @staticmethod
    def _preview_text(content: Any) -> str | None:
        if content is None:
            return None
        if isinstance(content, str):
            text = " ".join(content.split())
            return text[:77] + "..." if len(text) > 80 else text
        if isinstance(content, dict):
            if isinstance(content.get("summary"), str):
                text = " ".join(content["summary"].split())
                return text[:77] + "..." if len(text) > 80 else text
            text = " ".join(json.dumps(content, ensure_ascii=True, sort_keys=True).split())
            return text[:77] + "..." if len(text) > 80 else text
        text = " ".join(str(content).split())
        return text[:77] + "..." if len(text) > 80 else text

    def _capability_provider_config(
        self,
        context: PrimitiveExecutionContext,
    ) -> Any:
        if not context.provider_selection:
            return None
        try:
            return resolve_capability_provider_config(
                selection=context.provider_selection,
                env=self._provider_env_resolver() if self._provider_env_resolver is not None else None,
            )
        except RuntimeError as exc:
            raise self._reject(
                PrimitiveErrorCode.UNSUPPORTED_OPERATION,
                str(exc),
                details={"provider_selection": dict(context.provider_selection)},
            ) from exc

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
    def _supporting_episode_ids(target_objects: list[dict[str, Any]]) -> list[str]:
        return sorted(
            {
                str(obj.get("metadata", {}).get("episode_id"))
                for obj in target_objects
                if obj.get("metadata", {}).get("episode_id")
            }
        )

    @staticmethod
    def _schema_stability_score(
        target_objects: list[dict[str, Any]],
        supporting_episode_ids: list[str],
    ) -> float:
        return round(
            min(
                0.95,
                0.45 + 0.10 * len(target_objects) + 0.10 * len(supporting_episode_ids),
            ),
            4,
        )

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

    @staticmethod
    def _require_capability(
        context: PrimitiveExecutionContext,
        capability: Capability,
        *,
        action: str,
    ) -> None:
        if capability in context.capabilities:
            return
        raise PrimitiveService._reject(
            PrimitiveErrorCode.CAPABILITY_REQUIRED,
            f"capability '{capability.value}' required to {action}",
            details={"required_capability": capability.value},
        )

    @staticmethod
    def _is_object_concealed(store: MemoryStore, object_id: str) -> bool:
        check = getattr(store, "is_object_concealed", None)
        if check is None:
            return False
        return bool(check(object_id))

    def _after_write_operation(self, primitive: PrimitiveName) -> None:
        """Optional hook for tests and gate fault injection."""


def _tokenize(text: str) -> set[str]:
    return tokenize(text)


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

"""Primitive service object implementations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mind.kernel.provenance import build_direct_provenance_record, build_provenance_summary
from mind.kernel.schema import public_object_view
from mind.kernel.store import MemoryStore, PrimitiveTransaction, StoreError
from mind.telemetry import TelemetryRecorder

from .contracts import (
    BudgetCost,
    Capability,
    CapabilityPort,
    LinkRequest,
    LinkResponse,
    MemoryObject,
    PrimitiveCostCategory,
    PrimitiveError,
    PrimitiveErrorCode,
    PrimitiveExecutionContext,
    PrimitiveExecutionResult,
    PrimitiveName,
    ReadRequest,
    ReadResponse,
    RecordFeedbackRequest,
    RecordFeedbackResponse,
    ReflectRequest,
    ReflectResponse,
    ReorganizeSimpleRequest,
    ReorganizeSimpleResponse,
    RetrieveRequest,
    RetrieveResponse,
    SummarizeRequest,
    SummarizeResponse,
    WriteRawRequest,
    WriteRawResponse,
)
from .ops_mixin import _PrimitiveOpsMixin
from .runtime import (
    PrimitiveHandlerResult,
    PrimitiveRejectedError,
    PrimitiveRuntime,
)

SummaryScope = {"episode", "task", "object_set"}
InaccessibleStatuses = {"invalid"}
PositiveReasonHints = ("boost", "increase", "raise", "up", "urgent")
type VectorRetriever = Callable[[str | dict[str, Any], list[dict[str, Any]]], dict[str, float]]
type QueryEmbedder = Callable[[str | dict[str, Any]], tuple[float, ...]]
type ProviderEnvResolver = Callable[[], Mapping[str, str] | None]


class PrimitiveService(_PrimitiveOpsMixin):
    """Library-first primitive surface."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
        vector_retriever: VectorRetriever | None = None,
        query_embedder: QueryEmbedder | None = None,
        capability_service: CapabilityPort | None = None,
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
        self._capability_service = capability_service
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

    def _require_capability_port(self) -> CapabilityPort:
        if self._capability_service is None:
            raise RuntimeError("No CapabilityPort configured on PrimitiveService")
        return self._capability_service

    def _capability_provider_config(
        self,
        context: PrimitiveExecutionContext,
    ) -> Any:
        if not context.provider_selection:
            return None
        try:
            return self._require_capability_port().resolve_provider_config(
                selection=context.provider_selection,
                env=self._provider_env_resolver()
                if self._provider_env_resolver is not None
                else None,
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


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)

"""Runtime helpers for primitive execution, logging, and rollback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter, ValidationError

from mind.kernel.store import MemoryStore, PrimitiveTransaction
from mind.telemetry import TelemetryEvent, TelemetryEventKind, TelemetryRecorder, TelemetryScope

from .contracts import (
    BudgetEvent,
    PrimitiveCallLog,
    PrimitiveError,
    PrimitiveErrorCode,
    PrimitiveExecutionResult,
    PrimitiveName,
    PrimitiveOutcome,
)

type ReadPrimitiveHandler[RequestModelT: BaseModel, ResponseModelT: BaseModel] = Callable[
    [RequestModelT, MemoryStore],
    PrimitiveHandlerResult[ResponseModelT],
]
type WritePrimitiveHandler[RequestModelT: BaseModel, ResponseModelT: BaseModel] = Callable[
    [RequestModelT, PrimitiveTransaction],
    PrimitiveHandlerResult[ResponseModelT],
]


@dataclass(frozen=True)
class PrimitiveHandlerResult[ResponseModelT: BaseModel]:
    """Normalized handler return value used by the runtime wrapper."""

    response: ResponseModelT
    target_ids: tuple[str, ...] = ()
    mutated_ids: tuple[str, ...] = ()
    budget_events: tuple[BudgetEvent, ...] = ()
    telemetry_emissions: tuple[PrimitiveTelemetryEmission, ...] = ()


@dataclass(frozen=True)
class PrimitiveTelemetryEmission:
    """Additional telemetry emitted by a primitive handler."""

    scope: TelemetryScope
    kind: TelemetryEventKind
    payload: dict[str, Any]
    debug_fields: dict[str, Any] = None  # type: ignore[assignment]
    workspace_id: str | None = None
    job_id: str | None = None
    parent_event_id: str | None = None

    def __post_init__(self) -> None:
        if self.debug_fields is None:
            object.__setattr__(self, "debug_fields", {})


class PrimitiveRejectedError(RuntimeError):
    """Signal an explicit primitive rejection without partial state changes."""

    def __init__(self, error: PrimitiveError) -> None:
        super().__init__(error.message)
        self.error = error


class PrimitiveRuntime:
    """Common execution wrapper for primitive service methods."""

    def __init__(
        self,
        store: MemoryStore,
        clock: Callable[[], datetime] | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now
        self._telemetry_recorder = telemetry_recorder

    def execute_read[RequestModelT: BaseModel, ResponseModelT: BaseModel](
        self,
        *,
        primitive: PrimitiveName,
        actor: str,
        dev_mode: bool = False,
        telemetry_run_id: str | None = None,
        telemetry_operation_id: str | None = None,
        telemetry_parent_event_id: str | None = None,
        request_model: type[RequestModelT],
        response_model: type[ResponseModelT],
        request_payload: RequestModelT | dict[str, Any],
        handler: ReadPrimitiveHandler[RequestModelT, ResponseModelT],
    ) -> PrimitiveExecutionResult:
        call_id = _new_call_id(primitive)
        timestamp = self._clock()
        operation_id = telemetry_operation_id or call_id
        run_id = telemetry_run_id or call_id
        request_data = _json_compatible_payload(request_payload)
        self._record_telemetry(
            enabled=dev_mode,
            event=self._primitive_event(
                event_id=f"{call_id}-entry",
                occurred_at=timestamp,
                run_id=run_id,
                operation_id=operation_id,
                actor=actor,
                primitive=primitive,
                kind=TelemetryEventKind.ENTRY,
                parent_event_id=telemetry_parent_event_id,
                payload={"request": request_data},
                debug_fields={"call_id": call_id},
            ),
        )
        try:
            request = request_model.model_validate(request_payload)
        except ValidationError as exc:
            failure_result, failure_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request_payload,
                error=_schema_error(exc),
                outcome=PrimitiveOutcome.FAILURE,
            )
            self.store.record_primitive_call(failure_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-result",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    payload={"outcome": failure_result.outcome.value, "request": request_data},
                    debug_fields={
                        "error_code": failure_result.error.code.value
                        if failure_result.error
                        else "unknown"
                    },
                ),
            )
            return failure_result

        try:
            result = handler(request, self.store)
            response = response_model.model_validate(result.response)
        except PrimitiveRejectedError as exc:
            rejection_result, rejection_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request,
                error=exc.error,
                outcome=PrimitiveOutcome.REJECTED,
            )
            self.store.record_primitive_call(rejection_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-decision",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.DECISION,
                    payload={
                        "outcome": rejection_result.outcome.value,
                        "request": request.model_dump(mode="json"),
                    },
                    debug_fields={"error_code": exc.error.code.value},
                ),
            )
            return rejection_result
        except Exception as exc:
            failure_result, failure_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request,
                error=_unexpected_error(exc),
                outcome=PrimitiveOutcome.FAILURE,
            )
            self.store.record_primitive_call(failure_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-result",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    payload={
                        "outcome": failure_result.outcome.value,
                        "request": request.model_dump(mode="json"),
                    },
                    debug_fields={
                        "error_code": failure_result.error.code.value
                        if failure_result.error
                        else "unknown"
                    },
                ),
            )
            return failure_result

        execution_result = PrimitiveExecutionResult(
            primitive=primitive,
            outcome=PrimitiveOutcome.SUCCESS,
            response=response.model_dump(mode="json"),
            target_ids=list(result.target_ids),
            cost=[cost for event in result.budget_events for cost in event.cost],
        )
        call_log = PrimitiveCallLog(
            call_id=call_id,
            primitive=primitive,
            actor=actor,
            timestamp=timestamp,
            target_ids=list(result.target_ids),
            cost=[cost for event in result.budget_events for cost in event.cost],
            outcome=PrimitiveOutcome.SUCCESS,
            request=request.model_dump(mode="json"),
            response=response.model_dump(mode="json"),
        )
        transaction_factory = getattr(self.store, "transaction", None)
        if callable(transaction_factory):
            # Keep read-side audit writes in a single transaction so read-heavy
            # benchmarks do not pay a separate commit for each log row.
            with transaction_factory() as transaction:
                transaction.record_primitive_call(call_log)
                for event in result.budget_events:
                    transaction.record_budget_event(event.model_copy(update={"call_id": call_id}))
        else:
            self.store.record_primitive_call(call_log)
            for event in result.budget_events:
                self.store.record_budget_event(event.model_copy(update={"call_id": call_id}))
        self._record_telemetry(
            enabled=dev_mode,
            event=self._primitive_event(
                event_id=f"{call_id}-result",
                occurred_at=timestamp,
                run_id=run_id,
                operation_id=operation_id,
                actor=actor,
                primitive=primitive,
                kind=TelemetryEventKind.ACTION_RESULT,
                payload={
                    "outcome": execution_result.outcome.value,
                    "request": request.model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                },
                debug_fields={
                    "target_ids": list(result.target_ids),
                    "budget_event_count": len(result.budget_events),
                },
            ),
        )
        self._record_emissions(
            enabled=dev_mode,
            call_id=call_id,
            occurred_at=timestamp,
            run_id=run_id,
            operation_id=operation_id,
            actor=actor,
            emissions=result.telemetry_emissions,
        )
        return execution_result

    def execute_write[RequestModelT: BaseModel, ResponseModelT: BaseModel](
        self,
        *,
        primitive: PrimitiveName,
        actor: str,
        dev_mode: bool = False,
        telemetry_run_id: str | None = None,
        telemetry_operation_id: str | None = None,
        telemetry_parent_event_id: str | None = None,
        request_model: type[RequestModelT],
        response_model: type[ResponseModelT],
        request_payload: RequestModelT | dict[str, Any],
        handler: WritePrimitiveHandler[RequestModelT, ResponseModelT],
    ) -> PrimitiveExecutionResult:
        call_id = _new_call_id(primitive)
        timestamp = self._clock()
        operation_id = telemetry_operation_id or call_id
        run_id = telemetry_run_id or call_id
        request_data = _json_compatible_payload(request_payload)
        self._record_telemetry(
            enabled=dev_mode,
            event=self._primitive_event(
                event_id=f"{call_id}-entry",
                occurred_at=timestamp,
                run_id=run_id,
                operation_id=operation_id,
                actor=actor,
                primitive=primitive,
                kind=TelemetryEventKind.ENTRY,
                parent_event_id=telemetry_parent_event_id,
                payload={"request": request_data},
                debug_fields={"call_id": call_id},
            ),
        )
        try:
            request = request_model.model_validate(request_payload)
        except ValidationError as exc:
            failure_result, failure_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request_payload,
                error=_schema_error(exc),
                outcome=PrimitiveOutcome.FAILURE,
            )
            self.store.record_primitive_call(failure_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-result",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    payload={"outcome": failure_result.outcome.value, "request": request_data},
                    debug_fields={
                        "error_code": failure_result.error.code.value
                        if failure_result.error
                        else "unknown"
                    },
                ),
            )
            return failure_result

        try:
            execution_result: PrimitiveExecutionResult | None = None
            success_response: ResponseModelT | None = None
            success_result: PrimitiveHandlerResult[ResponseModelT] | None = None
            with self.store.transaction() as transaction:
                result = handler(request, transaction)
                response = response_model.model_validate(result.response)
                execution_result = PrimitiveExecutionResult(
                    primitive=primitive,
                    outcome=PrimitiveOutcome.SUCCESS,
                    response=response.model_dump(mode="json"),
                    target_ids=list(result.target_ids),
                    cost=[cost for event in result.budget_events for cost in event.cost],
                )
                transaction.record_primitive_call(
                    PrimitiveCallLog(
                        call_id=call_id,
                        primitive=primitive,
                        actor=actor,
                        timestamp=timestamp,
                        target_ids=list(result.target_ids),
                        cost=[cost for event in result.budget_events for cost in event.cost],
                        outcome=PrimitiveOutcome.SUCCESS,
                        request=request.model_dump(mode="json"),
                        response=response.model_dump(mode="json"),
                    )
                )
                for event in result.budget_events:
                    transaction.record_budget_event(event.model_copy(update={"call_id": call_id}))
                success_response = response
                success_result = result
        except PrimitiveRejectedError as exc:
            rejection_result, rejection_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request,
                error=exc.error,
                outcome=PrimitiveOutcome.REJECTED,
            )
            self.store.record_primitive_call(rejection_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-decision",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.DECISION,
                    payload={
                        "outcome": rejection_result.outcome.value,
                        "request": request.model_dump(mode="json"),
                    },
                    debug_fields={"error_code": exc.error.code.value},
                ),
            )
            return rejection_result
        except Exception as exc:
            failure_result, failure_log = self._build_failure_result(
                primitive=primitive,
                actor=actor,
                call_id=call_id,
                timestamp=timestamp,
                request_payload=request,
                error=_unexpected_error(exc),
                outcome=PrimitiveOutcome.ROLLED_BACK,
            )
            self.store.record_primitive_call(failure_log)
            self._record_telemetry(
                enabled=dev_mode,
                event=self._primitive_event(
                    event_id=f"{call_id}-result",
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    actor=actor,
                    primitive=primitive,
                    kind=TelemetryEventKind.ACTION_RESULT,
                    payload={
                        "outcome": failure_result.outcome.value,
                        "request": request.model_dump(mode="json"),
                    },
                    debug_fields={
                        "error_code": failure_result.error.code.value
                        if failure_result.error
                        else "unknown"
                    },
                ),
            )
            return failure_result

        if execution_result is None or success_response is None or success_result is None:
            raise RuntimeError("primitive runtime internal error: missing write success state")

        self._record_telemetry(
            enabled=dev_mode,
            event=self._primitive_event(
                event_id=f"{call_id}-result",
                occurred_at=timestamp,
                run_id=run_id,
                operation_id=operation_id,
                actor=actor,
                primitive=primitive,
                kind=TelemetryEventKind.ACTION_RESULT,
                payload={
                    "outcome": execution_result.outcome.value,
                    "request": request.model_dump(mode="json"),
                    "response": success_response.model_dump(mode="json"),
                },
                debug_fields={
                    "target_ids": list(success_result.target_ids),
                    "mutated_ids": list(success_result.mutated_ids or success_result.target_ids),
                    "budget_event_count": len(success_result.budget_events),
                },
            ),
        )
        self._record_emissions(
            enabled=dev_mode,
            call_id=call_id,
            occurred_at=timestamp,
            run_id=run_id,
            operation_id=operation_id,
            actor=actor,
            emissions=success_result.telemetry_emissions,
        )
        for delta_event in self._object_delta_events(
            primitive=primitive,
            actor=actor,
            call_id=call_id,
            timestamp=timestamp,
            run_id=run_id,
            operation_id=operation_id,
            mutated_ids=success_result.mutated_ids or success_result.target_ids,
        ):
            self._record_telemetry(enabled=dev_mode, event=delta_event)
        return execution_result

    @staticmethod
    def _build_failure_result(
        *,
        primitive: PrimitiveName,
        actor: str,
        call_id: str,
        timestamp: datetime,
        request_payload: BaseModel | dict[str, Any],
        error: PrimitiveError,
        outcome: PrimitiveOutcome,
    ) -> tuple[PrimitiveExecutionResult, PrimitiveCallLog]:
        request_data = _json_compatible_payload(request_payload)
        result = PrimitiveExecutionResult(
            primitive=primitive,
            outcome=outcome,
            error=error,
        )
        log = PrimitiveCallLog(
            call_id=call_id,
            primitive=primitive,
            actor=actor,
            timestamp=timestamp,
            outcome=outcome,
            request=request_data,
            error=error,
        )
        return result, log

    def _record_telemetry(
        self,
        *,
        enabled: bool,
        event: TelemetryEvent,
    ) -> None:
        if not enabled or self._telemetry_recorder is None:
            return
        self._telemetry_recorder.record(event)

    def _record_emissions(
        self,
        *,
        enabled: bool,
        call_id: str,
        occurred_at: datetime,
        run_id: str,
        operation_id: str,
        actor: str,
        emissions: tuple[PrimitiveTelemetryEmission, ...],
    ) -> None:
        if not enabled:
            return
        for index, emission in enumerate(emissions, start=1):
            self._record_telemetry(
                enabled=True,
                event=TelemetryEvent(
                    event_id=f"{call_id}-{emission.scope.value}-{index}",
                    scope=emission.scope,
                    kind=emission.kind,
                    occurred_at=occurred_at,
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=emission.parent_event_id or f"{call_id}-entry",
                    job_id=emission.job_id,
                    workspace_id=emission.workspace_id,
                    actor=actor,
                    payload=emission.payload,
                    debug_fields=emission.debug_fields,
                ),
            )

    def _primitive_event(
        self,
        *,
        event_id: str,
        occurred_at: datetime,
        run_id: str,
        operation_id: str,
        actor: str,
        primitive: PrimitiveName,
        kind: TelemetryEventKind,
        parent_event_id: str | None = None,
        payload: dict[str, Any],
        debug_fields: dict[str, Any],
    ) -> TelemetryEvent:
        return TelemetryEvent(
            event_id=event_id,
            scope=TelemetryScope.PRIMITIVE,
            kind=kind,
            occurred_at=occurred_at,
            run_id=run_id,
            operation_id=operation_id,
            parent_event_id=parent_event_id,
            actor=actor,
            payload={"primitive": primitive.value, **payload},
            debug_fields=debug_fields,
        )

    def _object_delta_events(
        self,
        *,
        primitive: PrimitiveName,
        actor: str,
        call_id: str,
        timestamp: datetime,
        run_id: str,
        operation_id: str,
        mutated_ids: tuple[str, ...],
    ) -> tuple[TelemetryEvent, ...]:
        events: list[TelemetryEvent] = []
        for index, object_id in enumerate(mutated_ids, start=1):
            after = _json_compatible_payload(self.store.read_object(object_id))
            current_version = int(after["version"])
            before: dict[str, Any] = {}
            previous_versions = [
                version
                for version in self.store.versions_for_object(object_id)
                if version < current_version
            ]
            if previous_versions:
                before = _json_compatible_payload(
                    self.store.read_object(object_id, version=max(previous_versions))
                )
            events.append(
                TelemetryEvent(
                    event_id=f"{call_id}-object-delta-{index}",
                    scope=TelemetryScope.OBJECT_DELTA,
                    kind=TelemetryEventKind.STATE_DELTA,
                    occurred_at=timestamp,
                    run_id=run_id,
                    operation_id=operation_id,
                    parent_event_id=f"{call_id}-result",
                    object_id=object_id,
                    object_version=current_version,
                    actor=actor,
                    before=before,
                    after=after,
                    delta=_snapshot_delta(before, after),
                    payload={"primitive": primitive.value},
                    debug_fields={
                        "created": not previous_versions,
                        "object_type": after["type"],
                    },
                )
            )
        return tuple(events)


def _new_call_id(primitive: PrimitiveName) -> str:
    return f"{primitive.value}-{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _unexpected_error(exc: Exception) -> PrimitiveError:
    return PrimitiveError(
        code=PrimitiveErrorCode.INTERNAL_ERROR,
        message=str(exc) or exc.__class__.__name__,
        details={"exception_type": exc.__class__.__name__},
    )


def _schema_error(exc: ValidationError) -> PrimitiveError:
    return PrimitiveError(
        code=PrimitiveErrorCode.SCHEMA_INVALID,
        message="request schema validation failed",
        details={"errors": exc.errors(include_url=False)},
    )


def _json_compatible_payload(payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return TypeAdapter(dict[str, Any]).dump_python(payload, mode="json")


def _snapshot_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value != after_value:
            delta[key] = {
                "before": before_value,
                "after": after_value,
            }
    return delta

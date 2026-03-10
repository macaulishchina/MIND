"""Runtime helpers for primitive execution, logging, and rollback."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter, ValidationError

from mind.kernel.store import MemoryStore, PrimitiveTransaction

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
    budget_events: tuple[BudgetEvent, ...] = ()


class PrimitiveRejectedError(RuntimeError):
    """Signal an explicit primitive rejection without partial state changes."""

    def __init__(self, error: PrimitiveError) -> None:
        super().__init__(error.message)
        self.error = error


class PrimitiveRuntime:
    """Common execution wrapper for Phase C primitive service methods."""

    def __init__(
        self,
        store: MemoryStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self._clock = clock or _utc_now

    def execute_read[RequestModelT: BaseModel, ResponseModelT: BaseModel](
        self,
        *,
        primitive: PrimitiveName,
        actor: str,
        request_model: type[RequestModelT],
        response_model: type[ResponseModelT],
        request_payload: RequestModelT | dict[str, Any],
        handler: ReadPrimitiveHandler[RequestModelT, ResponseModelT],
    ) -> PrimitiveExecutionResult:
        call_id = _new_call_id(primitive)
        timestamp = self._clock()
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
        self.store.record_primitive_call(call_log)
        for event in result.budget_events:
            self.store.record_budget_event(event.model_copy(update={"call_id": call_id}))
        return execution_result

    def execute_write[RequestModelT: BaseModel, ResponseModelT: BaseModel](
        self,
        *,
        primitive: PrimitiveName,
        actor: str,
        request_model: type[RequestModelT],
        response_model: type[ResponseModelT],
        request_payload: RequestModelT | dict[str, Any],
        handler: WritePrimitiveHandler[RequestModelT, ResponseModelT],
    ) -> PrimitiveExecutionResult:
        call_id = _new_call_id(primitive)
        timestamp = self._clock()
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
            return failure_result

        try:
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
                return execution_result
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
            return failure_result

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

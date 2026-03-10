"""Shared helpers for application service adapters."""

from __future__ import annotations

from mind.app.contracts import AppError, AppErrorCode, AppRequest, AppResponse, AppStatus
from mind.app.errors import map_primitive_error
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import PrimitiveExecutionResult, PrimitiveName, PrimitiveOutcome


def new_response(
    req: AppRequest | None = None,
    *,
    fallback_request_id: str | None = None,
) -> AppResponse:
    """Create a response envelope with correlation fields pre-filled."""

    request_id = req.request_id if req is not None else fallback_request_id
    idempotency_key = req.idempotency_key if req is not None else None
    trace_ref = f"app:{request_id}" if request_id is not None else None
    return AppResponse(
        request_id=request_id,
        idempotency_key=idempotency_key,
        trace_ref=trace_ref,
    )


def latest_trace_ref(
    store: MemoryStore,
    *,
    primitive: PrimitiveName | None = None,
) -> str | None:
    """Return the most recent primitive call id recorded in the store."""

    logs = store.iter_primitive_call_logs()
    for log in reversed(logs):
        if primitive is None or log.primitive is primitive:
            return log.call_id
    return None


def latest_audit_ref(
    store: MemoryStore,
    *,
    operation_id: str | None = None,
) -> str | None:
    """Return the latest governance audit id, optionally scoped to one operation."""

    audits = (
        store.iter_governance_audit_for_operation(operation_id)
        if operation_id is not None
        else store.iter_governance_audit()
    )
    if not audits:
        return None
    return audits[-1].audit_id


def result_status(outcome: PrimitiveOutcome) -> AppStatus:
    """Project primitive outcomes onto the app-layer status enum."""

    if outcome is PrimitiveOutcome.REJECTED:
        return AppStatus.REJECTED
    return AppStatus.ERROR


def result_error(result: PrimitiveExecutionResult) -> AppError:
    """Map a primitive execution result to a unified AppError."""

    if result.error is not None:
        return map_primitive_error(result.error)
    return AppError(
        code=AppErrorCode.INTERNAL_ERROR,
        message="operation failed without structured error",
    )

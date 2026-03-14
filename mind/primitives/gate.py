"""Primitive gate evaluation helpers."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from mind.fixtures.primitive_golden_calls import (
    PrimitiveGoldenCallCase,
    build_primitive_golden_calls_v1,
    build_primitive_seed_objects,
)
from mind.kernel.store import MemoryStoreFactory, SQLiteMemoryStore
from mind.primitives.contracts import (
    LinkRequest,
    LinkResponse,
    PrimitiveCallLog,
    PrimitiveErrorCode,
    PrimitiveExecutionContext,
    PrimitiveExecutionResult,
    PrimitiveName,
    PrimitiveOutcome,
    ReadRequest,
    ReadResponse,
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
from mind.primitives.service import PrimitiveService

RequestModelMap: dict[PrimitiveName, type[BaseModel]] = {
    PrimitiveName.WRITE_RAW: WriteRawRequest,
    PrimitiveName.READ: ReadRequest,
    PrimitiveName.RETRIEVE: RetrieveRequest,
    PrimitiveName.SUMMARIZE: SummarizeRequest,
    PrimitiveName.LINK: LinkRequest,
    PrimitiveName.REFLECT: ReflectRequest,
    PrimitiveName.REORGANIZE_SIMPLE: ReorganizeSimpleRequest,
}

ResponseModelMap: dict[PrimitiveName, type[BaseModel]] = {
    PrimitiveName.WRITE_RAW: WriteRawResponse,
    PrimitiveName.READ: ReadResponse,
    PrimitiveName.RETRIEVE: RetrieveResponse,
    PrimitiveName.SUMMARIZE: SummarizeResponse,
    PrimitiveName.LINK: LinkResponse,
    PrimitiveName.REFLECT: ReflectResponse,
    PrimitiveName.REORGANIZE_SIMPLE: ReorganizeSimpleResponse,
}


@dataclass(frozen=True)
class PrimitiveGoldenCallRun:
    case_id: str
    primitive: PrimitiveName
    tags: tuple[str, ...]
    outcome: PrimitiveOutcome
    error_code: PrimitiveErrorCode | None
    expectation_matched: bool
    schema_valid: bool
    log_covered: bool
    budget_rejected: bool
    rollback_atomic: bool


@dataclass(frozen=True)
class PrimitiveGateResult:
    total_calls: int
    schema_valid_calls: int
    structured_log_calls: int
    expectation_match_count: int
    smoke_success_count: int
    budget_rejection_match_count: int
    budget_total: int
    rollback_atomic_count: int
    rollback_total: int
    runs: tuple[PrimitiveGoldenCallRun, ...]

    @property
    def c1_pass(self) -> bool:
        return self.smoke_success_count == 7

    @property
    def c2_pass(self) -> bool:
        return self.total_calls >= 200 and self.schema_valid_calls == self.total_calls

    @property
    def c3_pass(self) -> bool:
        return self.structured_log_calls == self.total_calls

    @property
    def c4_pass(self) -> bool:
        return self.budget_total == 50 and self.budget_rejection_match_count == self.budget_total

    @property
    def c5_pass(self) -> bool:
        return self.rollback_total == 50 and self.rollback_atomic_count == self.rollback_total

    @property
    def primitive_gate_pass(self) -> bool:
        return self.c1_pass and self.c2_pass and self.c3_pass and self.c4_pass and self.c5_pass


def evaluate_primitive_gate(
    db_path: str | Path | None = None,
    store_factory: MemoryStoreFactory | None = None,
) -> PrimitiveGateResult:
    calls = build_primitive_golden_calls_v1()
    seed_objects = build_primitive_seed_objects()

    def default_store_factory(store_path: Path) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(store_path)

    def run(store_path: Path, active_store_factory: MemoryStoreFactory) -> PrimitiveGateResult:
        clock = _StepClock()
        with active_store_factory(store_path) as store:
            store.insert_objects(seed_objects)
            runs: list[PrimitiveGoldenCallRun] = []

            for call in calls:
                before_objects = _snapshot_objects(store.iter_objects())
                before_logs = len(store.iter_primitive_call_logs())
                before_budget_events = len(store.iter_budget_events())

                cap_port = _StubCapabilityPort()
                service = _FaultInjectingPrimitiveService(
                    store,
                    clock=clock.now,
                    capability_service=cap_port,
                    inject_fault_for=call.primitive if call.expectation.inject_fault else None,
                )
                method = getattr(service, call.primitive.value)
                result = method(call.request, call.context)

                after_logs = store.iter_primitive_call_logs()
                after_budget_events = store.iter_budget_events()
                after_objects = _snapshot_objects(store.iter_objects())
                log_count_delta = len(after_logs) - before_logs
                budget_event_delta = len(after_budget_events) - before_budget_events
                latest_log = after_logs[-1] if log_count_delta == 1 else None

                request_schema_valid = _request_schema_valid(call)
                response_schema_valid = _response_schema_valid(call.primitive, result)
                schema_valid = request_schema_valid and response_schema_valid
                expectation_matched = _expectation_matched(call, result)
                log_covered = log_count_delta == 1 and _log_has_required_fields(latest_log)
                budget_rejected = "budget" in call.expectation.tags and (
                    result.outcome is PrimitiveOutcome.REJECTED
                    and result.error is not None
                    and result.error.code is PrimitiveErrorCode.BUDGET_EXHAUSTED
                    and budget_event_delta == 0
                    and before_objects == after_objects
                )
                rollback_atomic = "rollback" in call.expectation.tags and (
                    result.outcome is PrimitiveOutcome.ROLLED_BACK
                    and result.error is not None
                    and result.error.code is PrimitiveErrorCode.INTERNAL_ERROR
                    and budget_event_delta == 0
                    and before_objects == after_objects
                )

                runs.append(
                    PrimitiveGoldenCallRun(
                        case_id=call.case_id,
                        primitive=call.primitive,
                        tags=call.expectation.tags,
                        outcome=result.outcome,
                        error_code=result.error.code if result.error is not None else None,
                        expectation_matched=expectation_matched,
                        schema_valid=schema_valid,
                        log_covered=log_covered,
                        budget_rejected=budget_rejected,
                        rollback_atomic=rollback_atomic,
                    )
                )

        return PrimitiveGateResult(
            total_calls=len(calls),
            schema_valid_calls=sum(run.schema_valid for run in runs),
            structured_log_calls=sum(run.log_covered for run in runs),
            expectation_match_count=sum(run.expectation_matched for run in runs),
            smoke_success_count=sum(
                "smoke" in run.tags
                and run.outcome is PrimitiveOutcome.SUCCESS
                and run.expectation_matched
                for run in runs
            ),
            budget_rejection_match_count=sum(run.budget_rejected for run in runs),
            budget_total=sum("budget" in run.tags for run in runs),
            rollback_atomic_count=sum(run.rollback_atomic for run in runs),
            rollback_total=sum("rollback" in run.tags for run in runs),
            runs=tuple(runs),
        )

    active_factory = store_factory or default_store_factory

    if db_path is not None:
        return run(Path(db_path), active_factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        return run(Path(tmpdir) / "primitive_gate.sqlite3", active_factory)


def assert_primitive_gate(result: PrimitiveGateResult) -> None:
    if result.expectation_match_count != result.total_calls:
        raise RuntimeError(
            "primitive golden call mismatch "
            f"({result.expectation_match_count}/{result.total_calls})"
        )
    if not result.c1_pass:
        raise RuntimeError(f"C-1 failed: smoke coverage {result.smoke_success_count}/7")
    if not result.c2_pass:
        raise RuntimeError(
            f"C-2 failed: schema compliance ({result.schema_valid_calls}/{result.total_calls})"
        )
    if not result.c3_pass:
        raise RuntimeError(
            "C-3 failed: structured log coverage "
            f"({result.structured_log_calls}/{result.total_calls})"
        )
    if not result.c4_pass:
        raise RuntimeError(
            "C-4 failed: budget rejection "
            f"({result.budget_rejection_match_count}/{result.budget_total})"
        )
    if not result.c5_pass:
        raise RuntimeError(
            "C-5 failed: rollback atomicity "
            f"({result.rollback_atomic_count}/{result.rollback_total})"
        )


class _StubCapabilityPort:
    """Deterministic CapabilityPort for gate evaluation (no capabilities import)."""

    def summarize_text(
        self,
        *,
        request_id: str,
        source_text: str,
        source_refs: list[str],
        instruction: str | None = None,
        provider_config: Any = None,
    ) -> str:
        words = source_text.split()[:24]
        return " ".join(words) + ("..." if len(source_text.split()) > 24 else "")

    def reflect_text(
        self,
        *,
        request_id: str,
        focus: str | dict[str, Any],
        evidence_text: str,
        episode_id: str | None = None,
        outcome_hint: str | None = None,
        evidence_refs: list[str] | None = None,
        provider_config: Any = None,
    ) -> str:
        f = focus if isinstance(focus, str) else json.dumps(focus, sort_keys=True)
        if outcome_hint in {"success", "failure"}:
            prefix = "Episode succeeded" if outcome_hint == "success" else "Episode failed"
            return f"{prefix}; reflection focus: {f[:120]}"
        words = evidence_text.split()[:20]
        return f"{f}: {' '.join(words)}{'...' if len(evidence_text.split()) > 20 else ''}"

    def resolve_provider_config(
        self,
        *,
        selection: Any = None,
        env: Any = None,
    ) -> Any:
        return None


class _FaultInjectingPrimitiveService(PrimitiveService):
    """Inject a runtime fault after write-side effects but before commit."""

    def __init__(
        self,
        *args: Any,
        inject_fault_for: PrimitiveName | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._inject_fault_for = inject_fault_for

    def _after_write_operation(self, primitive: PrimitiveName) -> None:
        if primitive is self._inject_fault_for:
            raise RuntimeError(f"fault injection for {primitive.value}")


class _StepClock:
    """Deterministic monotonic clock for repeatable gate runs."""

    def __init__(self) -> None:
        self._current = datetime(2026, 3, 9, 15, 0, tzinfo=UTC)

    def now(self) -> datetime:
        value = self._current
        self._current = value + timedelta(seconds=1)
        return value


def _request_schema_valid(call: PrimitiveGoldenCallCase) -> bool:
    try:
        request_model = RequestModelMap[call.primitive]
        PrimitiveExecutionContext.model_validate(call.context)
        request_model.model_validate(call.request)
    except ValidationError:
        return False
    return True


def _response_schema_valid(
    primitive: PrimitiveName,
    result: PrimitiveExecutionResult,
) -> bool:
    try:
        PrimitiveExecutionResult.model_validate(result.model_dump(mode="json"))
        if result.outcome is PrimitiveOutcome.SUCCESS:
            response_model = ResponseModelMap[primitive]
            response_model.model_validate(result.response)
    except ValidationError:
        return False
    return True


def _expectation_matched(
    call: PrimitiveGoldenCallCase,
    result: PrimitiveExecutionResult,
) -> bool:
    actual_error = result.error.code if result.error is not None else None
    return (
        result.outcome is call.expectation.outcome and actual_error is call.expectation.error_code
    )


def _log_has_required_fields(log: PrimitiveCallLog | None) -> bool:
    if log is None:
        return False
    PrimitiveCallLog.model_validate(log.model_dump(mode="json"))
    return bool(
        log.actor
        and log.timestamp is not None
        and isinstance(log.target_ids, list)
        and isinstance(log.cost, list)
        and log.outcome is not None
    )


def _snapshot_objects(objects: list[dict[str, Any]]) -> str:
    return json.dumps(objects, ensure_ascii=True, sort_keys=True)

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from mind.fixtures.golden_episode_set import build_core_object_showcase
from mind.kernel.store import MemoryStore, PrimitiveTransaction, SQLiteMemoryStore
from mind.primitives.contracts import (
    BudgetCost,
    BudgetEvent,
    MemoryObject,
    PrimitiveCallLog,
    PrimitiveCostCategory,
    PrimitiveErrorCode,
    PrimitiveName,
    PrimitiveOutcome,
    ReadRequest,
    ReadResponse,
    RetrieveQueryMode,
    RetrieveRequest,
    WriteRawRequest,
    WriteRawResponse,
)
from mind.primitives.runtime import PrimitiveHandlerResult, PrimitiveRuntime

FIXED_TIMESTAMP = datetime(2026, 3, 9, 12, 0, tzinfo=UTC)


def test_memory_object_contract_accepts_showcase_objects() -> None:
    showcase = build_core_object_showcase()

    validated = [MemoryObject.model_validate(obj) for obj in showcase]

    assert len(validated) == 10
    assert {item.type for item in validated} == {
        "RawRecord",
        "TaskEpisode",
        "SummaryNote",
        "ReflectionNote",
        "EntityNode",
        "LinkEdge",
        "WorkspaceView",
        "SchemaNote",
        "FeedbackRecord",
    }


def test_retrieve_request_requires_at_least_one_budget_limit() -> None:
    with pytest.raises(ValidationError):
        RetrieveRequest.model_validate(
            {
                "query": "recent summaries",
                "query_modes": [RetrieveQueryMode.KEYWORD.value],
                "budget": {},
                "filters": {},
            }
        )


def test_execution_result_rejects_missing_error() -> None:
    from mind.primitives.contracts import PrimitiveExecutionResult

    with pytest.raises(ValidationError):
        PrimitiveExecutionResult(
            primitive=PrimitiveName.READ,
            outcome=PrimitiveOutcome.REJECTED,
        )


def test_runtime_write_success_commits_object_log_and_budget_event(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_write_success.sqlite3"
    request = WriteRawRequest(
        record_kind="user_message",
        content={"text": "phase c raw"},
        episode_id="phase-c-episode",
        timestamp_order=1,
    )

    with SQLiteMemoryStore(db_path) as store:
        runtime = PrimitiveRuntime(store, clock=lambda: FIXED_TIMESTAMP)

        def handler(
            validated_request: WriteRawRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[WriteRawResponse]:
            object_id = "phase-c-raw"
            raw_object: dict[str, Any] = {
                "id": object_id,
                "type": "RawRecord",
                "content": validated_request.content,
                "source_refs": [],
                "created_at": FIXED_TIMESTAMP.isoformat(),
                "updated_at": FIXED_TIMESTAMP.isoformat(),
                "version": 1,
                "status": "active",
                "priority": 0.5,
                "metadata": {
                    "record_kind": validated_request.record_kind,
                    "episode_id": validated_request.episode_id,
                    "timestamp_order": validated_request.timestamp_order,
                },
            }
            transaction.insert_object(raw_object)
            budget_event = BudgetEvent(
                event_id="budget-event-success",
                call_id="pending",
                scope_id="phase-c-smoke",
                primitive=PrimitiveName.WRITE_RAW,
                actor="tester",
                timestamp=FIXED_TIMESTAMP,
                outcome=PrimitiveOutcome.SUCCESS,
                cost=[
                    BudgetCost(category=PrimitiveCostCategory.WRITE, amount=1.0),
                    BudgetCost(category=PrimitiveCostCategory.STORAGE, amount=0.25),
                ],
            )
            return PrimitiveHandlerResult(
                response=WriteRawResponse(object_id=object_id, version=1),
                target_ids=(object_id,),
                budget_events=(budget_event,),
            )

        result = runtime.execute_write(
            primitive=PrimitiveName.WRITE_RAW,
            actor="tester",
            request_model=WriteRawRequest,
            response_model=WriteRawResponse,
            request_payload=request,
            handler=handler,
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert store.has_object("phase-c-raw")

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 1
        assert logs[0].outcome is PrimitiveOutcome.SUCCESS
        assert logs[0].target_ids == ["phase-c-raw"]

        budget_events = store.iter_budget_events()
        assert len(budget_events) == 1
        assert budget_events[0].call_id == logs[0].call_id
        assert budget_events[0].cost[0].category.value == "write"


def test_runtime_write_rollback_clears_partial_state(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_write_rollback.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        runtime = PrimitiveRuntime(store, clock=lambda: FIXED_TIMESTAMP)

        def handler(
            validated_request: WriteRawRequest,
            transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[WriteRawResponse]:
            object_id = "phase-c-rollback"
            transaction.insert_object(
                {
                    "id": object_id,
                    "type": "RawRecord",
                    "content": validated_request.content,
                    "source_refs": [],
                    "created_at": FIXED_TIMESTAMP.isoformat(),
                    "updated_at": FIXED_TIMESTAMP.isoformat(),
                    "version": 1,
                    "status": "active",
                    "priority": 0.4,
                    "metadata": {
                        "record_kind": validated_request.record_kind,
                        "episode_id": validated_request.episode_id,
                        "timestamp_order": validated_request.timestamp_order,
                    },
                }
            )
            transaction.record_primitive_call(
                PrimitiveCallLog(
                    call_id="inflight-log",
                    primitive=PrimitiveName.WRITE_RAW,
                    actor="tester",
                    timestamp=FIXED_TIMESTAMP,
                    target_ids=[object_id],
                    outcome=PrimitiveOutcome.SUCCESS,
                    request=validated_request.model_dump(),
                    response={"object_id": object_id, "version": 1},
                )
            )
            transaction.record_budget_event(
                BudgetEvent(
                    event_id="budget-event-rollback",
                    call_id="pending",
                    scope_id="phase-c-smoke",
                    primitive=PrimitiveName.WRITE_RAW,
                    actor="tester",
                    timestamp=FIXED_TIMESTAMP,
                    outcome=PrimitiveOutcome.SUCCESS,
                    cost=[BudgetCost(category=PrimitiveCostCategory.WRITE, amount=1.0)],
                )
            )
            raise RuntimeError("simulated write failure")

        result = runtime.execute_write(
            primitive=PrimitiveName.WRITE_RAW,
            actor="tester",
            request_model=WriteRawRequest,
            response_model=WriteRawResponse,
            request_payload={
                "record_kind": "user_message",
                "content": {"text": "rollback me"},
                "episode_id": "phase-c-episode",
                "timestamp_order": 1,
            },
            handler=handler,
        )

        assert result.outcome is PrimitiveOutcome.ROLLED_BACK
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.INTERNAL_ERROR
        assert not store.has_object("phase-c-rollback")

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 1
        assert logs[0].outcome is PrimitiveOutcome.ROLLED_BACK
        assert logs[0].response is None
        assert logs[0].error is not None
        assert store.iter_budget_events() == []


def test_runtime_read_records_success_log(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_read.sqlite3"
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        runtime = PrimitiveRuntime(store, clock=lambda: FIXED_TIMESTAMP)

        def handler(
            validated_request: ReadRequest,
            active_store: MemoryStore,
        ) -> PrimitiveHandlerResult[ReadResponse]:
            objects = [
                MemoryObject.model_validate(active_store.read_object(object_id))
                for object_id in validated_request.object_ids
            ]
            return PrimitiveHandlerResult(
                response=ReadResponse(objects=objects),
                target_ids=tuple(validated_request.object_ids),
            )

        result = runtime.execute_read(
            primitive=PrimitiveName.READ,
            actor="tester",
            request_model=ReadRequest,
            response_model=ReadResponse,
            request_payload={"object_ids": [showcase[0]["id"]]},
            handler=handler,
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 1
        assert logs[0].primitive is PrimitiveName.READ
        assert logs[0].request["object_ids"] == [showcase[0]["id"]]

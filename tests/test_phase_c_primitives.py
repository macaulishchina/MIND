from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.store import MemoryStore, SQLiteMemoryStore
from mind.primitives.contracts import (
    PrimitiveErrorCode,
    PrimitiveExecutionContext,
    PrimitiveName,
    PrimitiveOutcome,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService

FIXED_TIMESTAMP = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)


def _context(
    *,
    actor: str = "phase-c-tester",
    budget_scope_id: str = "phase-c-smoke",
    budget_limit: float | None = 100.0,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=budget_scope_id,
        budget_limit=budget_limit,
    )


def test_all_seven_primitives_are_callable_and_logged(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_primitives.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        context = _context()

        write_result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "phase c write raw"},
                "episode_id": episode.episode_id,
                "timestamp_order": 99,
            },
            context,
        )
        read_result = service.read({"object_ids": [showcase[0]["id"]]}, context)
        retrieve_result = service.retrieve(
            {
                "query": "showcase summary",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {"object_types": ["SummaryNote"]},
            },
            context,
        )
        summarize_result = service.summarize(
            {
                "input_refs": [showcase[0]["id"]],
                "summary_scope": "episode",
                "target_kind": "summary_note",
            },
            context,
        )
        link_result = service.link(
            {
                "src_id": showcase[4]["id"],
                "dst_id": showcase[2]["id"],
                "relation_type": "supports",
                "evidence_refs": [showcase[0]["id"]],
            },
            context,
        )
        reflect_result = service.reflect(
            {
                "episode_id": episode.episode_id,
                "focus": "failure analysis",
            },
            context,
        )
        reorganize_result = service.reorganize_simple(
            {
                "target_refs": [showcase[2]["id"], showcase[3]["id"]],
                "operation": "synthesize_schema",
                "reason": "stable procedure across calls",
            },
            context,
        )

        results = [
            write_result,
            read_result,
            retrieve_result,
            summarize_result,
            link_result,
            reflect_result,
            reorganize_result,
        ]
        assert all(result.outcome is PrimitiveOutcome.SUCCESS for result in results)
        assert write_result.response is not None
        assert read_result.response is not None
        assert retrieve_result.response is not None
        assert summarize_result.response is not None
        assert link_result.response is not None
        assert reflect_result.response is not None
        assert reorganize_result.response is not None

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 7
        assert {log.primitive for log in logs} == {
            PrimitiveName.WRITE_RAW,
            PrimitiveName.READ,
            PrimitiveName.RETRIEVE,
            PrimitiveName.SUMMARIZE,
            PrimitiveName.LINK,
            PrimitiveName.REFLECT,
            PrimitiveName.REORGANIZE_SIMPLE,
        }
        assert all(log.actor == "phase-c-tester" for log in logs)
        assert all(log.timestamp == FIXED_TIMESTAMP for log in logs)
        assert all(log.outcome is PrimitiveOutcome.SUCCESS for log in logs)
        assert all(log.cost for log in logs)

        budget_events = store.iter_budget_events()
        assert len(budget_events) == 7
        assert all(event.scope_id == "phase-c-smoke" for event in budget_events)


def test_budget_rejection_returns_explicit_error_code(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_budget.sqlite3"
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.read(
            {"object_ids": [showcase[0]["id"]]},
            _context(budget_scope_id="tight-budget", budget_limit=0.5),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.BUDGET_EXHAUSTED
        assert store.iter_budget_events() == []

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 1
        assert logs[0].outcome is PrimitiveOutcome.REJECTED
        assert logs[0].error is not None
        assert logs[0].error.code is PrimitiveErrorCode.BUDGET_EXHAUSTED


def test_read_strips_reserved_control_plane_metadata_from_response() -> None:
    polluted_object: dict[str, Any] = {
        "id": "polluted-raw",
        "type": "RawRecord",
        "content": {"text": "safe content"},
        "source_refs": [],
        "created_at": FIXED_TIMESTAMP.isoformat(),
        "updated_at": FIXED_TIMESTAMP.isoformat(),
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "episode_id": "episode-1",
            "record_kind": "user_message",
            "timestamp_order": 1,
            "provenance_id": "prov-001",
        },
    }

    class FakeReadStore:
        def __init__(self, obj: dict[str, Any]) -> None:
            self.obj = obj
            self.logs: list[Any] = []
            self.events: list[Any] = []

        def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
            assert object_id == self.obj["id"]
            return dict(self.obj)

        def record_primitive_call(self, log: Any) -> None:
            self.logs.append(log)

        def record_budget_event(self, event: Any) -> None:
            self.events.append(event)

        def iter_budget_events(self) -> list[Any]:
            return []

    store = FakeReadStore(polluted_object)
    service = PrimitiveService(cast(MemoryStore, store), clock=lambda: FIXED_TIMESTAMP)

    result = service.read({"object_ids": ["polluted-raw"]}, _context())

    assert result.outcome is PrimitiveOutcome.SUCCESS
    assert result.response is not None
    returned = result.response["objects"][0]
    assert returned["metadata"]["episode_id"] == "episode-1"
    assert "provenance_id" not in returned["metadata"]
    assert len(store.logs) == 1
    assert len(store.events) == 1


def test_retrieve_uses_latest_versions_and_store_filters(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_d_retrieve.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[3]
    invalid_task_episode: dict[str, Any] = {
        "id": "invalid-showcase-episode",
        "type": "TaskEpisode",
        "content": {"title": "invalid showcase episode"},
        "source_refs": [showcase[0]["id"]],
        "created_at": FIXED_TIMESTAMP.isoformat(),
        "updated_at": FIXED_TIMESTAMP.isoformat(),
        "version": 1,
        "status": "invalid",
        "priority": 0.8,
        "metadata": {
            "task_id": "showcase-task",
            "goal": "invalid task should not be retrieved by default",
            "result": "failure",
            "success": False,
            "record_refs": [showcase[0]["id"]],
        },
    }

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)
        store.insert_object(invalid_task_episode)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        context = _context()

        summary_result = service.retrieve(
            {
                "query": "revised corrected replay hints",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 10},
                "filters": {"object_types": ["SummaryNote"]},
            },
            context,
        )
        task_result = service.retrieve(
            {
                "query": "showcase episode",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 10},
                "filters": {"object_types": ["TaskEpisode"], "task_id": "showcase-task"},
            },
            context,
        )

        assert summary_result.outcome is PrimitiveOutcome.SUCCESS
        assert summary_result.response is not None
        summary_response = RetrieveResponse.model_validate(summary_result.response)
        assert summary_response.candidate_ids.count(f"{episode.episode_id}-summary") == 1

        assert task_result.outcome is PrimitiveOutcome.SUCCESS
        assert task_result.response is not None
        task_response = RetrieveResponse.model_validate(task_result.response)
        assert task_response.candidate_ids == ["showcase-episode"]


def test_retrieve_vector_requires_explicit_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_vector_unavailable.sqlite3"
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.retrieve(
            {
                "query": "vector:showcase-summary",
                "query_modes": ["vector"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.RETRIEVAL_BACKEND_UNAVAILABLE


def test_reorganize_simple_rollback_keeps_store_atomic(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_reorganize_rollback.sqlite3"
    showcase = build_core_object_showcase()
    archived_target: dict[str, Any] = {
        "id": "already-archived",
        "type": "SummaryNote",
        "content": {"summary": "archived already"},
        "source_refs": [showcase[0]["id"]],
        "created_at": FIXED_TIMESTAMP.isoformat(),
        "updated_at": FIXED_TIMESTAMP.isoformat(),
        "version": 1,
        "status": "archived",
        "priority": 0.3,
        "metadata": {
            "summary_scope": "episode",
            "input_refs": [showcase[0]["id"]],
            "compression_ratio_estimate": 0.5,
        },
    }

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_object(archived_target)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.reorganize_simple(
            {
                "target_refs": [showcase[2]["id"], archived_target["id"]],
                "operation": "archive",
                "reason": "lower usage",
            },
            _context(),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.UNSAFE_STATE_TRANSITION
        assert store.versions_for_object(showcase[2]["id"]) == [1]
        assert store.versions_for_object(archived_target["id"]) == [1]

        logs = store.iter_primitive_call_logs()
        assert len(logs) == 1
        assert logs[0].outcome is PrimitiveOutcome.REJECTED
        assert store.iter_budget_events() == []

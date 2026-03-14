from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.kernel.provenance import HIGH_SENSITIVITY_PROVENANCE_FIELDS
from mind.kernel.store import MemoryStore, SQLiteMemoryStore
from mind.primitives.contracts import (
    Capability,
    PrimitiveErrorCode,
    PrimitiveExecutionContext,
    PrimitiveName,
    PrimitiveOutcome,
    RetrieveResponse,
)
from mind.primitives.service import PrimitiveService

FIXED_TIMESTAMP = datetime(2026, 3, 9, 14, 0, tzinfo=UTC)


class _StubCapabilityPort:
    """Minimal stub so summarize / reflect can run without a real LLM."""

    def summarize_text(self, **kwargs: Any) -> str:
        return "stub summary"

    def reflect_text(self, **kwargs: Any) -> str:
        return "stub reflection"

    def resolve_provider_config(self, **kwargs: Any) -> Any:
        return None


def _context(
    *,
    actor: str = "phase-c-tester",
    budget_scope_id: str = "phase-c-smoke",
    budget_limit: float | None = 100.0,
    capabilities: list[Capability] | None = None,
) -> PrimitiveExecutionContext:
    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=budget_scope_id,
        budget_limit=budget_limit,
        capabilities=[Capability.MEMORY_READ] if capabilities is None else capabilities,
    )


def test_all_seven_primitives_are_callable_and_logged(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_c_primitives.sqlite3"
    showcase = build_core_object_showcase()
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        store.insert_objects(episode.objects)
        service = PrimitiveService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            capability_service=_StubCapabilityPort(),
        )
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


def test_write_raw_binds_fallback_direct_provenance(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_write_raw_fallback.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "phase h fallback provenance"},
                "episode_id": "episode-fallback",
                "timestamp_order": 1,
            },
            _context(actor="phase-h-writer"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        assert result.response["provenance_id"] is not None

        provenance = store.direct_provenance_for_object(result.response["object_id"])
        assert provenance.provenance_id == result.response["provenance_id"]
        assert provenance.bound_object_id == result.response["object_id"]
        assert provenance.bound_object_type == "RawRecord"
        assert provenance.producer_kind.value == "system"
        assert provenance.producer_id == "phase-h-writer"
        assert provenance.source_channel.value == "system_internal"
        assert provenance.tenant_id == "default"
        assert provenance.retention_class.value == "default"
        assert provenance.episode_id == "episode-fallback"
        assert provenance.ingested_at == FIXED_TIMESTAMP
        assert provenance.captured_at == FIXED_TIMESTAMP


def test_write_raw_persists_explicit_direct_provenance(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_write_raw_explicit.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "phase h explicit provenance"},
                "episode_id": "episode-explicit",
                "timestamp_order": 2,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-a",
                    "captured_at": "2026-03-08T10:30:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "retention_class": "sensitive",
                    "user_id": "user-a",
                    "ip_addr": "203.0.113.8",
                    "device_id": "device-001",
                    "session_id": "session-001",
                    "request_id": "request-001",
                    "conversation_id": "conversation-001",
                    "episode_id": "episode-explicit",
                },
            },
            _context(actor="phase-h-writer"),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        provenance = store.read_direct_provenance(result.response["provenance_id"])
        assert provenance.bound_object_id == result.response["object_id"]
        assert provenance.producer_kind.value == "user"
        assert provenance.producer_id == "user-a"
        assert provenance.source_channel.value == "chat"
        assert provenance.tenant_id == "tenant-a"
        assert provenance.retention_class.value == "sensitive"
        assert provenance.user_id == "user-a"
        assert provenance.ip_addr == "203.0.113.8"
        assert provenance.device_id == "device-001"
        assert provenance.session_id == "session-001"
        assert provenance.request_id == "request-001"
        assert provenance.conversation_id == "conversation-001"
        assert provenance.episode_id == "episode-explicit"
        assert provenance.captured_at == datetime.fromisoformat("2026-03-08T10:30:00+00:00")
        assert provenance.ingested_at == FIXED_TIMESTAMP


def test_write_raw_rejects_mismatched_direct_provenance_episode(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_write_raw_episode_mismatch.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)

        result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "phase h mismatch"},
                "episode_id": "episode-a",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "user",
                    "producer_id": "user-a",
                    "captured_at": "2026-03-08T10:30:00+00:00",
                    "source_channel": "chat",
                    "tenant_id": "tenant-a",
                    "episode_id": "episode-b",
                },
            },
            _context(actor="phase-h-writer"),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.SCHEMA_INVALID
        assert store.iter_objects() == []
        assert store.iter_direct_provenance() == []


def test_read_with_provenance_requires_capability(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_read_capability.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        write_result = service.write_raw(
            {
                "record_kind": "user_message",
                "content": {"text": "phase h privileged read"},
                "episode_id": "episode-read-cap",
                "timestamp_order": 1,
            },
            _context(actor="phase-h-writer"),
        )

        assert write_result.response is not None
        result = service.read_with_provenance(
            {"object_ids": [write_result.response["object_id"]]},
            _context(actor="phase-h-reader"),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.CAPABILITY_REQUIRED


def test_read_with_provenance_returns_frozen_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_read_with_provenance.sqlite3"

    with SQLiteMemoryStore(db_path) as store:
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        write_result = service.write_raw(
            {
                "record_kind": "assistant_message",
                "content": {"text": "phase h provenance summary"},
                "episode_id": "episode-read-summary",
                "timestamp_order": 1,
                "direct_provenance": {
                    "producer_kind": "model",
                    "producer_id": "model-a",
                    "captured_at": "2026-03-08T18:00:00+00:00",
                    "source_channel": "api",
                    "tenant_id": "tenant-a",
                    "retention_class": "regulated",
                    "model_id": "model-a",
                    "model_provider": "provider-a",
                    "model_version": "v1",
                    "ip_addr": "203.0.113.10",
                    "device_id": "device-010",
                    "machine_fingerprint": "machine-010",
                    "session_id": "session-010",
                    "request_id": "request-010",
                    "conversation_id": "conversation-010",
                    "episode_id": "episode-read-summary",
                },
            },
            _context(actor="phase-h-writer"),
        )

        assert write_result.response is not None
        result = service.read_with_provenance(
            {"object_ids": [write_result.response["object_id"]]},
            _context(
                actor="phase-h-reader",
                capabilities=[
                    Capability.MEMORY_READ,
                    Capability.MEMORY_READ_WITH_PROVENANCE,
                ],
            ),
        )

        assert result.outcome is PrimitiveOutcome.SUCCESS
        assert result.response is not None
        assert result.response["objects"][0]["id"] == write_result.response["object_id"]
        summary = result.response["provenance_summaries"][write_result.response["object_id"]]
        assert summary["provenance_id"] == write_result.response["provenance_id"]
        assert summary["producer_kind"] == "model"
        assert summary["producer_id"] == "model-a"
        assert summary["source_channel"] == "api"
        assert summary["tenant_id"] == "tenant-a"
        assert summary["retention_class"] == "regulated"
        assert summary["model_id"] == "model-a"
        assert summary["model_provider"] == "provider-a"
        assert summary["model_version"] == "v1"
        assert summary["episode_id"] == "episode-read-summary"
        assert not (HIGH_SENSITIVITY_PROVENANCE_FIELDS & set(summary))


def test_retrieve_requires_memory_read_capability(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_h_retrieve_capability.sqlite3"
    showcase = build_core_object_showcase()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(showcase)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        result = service.retrieve(
            {
                "query": "showcase summary",
                "query_modes": ["keyword"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {"object_types": ["SummaryNote"]},
            },
            _context(actor="phase-h-reader", capabilities=[]),
        )

        assert result.outcome is PrimitiveOutcome.REJECTED
        assert result.error is not None
        assert result.error.code is PrimitiveErrorCode.CAPABILITY_REQUIRED


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

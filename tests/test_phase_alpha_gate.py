"""Phase α gate tests: feedback loop, priority signals, scheduler, eval metrics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mind.access.contracts import AccessRunResponse
from mind.eval.growth_metrics import (
    FeedbackCorrelationResult,
    GrowthLiftResult,
    GrowthPhaseAlphaReport,
    MemoryEfficiencyResult,
)
from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.kernel.schema import CORE_OBJECT_TYPES, validate_object
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineMaintenanceService,
    new_offline_job,
)
from mind.offline.replay import _replay_score
from mind.offline.scheduler import OfflineJobScheduler
from mind.offline_jobs import UpdatePriorityJobPayload
from mind.primitives.contracts import (
    PrimitiveExecutionContext,
    PrimitiveName,
    PrimitiveOutcome,
)
from mind.primitives.service import PrimitiveService

FIXED_TIMESTAMP = datetime(2026, 3, 13, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _context(
    *,
    actor: str = "alpha-tester",
    budget_scope_id: str = "alpha-scope",
    budget_limit: float | None = 100.0,
) -> PrimitiveExecutionContext:
    from mind.primitives.contracts import Capability

    return PrimitiveExecutionContext(
        actor=actor,
        budget_scope_id=budget_scope_id,
        budget_limit=budget_limit,
        capabilities=[Capability.MEMORY_READ],
    )


def _raw_object(
    object_id: str = "raw-001",
    episode_id: str = "ep-001",
    *,
    created_at: str | None = None,
    metadata_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ts = created_at or FIXED_TIMESTAMP.isoformat()
    meta: dict[str, Any] = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if metadata_extras:
        meta.update(metadata_extras)
    return {
        "id": object_id,
        "type": "RawRecord",
        "content": {"text": "some content"},
        "source_refs": [],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": meta,
    }


class _FakeJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, OfflineJob] = {}

    def enqueue_offline_job(self, job: OfflineJob | dict[str, Any]) -> None:
        validated = OfflineJob.model_validate(job)
        self._jobs[validated.job_id] = validated

    def iter_offline_jobs(
        self,
        *,
        statuses: Iterable[OfflineJobStatus] = (),
    ) -> list[OfflineJob]:
        jobs = list(self._jobs.values())
        allowed = set(statuses)
        if allowed:
            jobs = [j for j in jobs if j.status in allowed]
        return sorted(jobs, key=lambda j: j.created_at)

    def claim_offline_job(self, **kwargs: Any) -> OfflineJob | None:
        return None

    def complete_offline_job(self, *args: Any, **kwargs: Any) -> None:
        pass

    def fail_offline_job(self, *args: Any, **kwargs: Any) -> None:
        pass

    def cancel_offline_job(self, *args: Any, **kwargs: Any) -> None:
        pass


# ===========================================================================
# α-1: FeedbackRecord schema
# ===========================================================================


def test_feedback_record_is_in_core_object_types() -> None:
    assert "FeedbackRecord" in CORE_OBJECT_TYPES


def test_feedback_record_object_validates_successfully() -> None:
    ts = FIXED_TIMESTAMP.isoformat()
    obj: dict[str, Any] = {
        "id": "feedback-001",
        "type": "FeedbackRecord",
        "content": {"query": "what tasks are due?"},
        "source_refs": ["raw-001"],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "task_id": "task-001",
            "episode_id": "ep-001",
            "query": "what tasks are due?",
            "used_object_ids": ["raw-001"],
            "helpful_object_ids": ["raw-001"],
            "unhelpful_object_ids": [],
            "quality_signal": 0.8,
            "cost": 1.0,
        },
    }
    errors = validate_object(obj)
    assert errors == []


def test_feedback_record_quality_signal_out_of_range_is_rejected() -> None:
    ts = FIXED_TIMESTAMP.isoformat()
    obj: dict[str, Any] = {
        "id": "feedback-002",
        "type": "FeedbackRecord",
        "content": {"query": "test"},
        "source_refs": ["raw-001"],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "task_id": "task-001",
            "episode_id": "ep-001",
            "query": "test",
            "used_object_ids": [],
            "helpful_object_ids": [],
            "unhelpful_object_ids": [],
            "quality_signal": 2.0,  # out of [-1, 1]
            "cost": 0.0,
        },
    }
    errors = validate_object(obj)
    assert any("quality_signal" in e for e in errors)


def test_feedback_record_missing_required_metadata_is_rejected() -> None:
    ts = FIXED_TIMESTAMP.isoformat()
    obj: dict[str, Any] = {
        "id": "feedback-003",
        "type": "FeedbackRecord",
        "content": {"query": "test"},
        "source_refs": ["raw-001"],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": "active",
        "priority": 0.5,
        "metadata": {
            "task_id": "task-001",
            # missing episode_id, query, etc.
        },
    }
    errors = validate_object(obj)
    assert any("episode_id" in e for e in errors)


# ===========================================================================
# α-1: record_feedback primitive
# ===========================================================================


def test_record_feedback_primitive_creates_feedback_object(tmp_path: Path) -> None:
    db_path = tmp_path / "alpha_feedback.sqlite3"
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episode.objects)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        ctx = _context()

        raw_id = episode.objects[0]["id"]
        result = service.record_feedback(
            {
                "task_id": episode.task_id,
                "episode_id": episode.episode_id,
                "query": "test query",
                "used_object_ids": [raw_id],
                "helpful_object_ids": [raw_id],
                "unhelpful_object_ids": [],
                "quality_signal": 0.5,
            },
            ctx,
        )

    assert result.outcome is PrimitiveOutcome.SUCCESS
    assert result.response is not None
    fb_id = result.response["feedback_object_id"]
    assert fb_id.startswith("feedback-")
    assert PrimitiveName.RECORD_FEEDBACK in (r.primitive for r in [result])


def test_record_feedback_updates_access_count_on_used_objects(tmp_path: Path) -> None:
    db_path = tmp_path / "alpha_access_count.sqlite3"
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episode.objects)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        ctx = _context()

        raw_id = episode.objects[0]["id"]
        service.record_feedback(
            {
                "task_id": episode.task_id,
                "episode_id": episode.episode_id,
                "query": "test",
                "used_object_ids": [raw_id],
                "helpful_object_ids": [raw_id],
                "unhelpful_object_ids": [],
                "quality_signal": 1.0,
            },
            ctx,
        )
        updated = store.read_object(raw_id)

    assert updated["metadata"].get("access_count") == 1
    assert updated["metadata"].get("feedback_positive_count") == 1
    assert updated["metadata"].get("feedback_negative_count", 0) == 0
    assert updated["metadata"].get("last_accessed_at") == FIXED_TIMESTAMP.isoformat()


def test_record_feedback_tracks_negative_feedback(tmp_path: Path) -> None:
    db_path = tmp_path / "alpha_neg_feedback.sqlite3"
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episode.objects)
        service = PrimitiveService(store, clock=lambda: FIXED_TIMESTAMP)
        ctx = _context()

        raw_id = episode.objects[0]["id"]
        service.record_feedback(
            {
                "task_id": episode.task_id,
                "episode_id": episode.episode_id,
                "query": "test",
                "used_object_ids": [raw_id],
                "helpful_object_ids": [],
                "unhelpful_object_ids": [raw_id],
                "quality_signal": -0.5,
            },
            ctx,
        )
        updated = store.read_object(raw_id)

    assert updated["metadata"].get("feedback_positive_count", 0) == 0
    assert updated["metadata"].get("feedback_negative_count") == 1


# ===========================================================================
# α-1: AccessRunResponse has used_object_ids and answer_quality_signal
# ===========================================================================


def test_access_run_response_accepts_feedback_fields() -> None:
    from mind.access.contracts import (
        AccessContextKind,
        AccessMode,
        AccessModeTraceEvent,
        AccessReasonCode,
        AccessRunTrace,
        AccessSwitchKind,
        AccessTraceKind,
    )

    trace = AccessRunTrace(
        requested_mode=AccessMode.FLASH,
        resolved_mode=AccessMode.FLASH,
        events=[
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.SELECT_MODE,
                mode=AccessMode.FLASH,
                summary="selected flash",
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
            ),
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.FLASH,
                summary="flash done",
            ),
        ],
    )
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="some context",
        context_token_count=10,
        trace=trace,
        used_object_ids=["obj-1", "obj-2"],
        answer_quality_signal=0.7,
    )
    assert response.used_object_ids == ["obj-1", "obj-2"]
    assert response.answer_quality_signal == 0.7


def test_access_run_response_defaults_to_empty_feedback_fields() -> None:
    from mind.access.contracts import (
        AccessContextKind,
        AccessMode,
        AccessModeTraceEvent,
        AccessReasonCode,
        AccessRunTrace,
        AccessSwitchKind,
        AccessTraceKind,
    )

    trace = AccessRunTrace(
        requested_mode=AccessMode.FLASH,
        resolved_mode=AccessMode.FLASH,
        events=[
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.SELECT_MODE,
                mode=AccessMode.FLASH,
                summary="selected flash",
                reason_code=AccessReasonCode.EXPLICIT_MODE_REQUEST,
                switch_kind=AccessSwitchKind.INITIAL,
            ),
            AccessModeTraceEvent(
                event_kind=AccessTraceKind.MODE_SUMMARY,
                mode=AccessMode.FLASH,
                summary="flash done",
            ),
        ],
    )
    response = AccessRunResponse(
        resolved_mode=AccessMode.FLASH,
        context_kind=AccessContextKind.RAW_TOPK,
        context_text="ctx",
        context_token_count=5,
        trace=trace,
    )
    assert response.used_object_ids == []
    assert response.answer_quality_signal is None


# ===========================================================================
# α-2: replay score with dynamic signals
# ===========================================================================


def test_replay_score_increases_with_access_count() -> None:
    base_obj = _raw_object(metadata_extras={})
    obj_with_accesses = _raw_object(metadata_extras={"access_count": 5})
    base_score = _replay_score(base_obj)
    boosted_score = _replay_score(obj_with_accesses)
    assert boosted_score > base_score


def test_replay_score_increases_with_positive_feedback() -> None:
    base_obj = _raw_object()
    obj_with_positive = _raw_object(metadata_extras={"feedback_positive_count": 3})
    assert _replay_score(obj_with_positive) > _replay_score(base_obj)


def test_replay_score_decreases_with_negative_feedback() -> None:
    base_obj = _raw_object()
    obj_with_negative = _raw_object(metadata_extras={"feedback_negative_count": 2})
    assert _replay_score(obj_with_negative) < _replay_score(base_obj)


def test_replay_score_decreases_with_low_decay_score() -> None:
    base_obj = _raw_object()
    stale_obj = _raw_object(metadata_extras={"decay_score": 0.1})
    assert _replay_score(stale_obj) < _replay_score(base_obj)


def test_replay_score_unchanged_with_neutral_decay() -> None:
    base_obj = _raw_object()
    fresh_obj = _raw_object(metadata_extras={"decay_score": 1.0})
    assert _replay_score(fresh_obj) == pytest.approx(_replay_score(base_obj), abs=0.01)


# ===========================================================================
# α-2: UPDATE_PRIORITY job kind
# ===========================================================================


def test_update_priority_job_kind_exists() -> None:
    assert OfflineJobKind.UPDATE_PRIORITY == "update_priority"


def test_update_priority_job_payload_validates() -> None:
    payload = UpdatePriorityJobPayload(object_ids=["obj-1", "obj-2"], reason="test refresh")
    assert payload.reason == "test refresh"
    assert payload.object_ids == ["obj-1", "obj-2"]


def test_update_priority_job_payload_defaults() -> None:
    payload = UpdatePriorityJobPayload()
    assert payload.object_ids == []
    assert "update" in payload.reason


def test_offline_service_handles_update_priority_job(tmp_path: Path) -> None:
    db_path = tmp_path / "alpha_update_priority.sqlite3"
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episode.objects)
        service = OfflineMaintenanceService(store, clock=lambda: FIXED_TIMESTAMP)
        raw_id = episode.objects[0]["id"]
        job = new_offline_job(
            job_kind=OfflineJobKind.UPDATE_PRIORITY,
            payload=UpdatePriorityJobPayload(object_ids=[raw_id], reason="test"),
            now=FIXED_TIMESTAMP,
        )
        result = service.process_job(job, actor="alpha-tester")

    assert result["job_kind"] == "update_priority"
    assert isinstance(result["updated_count"], int)


# ===========================================================================
# α-3: OfflineJobScheduler
# ===========================================================================


def test_scheduler_enqueues_reflect_episode_on_completed_episode() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)

    episode_obj = {
        "metadata": {
            "result": "task completed successfully",
            "task_id": "task-001",
        }
    }
    job_id = scheduler.on_episode_completed("ep-001", episode_obj)

    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.REFLECT_EPISODE
    assert jobs[0].payload["episode_id"] == "ep-001"


def test_scheduler_does_not_enqueue_for_incomplete_episode() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)

    episode_obj = {"metadata": {"result": None, "task_id": "task-001"}}
    job_id = scheduler.on_episode_completed("ep-001", episode_obj)

    assert job_id is None
    assert len(job_store.iter_offline_jobs()) == 0


def test_scheduler_enqueues_promote_schema_when_threshold_met() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP, promote_threshold=3)

    feedback_obj = {"metadata": {"episode_id": "ep-001"}}
    job_id = scheduler.on_feedback_recorded(feedback_obj, "obj-001", positive_feedback_count=3)

    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.PROMOTE_SCHEMA


def test_scheduler_does_not_enqueue_promote_schema_below_threshold() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP, promote_threshold=3)

    feedback_obj = {"metadata": {"episode_id": "ep-001"}}
    job_id = scheduler.on_feedback_recorded(feedback_obj, "obj-001", positive_feedback_count=2)

    assert job_id is None
    assert len(job_store.iter_offline_jobs()) == 0


def test_scheduler_schedules_update_priority_job() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)

    job_id = scheduler.schedule_priority_update(["obj-1", "obj-2"], reason="batch update")

    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert len(jobs) == 1
    assert jobs[0].job_kind is OfflineJobKind.UPDATE_PRIORITY
    assert jobs[0].payload["object_ids"] == ["obj-1", "obj-2"]


def test_scheduler_schedules_priority_update_for_all_objects() -> None:
    job_store = _FakeJobStore()
    scheduler = OfflineJobScheduler(job_store, clock=lambda: FIXED_TIMESTAMP)

    job_id = scheduler.schedule_priority_update()  # no object_ids = all objects

    assert job_id is not None
    jobs = job_store.iter_offline_jobs()
    assert jobs[0].payload["object_ids"] == []


# ===========================================================================
# α-4: GrowthLift, MemoryEfficiency, FeedbackCorrelation
# ===========================================================================


def test_growth_lift_result_computes_correctly() -> None:
    from mind.eval.runner import (
        LongHorizonBenchmarkRun,
        LongHorizonEvalSequenceResult,
        LongHorizonScoreCard,
    )

    def _make_run(system_id: str, pus_value: float) -> LongHorizonBenchmarkRun:
        return LongHorizonBenchmarkRun(
            system_id=system_id,
            run_id=1,
            fixture_name="test",
            fixture_hash="abc",
            sequence_count=1,
            average_task_success_rate=pus_value,
            average_gold_fact_coverage=0.5,
            average_reuse_rate=0.3,
            average_context_cost_ratio=0.2,
            average_maintenance_cost_ratio=0.1,
            average_pollution_rate=0.0,
            average_pus=pus_value,
            sequence_results=(
                LongHorizonEvalSequenceResult(
                    sequence_id="seq-1",
                    family="single",
                    score_card=LongHorizonScoreCard(
                        task_success_rate=pus_value,
                        gold_fact_coverage=0.5,
                        reuse_rate=0.3,
                        context_cost_ratio=0.2,
                        maintenance_cost_ratio=0.1,
                        pollution_rate=0.0,
                    ),
                ),
            ),
        )

    run_with = _make_run("with_maintenance", 0.6)
    run_without = _make_run("without_maintenance", 0.4)
    result = GrowthLiftResult.compute(run_with, run_without)

    assert result.with_maintenance_pus == 0.6
    assert result.without_maintenance_pus == 0.4
    assert result.growth_lift == pytest.approx(0.2, abs=0.001)


def test_memory_efficiency_computes_correctly() -> None:
    from mind.eval.runner import (
        LongHorizonBenchmarkRun,
        LongHorizonEvalSequenceResult,
        LongHorizonScoreCard,
    )

    run = LongHorizonBenchmarkRun(
        system_id="mind",
        run_id=1,
        fixture_name="test",
        fixture_hash="abc",
        sequence_count=10,
        average_task_success_rate=0.8,
        average_gold_fact_coverage=0.6,
        average_reuse_rate=0.4,
        average_context_cost_ratio=0.2,
        average_maintenance_cost_ratio=0.1,
        average_pollution_rate=0.0,
        average_pus=0.5,
        sequence_results=tuple(
            LongHorizonEvalSequenceResult(
                sequence_id=f"seq-{i}",
                family="single",
                score_card=LongHorizonScoreCard(
                    task_success_rate=0.8,
                    gold_fact_coverage=0.6,
                    reuse_rate=0.4,
                    context_cost_ratio=0.2,
                    maintenance_cost_ratio=0.1,
                    pollution_rate=0.0,
                ),
            )
            for i in range(10)
        ),
    )
    result = MemoryEfficiencyResult.compute(run, total_objects=100)

    assert result.task_count == 10
    assert result.total_objects == 100
    expected = round((0.8 * 10) / 100, 4)
    assert result.memory_efficiency == pytest.approx(expected, abs=0.0001)


def test_memory_efficiency_zero_objects_returns_zero() -> None:
    from mind.eval.runner import (
        LongHorizonBenchmarkRun,
        LongHorizonEvalSequenceResult,
        LongHorizonScoreCard,
    )

    run = LongHorizonBenchmarkRun(
        system_id="mind",
        run_id=1,
        fixture_name="test",
        fixture_hash="abc",
        sequence_count=5,
        average_task_success_rate=0.9,
        average_gold_fact_coverage=0.7,
        average_reuse_rate=0.5,
        average_context_cost_ratio=0.1,
        average_maintenance_cost_ratio=0.1,
        average_pollution_rate=0.0,
        average_pus=0.5,
        sequence_results=tuple(
            LongHorizonEvalSequenceResult(
                sequence_id=f"seq-{i}",
                family="single",
                score_card=LongHorizonScoreCard(
                    task_success_rate=0.9,
                    gold_fact_coverage=0.7,
                    reuse_rate=0.5,
                    context_cost_ratio=0.1,
                    maintenance_cost_ratio=0.1,
                    pollution_rate=0.0,
                ),
            )
            for i in range(5)
        ),
    )
    result = MemoryEfficiencyResult.compute(run, total_objects=0)
    assert result.memory_efficiency == 0.0


def test_feedback_correlation_positive_better_than_negative() -> None:
    positive_ids = {"obj-1", "obj-2"}
    negative_ids = {"obj-3"}
    selected_ids_per_step = [
        ["obj-1"],
        ["obj-2"],
        ["obj-3"],
        ["obj-1", "obj-3"],
    ]
    result = FeedbackCorrelationResult.compute(
        positive_object_ids=positive_ids,
        negative_object_ids=negative_ids,
        selected_ids_per_step=selected_ids_per_step,
    )
    assert result.positive_reuse_rate > result.negative_reuse_rate
    assert result.feedback_correlation > 0


def test_feedback_correlation_empty_steps_returns_zero() -> None:
    result = FeedbackCorrelationResult.compute(
        positive_object_ids={"obj-1"},
        negative_object_ids={"obj-2"},
        selected_ids_per_step=[],
    )
    assert result.feedback_correlation == 0.0


def test_growth_phase_alpha_report_gate_pass() -> None:
    from mind.eval.runner import (
        LongHorizonBenchmarkRun,
        LongHorizonEvalSequenceResult,
        LongHorizonScoreCard,
    )

    def _make_run(pus: float) -> LongHorizonBenchmarkRun:
        return LongHorizonBenchmarkRun(
            system_id="s",
            run_id=1,
            fixture_name="t",
            fixture_hash="h",
            sequence_count=1,
            average_task_success_rate=pus,
            average_gold_fact_coverage=pus,
            average_reuse_rate=0.3,
            average_context_cost_ratio=0.1,
            average_maintenance_cost_ratio=0.1,
            average_pollution_rate=0.0,
            average_pus=pus,
            sequence_results=(
                LongHorizonEvalSequenceResult(
                    sequence_id="seq-1",
                    family="single",
                    score_card=LongHorizonScoreCard(
                        task_success_rate=pus,
                        gold_fact_coverage=pus,
                        reuse_rate=0.3,
                        context_cost_ratio=0.1,
                        maintenance_cost_ratio=0.1,
                        pollution_rate=0.0,
                    ),
                ),
            ),
        )

    report = GrowthPhaseAlphaReport(
        growth_lift=GrowthLiftResult.compute(_make_run(0.7), _make_run(0.5)),
        memory_efficiency=MemoryEfficiencyResult.compute(_make_run(0.7), 50),
        feedback_correlation=FeedbackCorrelationResult.compute(
            positive_object_ids={"o1"},
            negative_object_ids=set(),
            selected_ids_per_step=[["o1"]],
        ),
    )
    assert report.alpha_gate_pass is True
    assert report.growth_lift.growth_lift > 0


def test_new_offline_job_with_update_priority_kind() -> None:
    job = new_offline_job(
        job_kind=OfflineJobKind.UPDATE_PRIORITY,
        payload=UpdatePriorityJobPayload(object_ids=["x"], reason="test"),
        now=FIXED_TIMESTAMP,
    )
    assert job.job_kind is OfflineJobKind.UPDATE_PRIORITY
    assert job.payload["reason"] == "test"
    assert job.payload["object_ids"] == ["x"]

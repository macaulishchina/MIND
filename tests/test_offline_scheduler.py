"""Tests for Phase α-3: Offline Worker Auto-Trigger Scheduler.

Covers:
- Episode-completed auto-enqueues REFLECT_EPISODE
- Feedback-accumulated auto-enqueues PROMOTE_SCHEMA at threshold
- Below-threshold feedback does NOT enqueue
- Priority-update scheduling
- Conflict-detected auto-enqueues RESOLVE_CONFLICT
- Schema-promoted auto-enqueues VERIFY_PROPOSAL
- Scheduler configuration in cli_config
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mind.offline.scheduler import (
    PROMOTE_SCHEMA_POSITIVE_FEEDBACK_THRESHOLD,
    OfflineJobScheduler,
)
from mind.offline_jobs import OfflineJobKind, OfflineJobStatus
from tests.conftest import FakeJobStoreStub

FIXED_NOW = datetime(2026, 3, 14, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scheduler(
    job_store: FakeJobStoreStub | None = None,
    promote_threshold: int = PROMOTE_SCHEMA_POSITIVE_FEEDBACK_THRESHOLD,
) -> tuple[OfflineJobScheduler, FakeJobStoreStub]:
    store = job_store or FakeJobStoreStub()
    sched = OfflineJobScheduler(
        store,
        clock=lambda: FIXED_NOW,
        promote_threshold=promote_threshold,
    )
    return sched, store


def _episode_obj(result: str | None = "success") -> dict[str, Any]:
    return {
        "id": "ep-test",
        "type": "TaskEpisode",
        "metadata": {
            "task_id": "task-1",
            "goal": "test goal",
            "result": result,
            "success": True,
            "record_refs": [],
        },
    }


# ---------------------------------------------------------------------------
# on_episode_completed
# ---------------------------------------------------------------------------


class TestOnEpisodeCompleted:
    def test_enqueues_reflect_when_episode_has_result(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_episode_completed(
            episode_id="ep-1",
            episode_object=_episode_obj(result="task completed successfully"),
        )
        assert job_id is not None
        jobs = store.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING])
        assert len(jobs) == 1
        assert jobs[0].job_kind == OfflineJobKind.REFLECT_EPISODE

    def test_does_not_enqueue_when_episode_has_no_result(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_episode_completed(
            episode_id="ep-1",
            episode_object=_episode_obj(result=None),
        )
        assert job_id is None
        assert len(store.iter_offline_jobs()) == 0

    def test_does_not_enqueue_when_result_is_empty_string(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_episode_completed(
            episode_id="ep-1",
            episode_object=_episode_obj(result=""),
        )
        assert job_id is None


# ---------------------------------------------------------------------------
# on_feedback_recorded
# ---------------------------------------------------------------------------


class TestOnFeedbackRecorded:
    def test_enqueues_promote_at_threshold(self) -> None:
        sched, store = _scheduler(promote_threshold=3)
        job_id = sched.on_feedback_recorded(
            feedback_object={"metadata": {"episode_id": "ep-1"}},
            object_id="obj-1",
            positive_feedback_count=3,
        )
        assert job_id is not None
        jobs = store.iter_offline_jobs(statuses=[OfflineJobStatus.PENDING])
        assert len(jobs) == 1
        assert jobs[0].job_kind == OfflineJobKind.PROMOTE_SCHEMA

    def test_does_not_enqueue_below_threshold(self) -> None:
        sched, store = _scheduler(promote_threshold=3)
        job_id = sched.on_feedback_recorded(
            feedback_object={"metadata": {"episode_id": "ep-1"}},
            object_id="obj-1",
            positive_feedback_count=2,
        )
        assert job_id is None
        assert len(store.iter_offline_jobs()) == 0

    def test_custom_threshold_respected(self) -> None:
        sched, store = _scheduler(promote_threshold=1)
        job_id = sched.on_feedback_recorded(
            feedback_object={"metadata": {}},
            object_id="obj-1",
            positive_feedback_count=1,
        )
        assert job_id is not None


# ---------------------------------------------------------------------------
# schedule_priority_update
# ---------------------------------------------------------------------------


class TestSchedulePriorityUpdate:
    def test_enqueues_update_priority(self) -> None:
        sched, store = _scheduler()
        job_id = sched.schedule_priority_update(
            object_ids=["obj-1", "obj-2"],
            reason="test refresh",
        )
        assert job_id
        jobs = store.iter_offline_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_kind == OfflineJobKind.UPDATE_PRIORITY


# ---------------------------------------------------------------------------
# on_conflict_detected
# ---------------------------------------------------------------------------


class TestOnConflictDetected:
    def test_enqueues_resolve_when_contradiction_present(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_conflict_detected(
            object_id="obj-1",
            conflict_candidates=[
                {"relation": "contradict", "neighbor_id": "obj-2", "confidence": 0.9},
            ],
        )
        assert job_id is not None
        jobs = store.iter_offline_jobs()
        assert jobs[0].job_kind == OfflineJobKind.RESOLVE_CONFLICT

    def test_does_not_enqueue_without_contradiction(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_conflict_detected(
            object_id="obj-1",
            conflict_candidates=[
                {"relation": "duplicate", "neighbor_id": "obj-2", "confidence": 0.95},
            ],
        )
        assert job_id is None


# ---------------------------------------------------------------------------
# on_schema_promoted
# ---------------------------------------------------------------------------


class TestOnSchemaPromoted:
    def test_enqueues_verify_proposal(self) -> None:
        sched, store = _scheduler()
        job_id = sched.on_schema_promoted(schema_note_id="schema-1")
        assert job_id is not None
        jobs = store.iter_offline_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_kind == OfflineJobKind.VERIFY_PROPOSAL


# ---------------------------------------------------------------------------
# α-3.6: scheduler config from cli_config
# ---------------------------------------------------------------------------


class TestSchedulerConfig:
    def test_scheduler_config_defaults(self) -> None:
        from mind.cli_config import SchedulerConfig

        cfg = SchedulerConfig()
        assert cfg.auto_reflect_enabled is True
        assert cfg.promote_threshold == 3
        assert cfg.priority_refresh_days == 7

    def test_default_promote_threshold_matches_scheduler_constant(self) -> None:
        from mind.cli_config import SchedulerConfig

        cfg = SchedulerConfig()
        assert cfg.promote_threshold == PROMOTE_SCHEMA_POSITIVE_FEEDBACK_THRESHOLD

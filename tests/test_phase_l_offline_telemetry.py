from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineMaintenanceError,
    OfflineMaintenanceService,
    OfflineWorker,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from mind.telemetry import InMemoryTelemetryRecorder, TelemetryEventKind, TelemetryScope

FIXED_TIMESTAMP = datetime(2026, 3, 12, 1, 30, tzinfo=UTC)


class _SingleJobStore:
    def __init__(self, jobs: list[OfflineJob]) -> None:
        self._jobs = {job.job_id: job for job in jobs}

    def enqueue_offline_job(self, job: OfflineJob | dict) -> None:
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
            jobs = [job for job in jobs if job.status in allowed]
        return sorted(jobs, key=lambda item: (item.created_at, item.job_id))

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        allowed_job_kinds = set(job_kinds)
        jobs = [
            job
            for job in self._jobs.values()
            if job.status is OfflineJobStatus.PENDING
            and job.available_at <= now
            and job.attempt_count < job.max_attempts
            and (not allowed_job_kinds or job.job_kind in allowed_job_kinds)
        ]
        if not jobs:
            return None
        selected = jobs[0]
        claimed = selected.model_copy(
            update={
                "status": OfflineJobStatus.RUNNING,
                "attempt_count": selected.attempt_count + 1,
                "locked_by": worker_id,
                "locked_at": now,
                "updated_at": now,
            }
        )
        self._jobs[claimed.job_id] = claimed
        return claimed

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict,
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.SUCCEEDED,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "result": result,
                "error": None,
            }
        )

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict,
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.FAILED,
                "completed_at": failed_at,
                "updated_at": failed_at,
                "result": None,
                "error": error,
            }
        )


def test_offline_reflect_job_emits_offline_events_in_dev_mode(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(tmp_path / "phase_l_offline_reflect.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        job = new_offline_job(
            job_id="phase-l-reflect-job",
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload=ReflectEpisodeJobPayload(
                episode_id=episode.episode_id,
                focus="offline telemetry reflection",
            ),
            now=FIXED_TIMESTAMP,
        )

        result = service.process_job(
            job,
            actor="phase-l-offline",
            dev_mode=True,
            telemetry_run_id="run-phase-l-offline-001",
        )

    offline_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.OFFLINE
    ]
    assert [event.kind for event in offline_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert all(event.run_id == "run-phase-l-offline-001" for event in offline_events)
    assert all(event.job_id == "phase-l-reflect-job" for event in offline_events)
    assert offline_events[1].payload["primitive"] == "reflect"
    assert offline_events[1].payload["episode_id"] == episode.episode_id
    assert offline_events[2].payload["result"]["reflection_object_id"] == result["reflection_object_id"]

    primitive_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.PRIMITIVE
    ]
    assert primitive_events
    assert all(event.run_id == "run-phase-l-offline-001" for event in primitive_events)
    assert all(
        event.operation_id == "offline-reflect_episode-phase-l-reflect-job"
        for event in primitive_events
    )
    assert primitive_events[0].parent_event_id == (
        "offline-reflect_episode-phase-l-reflect-job-dispatch"
    )


def test_offline_promote_job_emits_assessment_and_result_events(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    episodes = build_golden_episode_set()
    reflect_episode = next(item for item in episodes if item.episode_id == "episode-004")
    promotion_episode = next(item for item in episodes if item.episode_id == "episode-008")

    with SQLiteMemoryStore(tmp_path / "phase_l_offline_promote.sqlite3") as store:
        store.insert_objects(reflect_episode.objects)
        store.insert_objects(promotion_episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        job = new_offline_job(
            job_id="phase-l-promote-job",
            job_kind=OfflineJobKind.PROMOTE_SCHEMA,
            payload=PromoteSchemaJobPayload(
                target_refs=[
                    f"{reflect_episode.episode_id}-reflection",
                    f"{promotion_episode.episode_id}-reflection",
                ],
                reason="promote repeated stale-memory pattern",
            ),
            now=FIXED_TIMESTAMP,
        )

        result = service.process_job(job, actor="phase-l-offline", dev_mode=True)

    offline_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.OFFLINE
    ]
    assert [event.kind for event in offline_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert offline_events[1].payload["stage"] == "dispatch"
    assert offline_events[2].payload["stage"] == "promotion_assessment"
    assert offline_events[2].payload["promote"] is True
    assert offline_events[2].payload["supporting_episode_ids"] == [
        reflect_episode.episode_id,
        promotion_episode.episode_id,
    ]
    assert offline_events[3].payload["result"]["schema_object_id"] == result["schema_object_id"]

    object_delta_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.OBJECT_DELTA
    ]
    assert object_delta_events
    assert all(event.run_id == "offline-phase-l-promote-job" for event in object_delta_events)
    assert all(
        event.operation_id == "offline-promote_schema-phase-l-promote-job"
        for event in object_delta_events
    )


def test_offline_telemetry_records_failure_before_reraising(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    episode = build_golden_episode_set()[0]

    with SQLiteMemoryStore(tmp_path / "phase_l_offline_failure.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        job = new_offline_job(
            job_id="phase-l-invalid-promote-job",
            job_kind=OfflineJobKind.PROMOTE_SCHEMA,
            payload=PromoteSchemaJobPayload(
                target_refs=[
                    f"{episode.episode_id}-summary",
                    f"{episode.episode_id}-summary",
                ],
                reason="should fail because support is same episode",
            ),
            now=FIXED_TIMESTAMP,
        )

        with pytest.raises(OfflineMaintenanceError, match="cross-episode support"):
            service.process_job(job, actor="phase-l-offline", dev_mode=True)

    offline_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.OFFLINE
    ]
    assert [event.kind for event in offline_events] == [
        TelemetryEventKind.ENTRY,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.DECISION,
        TelemetryEventKind.ACTION_RESULT,
    ]
    assert offline_events[-1].payload["outcome"] == "failure"
    assert offline_events[-1].payload["error_type"] == "OfflineMaintenanceError"
    assert "cross-episode support" in offline_events[-1].payload["error_message"]


def test_offline_service_does_not_emit_when_dev_mode_disabled(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(tmp_path / "phase_l_offline_disabled.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        service.process_job(
            new_offline_job(
                job_id="phase-l-reflect-off",
                job_kind=OfflineJobKind.REFLECT_EPISODE,
                payload=ReflectEpisodeJobPayload(
                    episode_id=episode.episode_id,
                    focus="offline telemetry disabled",
                ),
                now=FIXED_TIMESTAMP,
            ),
            actor="phase-l-offline",
        )

    assert [event for event in recorder.iter_events() if event.scope is TelemetryScope.OFFLINE] == []


def test_offline_worker_passes_dev_mode_to_maintenance_service(tmp_path: Path) -> None:
    recorder = InMemoryTelemetryRecorder()
    episode = build_golden_episode_set()[3]

    with SQLiteMemoryStore(tmp_path / "phase_l_offline_worker.sqlite3") as store:
        store.insert_objects(episode.objects)
        service = OfflineMaintenanceService(
            store,
            clock=lambda: FIXED_TIMESTAMP,
            telemetry_recorder=recorder,
        )
        job_store = _SingleJobStore(
            [
                new_offline_job(
                    job_id="phase-l-worker-reflect",
                    job_kind=OfflineJobKind.REFLECT_EPISODE,
                    payload=ReflectEpisodeJobPayload(
                        episode_id=episode.episode_id,
                        focus="offline worker telemetry",
                    ),
                    now=FIXED_TIMESTAMP,
                )
            ]
        )
        worker = OfflineWorker(
            job_store,
            service,
            worker_id="phase-l-worker",
            clock=lambda: FIXED_TIMESTAMP,
            dev_mode=True,
        )

        run = worker.run_once(max_jobs=1)

    assert run.succeeded_jobs == 1
    offline_events = [
        event for event in recorder.iter_events() if event.scope is TelemetryScope.OFFLINE
    ]
    assert offline_events
    assert all(event.run_id == "offline-phase-l-worker-reflect" for event in offline_events)
    assert all(event.job_id == "phase-l-worker-reflect" for event in offline_events)

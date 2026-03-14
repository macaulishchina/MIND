from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mind.fixtures.golden_episode_set import build_golden_episode_set
from mind.kernel.store import SQLiteMemoryStore
from mind.offline import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
    OfflineMaintenanceService,
    OfflineWorker,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
    new_offline_job,
)
from tests.conftest import FakeJobStoreFull

FIXED_TIMESTAMP = datetime(2026, 3, 9, 18, 0, tzinfo=UTC)




def test_offline_worker_processes_reflection_and_promotion_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_e_worker.sqlite3"
    episodes = build_golden_episode_set()
    reflect_episode = episodes[3]
    promotion_episode = episodes[7]

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(reflect_episode.objects)
        store.insert_objects(promotion_episode.objects)
        maintenance_service = OfflineMaintenanceService(store, clock=lambda: FIXED_TIMESTAMP)
        job_store = FakeJobStoreFull(
            [
                new_offline_job(
                    job_id="job-reflect",
                    job_kind=OfflineJobKind.REFLECT_EPISODE,
                    payload=ReflectEpisodeJobPayload(
                        episode_id=reflect_episode.episode_id,
                        focus="offline replay reflection",
                    ),
                    priority=0.9,
                    now=FIXED_TIMESTAMP,
                ),
                new_offline_job(
                    job_id="job-promote",
                    job_kind=OfflineJobKind.PROMOTE_SCHEMA,
                    payload=PromoteSchemaJobPayload(
                        target_refs=[
                            f"{reflect_episode.episode_id}-reflection",
                            f"{promotion_episode.episode_id}-reflection",
                        ],
                        reason="promote repeated stale-memory pattern",
                    ),
                    priority=0.8,
                    now=FIXED_TIMESTAMP,
                ),
            ]
        )
        worker = OfflineWorker(
            job_store,
            maintenance_service,
            worker_id="phase-e-worker",
            clock=lambda: FIXED_TIMESTAMP,
        )

        run = worker.run_once(max_jobs=2)

        assert run.claimed_jobs == 2
        assert run.succeeded_jobs == 2
        assert run.failed_jobs == 0

        jobs = job_store.iter_offline_jobs()
        assert [job.status for job in jobs] == [
            OfflineJobStatus.SUCCEEDED,
            OfflineJobStatus.SUCCEEDED,
        ]
        reflect_result = next(job.result for job in jobs if job.job_id == "job-reflect")
        promote_result = next(job.result for job in jobs if job.job_id == "job-promote")
        assert reflect_result is not None
        assert promote_result is not None

        reflection = store.read_object(str(reflect_result["reflection_object_id"]))
        assert reflection["type"] == "ReflectionNote"
        assert reflection["source_refs"]

        schema = store.read_object(str(promote_result["schema_object_id"]))
        assert schema["type"] == "SchemaNote"
        # Phase β-4: promotion sets proposal_status=proposed on a new version.
        assert schema["version"] >= 1
        assert schema["metadata"].get("proposal_status") == "proposed"
        assert schema["source_refs"] == [
            f"{reflect_episode.episode_id}-reflection",
            f"{promotion_episode.episode_id}-reflection",
        ]
        assert schema["metadata"]["supporting_episode_ids"] == [
            reflect_episode.episode_id,
            promotion_episode.episode_id,
        ]
        assert schema["metadata"]["promotion_source_refs"] == schema["source_refs"]


def test_offline_worker_marks_failed_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "phase_e_worker_fail.sqlite3"
    episodes = build_golden_episode_set()

    with SQLiteMemoryStore(db_path) as store:
        store.insert_objects(episodes[0].objects)
        maintenance_service = OfflineMaintenanceService(store, clock=lambda: FIXED_TIMESTAMP)
        job_store = FakeJobStoreFull(
            [
                new_offline_job(
                    job_id="job-invalid-promotion",
                    job_kind=OfflineJobKind.PROMOTE_SCHEMA,
                    payload=PromoteSchemaJobPayload(
                        target_refs=[
                            f"{episodes[0].episode_id}-summary",
                            f"{episodes[0].episode_id}-summary",
                        ],
                        reason="should fail because support is same episode",
                    ),
                    priority=0.7,
                    now=FIXED_TIMESTAMP,
                )
            ]
        )
        worker = OfflineWorker(
            job_store,
            maintenance_service,
            worker_id="phase-e-worker",
            clock=lambda: FIXED_TIMESTAMP,
        )

        run = worker.run_once(max_jobs=1)

        assert run.claimed_jobs == 1
        assert run.succeeded_jobs == 0
        assert run.failed_jobs == 1
        failed_job = job_store.iter_offline_jobs()[0]
        assert failed_job.status is OfflineJobStatus.FAILED
        assert failed_job.error is not None
        assert "cross-episode support" in str(failed_job.error["message"])


def test_offline_worker_replays_job_provider_selection() -> None:
    captured: dict[str, object] = {}

    class _FakeMaintenanceService:
        def process_job(
            self,
            job: OfflineJob,
            *,
            actor: str,
            dev_mode: bool = False,
            provider_selection: dict[str, object] | None = None,
            telemetry_run_id: str | None = None,
        ) -> dict[str, object]:
            captured["job_id"] = job.job_id
            captured["actor"] = actor
            captured["provider_selection"] = provider_selection
            return {"job_id": job.job_id, "ok": True}

    job_store = FakeJobStoreFull(
        [
            new_offline_job(
                job_id="job-provider-selection",
                job_kind=OfflineJobKind.REFLECT_EPISODE,
                payload=ReflectEpisodeJobPayload(
                    episode_id="episode-004",
                    focus="worker provider replay",
                ),
                provider_selection={
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "endpoint": "https://api.openai.com/v1/responses",
                    "timeout_ms": 12_000,
                    "retry_policy": "none",
                },
                now=FIXED_TIMESTAMP,
            )
        ]
    )
    worker = OfflineWorker(
        job_store,
        _FakeMaintenanceService(),  # type: ignore[arg-type]
        worker_id="phase-e-worker",
        clock=lambda: FIXED_TIMESTAMP,
    )

    run = worker.run_once(max_jobs=1)

    assert run.succeeded_jobs == 1
    assert captured["job_id"] == "job-provider-selection"
    assert captured["actor"] == "phase-e-worker"
    assert captured["provider_selection"] is not None
    assert captured["provider_selection"]["provider"] == "openai"  # type: ignore[index]

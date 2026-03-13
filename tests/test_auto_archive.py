"""Tests for Phase γ-5: Memory decay and auto-archive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from mind.eval.growth_metrics import ArchiveReport
from mind.kernel.store import SQLiteMemoryStore
from mind.offline_jobs import AutoArchiveJobPayload, OfflineJobKind
from mind.offline.scheduler import OfflineJobScheduler


def _ts(days_ago: float = 0.0) -> str:
    dt = datetime.now(UTC) - timedelta(days=days_ago)
    return dt.isoformat()


def _raw_object(
    obj_id: str,
    *,
    days_old: float = 0.0,
    positive_feedback_count: int = 0,
    status: str = "active",
    obj_type: str = "RawRecord",
    episode_id: str = "ep-1",
) -> dict:
    ts = _ts(days_ago=days_old)
    meta: dict = {
        "record_kind": "user_message",
        "episode_id": episode_id,
        "timestamp_order": 1,
    }
    if positive_feedback_count > 0:
        meta["feedback_positive_count"] = positive_feedback_count
    return {
        "id": obj_id,
        "type": obj_type,
        "content": f"content for {obj_id}",
        "source_refs": [],
        "created_at": ts,
        "updated_at": ts,
        "version": 1,
        "status": status,
        "priority": 0.5,
        "metadata": meta,
    }


# ─── AUTO_ARCHIVE job kind ────────────────────────────────────────────────────


class TestAutoArchiveJobKind:
    def test_auto_archive_kind_exists(self) -> None:
        assert OfflineJobKind.AUTO_ARCHIVE == "auto_archive"

    def test_auto_archive_payload_defaults(self) -> None:
        payload = AutoArchiveJobPayload()
        assert payload.stale_days == 90
        assert payload.dry_run is False

    def test_auto_archive_payload_custom(self) -> None:
        payload = AutoArchiveJobPayload(dry_run=True, stale_days=30, reason="test")
        assert payload.dry_run is True
        assert payload.stale_days == 30

    def test_auto_archive_payload_stale_days_ge_1(self) -> None:
        with pytest.raises(Exception):
            AutoArchiveJobPayload(stale_days=0)


# ─── OfflineJobScheduler.schedule_auto_archive ───────────────────────────────


class TestSchedulerAutoArchive:
    def _fake_store(self) -> tuple[list, object]:
        jobs: list = []

        class FakeStore:
            def enqueue_offline_job(self, job):
                jobs.append(job)

            def iter_offline_jobs(self, *, statuses=()):
                return list(jobs)

        return jobs, FakeStore()

    def test_schedule_auto_archive_enqueues_job(self) -> None:
        jobs, store = self._fake_store()
        scheduler = OfflineJobScheduler(store)  # type: ignore[arg-type]
        job_id = scheduler.schedule_auto_archive()
        assert len(jobs) == 1
        assert jobs[0].job_kind == OfflineJobKind.AUTO_ARCHIVE
        assert job_id == jobs[0].job_id

    def test_schedule_auto_archive_dry_run(self) -> None:
        jobs, store = self._fake_store()
        scheduler = OfflineJobScheduler(store)  # type: ignore[arg-type]
        scheduler.schedule_auto_archive(dry_run=True, stale_days=30)
        payload = AutoArchiveJobPayload.model_validate(jobs[0].payload)
        assert payload.dry_run is True
        assert payload.stale_days == 30

    def test_schedule_auto_archive_priority(self) -> None:
        jobs, store = self._fake_store()
        scheduler = OfflineJobScheduler(store)  # type: ignore[arg-type]
        scheduler.schedule_auto_archive(priority=0.1)
        assert jobs[0].priority == 0.1


# ─── Auto-archive execution ───────────────────────────────────────────────────


class TestAutoArchiveExecution:
    def _store(self) -> SQLiteMemoryStore:
        return SQLiteMemoryStore(":memory:")

    def _service(self, store: SQLiteMemoryStore):
        from mind.offline.service import OfflineMaintenanceService
        return OfflineMaintenanceService(store)

    def _make_job(self, payload: AutoArchiveJobPayload):
        from mind.offline_jobs import new_offline_job
        return new_offline_job(
            job_kind=OfflineJobKind.AUTO_ARCHIVE,
            payload=payload,
        )

    def test_stale_object_archived(self) -> None:
        store = self._store()
        stale_obj = _raw_object("stale-1", days_old=100)
        store.insert_object(stale_obj)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert result["archived_count"] == 1
        assert "stale-1" in result["archived_ids"]
        archived = store.read_object("stale-1")
        assert archived["status"] == "archived"

    def test_fresh_object_not_archived(self) -> None:
        store = self._store()
        fresh_obj = _raw_object("fresh-1", days_old=10)
        store.insert_object(fresh_obj)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert result["archived_count"] == 0
        assert store.read_object("fresh-1")["status"] == "active"

    def test_object_with_positive_feedback_not_archived(self) -> None:
        store = self._store()
        feedback_obj = _raw_object("feedback-obj-1", days_old=100, positive_feedback_count=3)
        store.insert_object(feedback_obj)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert "feedback-obj-1" not in result["archived_ids"]
        assert store.read_object("feedback-obj-1")["status"] == "active"

    def test_dry_run_does_not_modify_store(self) -> None:
        store = self._store()
        stale_obj = _raw_object("dry-stale-1", days_old=100)
        store.insert_object(stale_obj)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90, dry_run=True))
        result = service.process_job(job, actor="test")

        assert result["dry_run"] is True
        assert result["archived_count"] >= 1
        # Object should remain active in dry-run mode.
        assert store.read_object("dry-stale-1")["status"] == "active"

    def test_only_raw_record_and_summary_note_archived(self) -> None:
        store = self._store()
        raw = _raw_object("arch-raw-1", days_old=100)
        store.insert_object(raw)
        # Insert a seed episode for the ReflectionNote source_refs.
        seed_ep = _raw_object("ep-99-seed", days_old=100, episode_id="ep-99")
        store.insert_object(seed_ep)
        # ReflectionNote is not in eligible_types — should not be archived.
        reflection = {
            "id": "arch-reflect-1",
            "type": "ReflectionNote",
            "content": "old reflection",
            "source_refs": ["ep-99-seed"],
            "created_at": _ts(100),
            "updated_at": _ts(100),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "episode_id": "ep-99",
                "reflection_kind": "success",
                "claims": ["old claim"],
            },
        }
        store.insert_object(reflection)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert "arch-raw-1" in result["archived_ids"]
        assert "arch-reflect-1" not in result["archived_ids"]
        assert store.read_object("arch-reflect-1")["status"] == "active"

    def test_archived_objects_not_re_archived(self) -> None:
        store = self._store()
        already_archived = _raw_object("already-arch-1", days_old=200, status="archived")
        store.insert_object(already_archived)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert "already-arch-1" not in result["archived_ids"]

    def test_summary_note_eligible_for_archive(self) -> None:
        store = self._store()
        # Insert source object first.
        src = _raw_object("ep-1-seed", days_old=100)
        store.insert_object(src)
        summary = {
            "id": "stale-summary-1",
            "type": "SummaryNote",
            "content": "old summary",
            "source_refs": ["ep-1-seed"],
            "created_at": _ts(100),
            "updated_at": _ts(100),
            "version": 1,
            "status": "active",
            "priority": 0.5,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": ["ep-1-seed"],
                "compression_ratio_estimate": 0.5,
            },
        }
        store.insert_object(summary)

        service = self._service(store)
        job = self._make_job(AutoArchiveJobPayload(stale_days=90))
        result = service.process_job(job, actor="test")

        assert "stale-summary-1" in result["archived_ids"]


# ─── ArchiveReport metric ─────────────────────────────────────────────────────


class TestArchiveReport:
    def test_compute_zero_total(self) -> None:
        report = ArchiveReport.compute(
            archived_count=0,
            unarchived_count=0,
            total_objects=0,
        )
        assert report.archive_rate == 0.0
        assert report.misarchive_rate == 0.0

    def test_compute_basic_metrics(self) -> None:
        report = ArchiveReport.compute(
            archived_count=10,
            unarchived_count=1,
            total_objects=100,
        )
        assert report.archive_rate == pytest.approx(0.10)
        assert report.misarchive_rate == pytest.approx(0.10)

    def test_gamma_gate_pass(self) -> None:
        report = ArchiveReport.compute(
            archived_count=50,
            unarchived_count=5,
            total_objects=500,
        )
        assert report.gamma_gate_pass  # misarchive_rate = 0.10 ≤ 0.10

    def test_gamma_gate_fail(self) -> None:
        report = ArchiveReport.compute(
            archived_count=10,
            unarchived_count=2,
            total_objects=100,
        )
        assert not report.gamma_gate_pass  # misarchive_rate = 0.20 > 0.10

    def test_no_archived_gate_passes(self) -> None:
        report = ArchiveReport.compute(
            archived_count=0,
            unarchived_count=0,
            total_objects=100,
        )
        assert report.gamma_gate_pass

    def test_archive_rate_correct(self) -> None:
        report = ArchiveReport.compute(
            archived_count=20,
            unarchived_count=0,
            total_objects=200,
        )
        assert report.archive_rate == pytest.approx(0.10)


# ─── product_cli unarchive command ───────────────────────────────────────────


class TestProductCliUnarchive:
    def test_unarchive_subcommand_registered(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        # Verify "unarchive" is a registered subcommand.
        choices = parser._subparsers._group_actions[0].choices
        assert "unarchive" in choices

    def test_unarchive_requires_object_id(self) -> None:
        from mind.product_cli import build_product_parser

        parser = build_product_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["unarchive"])  # missing --object-id

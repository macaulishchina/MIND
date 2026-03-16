from __future__ import annotations

import json
import os
import re
from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from mind.kernel.store import SQLiteMemoryStore
from mind.offline_jobs import (
    OfflineJob,
    OfflineJobKind,
    OfflineJobStatus,
)

try:
    from xdist.scheduler.loadfile import LoadFileScheduling  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - xdist is installed for health checks
    LoadFileScheduling = None

DEFAULT_PYTEST_TIMING_PATH = Path(".ai/health/pytest-timing-latest.json")
_GATE_TEST_PATH_RE = re.compile(r"(^|.*/)test_phase_[^/]+_gate\.py$")
_PHASE_TEST_PATH_RE = re.compile(r"(^|.*/)test_phase_([^_/]+)_.+\.py$")
_SLOW_TEST_FILES = {
    "test_access_benchmark.py",
    "test_postgres_regression.py",
    "test_phase_f_comparison.py",
}


@dataclass
class _TimingCase:
    """Aggregate timing information for a single pytest nodeid."""

    nodeid: str
    phase: str
    duration_seconds: float = 0.0
    outcome: str = "passed"
    worker_id: str = "master"


@dataclass
class _TimingState:
    """Shared timing accumulator for the current pytest session."""

    cases: dict[str, _TimingCase]


_TIMING_STATE: _TimingState | None = None


def _phase_for_nodeid(nodeid: str) -> str:
    """Map a pytest nodeid to a phase bucket for timing reports."""
    path = nodeid.split("::", 1)[0]
    match = _PHASE_TEST_PATH_RE.search(path)
    if match is None:
        return "unphased"
    return match.group(2)


def _timing_output_path() -> Path:
    """Return the configured pytest timing output path."""
    raw = os.environ.get("MIND_PYTEST_TIMING_PATH")
    return Path(raw) if raw else DEFAULT_PYTEST_TIMING_PATH


def _scheduler_mode(config: pytest.Config) -> str:
    return str(getattr(cast(Any, config), "_mind_pytest_scheduler_mode", "serial"))


def _set_scheduler_mode(config: pytest.Config, mode: str) -> None:
    cast(Any, config)._mind_pytest_scheduler_mode = mode


def _configured_worker_count(config: pytest.Config) -> int:
    """Return the configured xdist worker count for the active pytest run."""
    numprocesses = getattr(config.option, "numprocesses", None)
    if isinstance(numprocesses, int):
        return max(1, numprocesses)
    if isinstance(numprocesses, str) and numprocesses.isdigit():
        return max(1, int(numprocesses))
    return 1


def _merge_outcome(current: str, report: pytest.TestReport) -> str:
    """Merge a phase report outcome into the overall test-case outcome."""
    if report.failed:
        return "failed"
    if report.skipped and current != "failed":
        return "skipped"
    if current not in {"failed", "skipped"} and report.passed:
        return "passed"
    return current


def _timing_payload(config: pytest.Config) -> dict[str, Any]:
    """Build the persisted pytest timing payload from the current session."""
    cases = list((_TIMING_STATE or _TimingState({})).cases.values())
    sorted_cases = sorted(cases, key=lambda case: case.duration_seconds, reverse=True)
    totals = Counter(case.outcome for case in sorted_cases)
    total_duration = sum(case.duration_seconds for case in sorted_cases)

    phase_buckets: dict[str, dict[str, Any]] = {}
    for case in sorted_cases:
        bucket = phase_buckets.setdefault(
            case.phase,
            {
                "phase": case.phase,
                "test_case_count": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total_duration_seconds": 0.0,
            },
        )
        bucket["test_case_count"] += 1
        bucket[case.outcome] += 1
        bucket["total_duration_seconds"] += case.duration_seconds

    phase_summaries = sorted(
        phase_buckets.values(),
        key=lambda item: (-float(item["total_duration_seconds"]), item["phase"]),
    )
    for summary in phase_summaries:
        summary["total_duration_seconds"] = round(float(summary["total_duration_seconds"]), 6)

    worker_count = _configured_worker_count(config)
    xdist_enabled = worker_count > 1
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "worker_count": worker_count,
        "xdist_enabled": xdist_enabled,
        "scheduler_mode": _scheduler_mode(config),
        "totals": {
            "test_case_count": len(sorted_cases),
            "passed": totals.get("passed", 0),
            "failed": totals.get("failed", 0),
            "skipped": totals.get("skipped", 0),
            "total_duration_seconds": round(total_duration, 6),
        },
        "phase_summaries": phase_summaries,
        "test_cases": [
            {
                "nodeid": case.nodeid,
                "phase": case.phase,
                "duration_seconds": round(case.duration_seconds, 6),
                "outcome": case.outcome,
                "worker_id": case.worker_id,
            }
            for case in sorted_cases
        ],
    }


def _load_weighted_file_durations(path: Path) -> dict[str, tuple[float, int]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    file_totals: dict[str, list[float | int]] = {}
    for case in payload.get("test_cases", []):
        nodeid = case.get("nodeid")
        if not isinstance(nodeid, str) or not nodeid:
            continue
        file_path = nodeid.split("::", 1)[0]
        duration_seconds = float(case.get("duration_seconds", 0.0))
        bucket = file_totals.setdefault(file_path, [0.0, 0])
        bucket[0] += duration_seconds
        bucket[1] += 1
    return {
        file_path: (round(float(duration), 6), int(case_count))
        for file_path, (duration, case_count) in file_totals.items()
    }


if LoadFileScheduling is not None:
    class _WeightedLoadFileScheduling(LoadFileScheduling):
        def __init__(
            self,
            config: pytest.Config,
            log: Any,
            file_weights: dict[str, tuple[float, int]],
        ) -> None:
            super().__init__(config, log)
            self._file_weights = file_weights

        def schedule(self) -> None:
            assert self.collection_is_completed

            if getattr(self, "collection", None) is not None:
                for node in self.nodes:
                    self._reschedule(node)
                return

            if not self._check_nodes_have_same_collection():
                self.log("**Different tests collected, aborting run**")
                return

            collection = cast(
                list[str],
                list(next(iter(self.registered_collections.values()))),
            )
            self.__dict__["collection"] = collection
            if not collection:
                return

            unsorted_workqueue: dict[str, dict[str, bool]] = {}
            for nodeid in collection:
                scope = self._split_scope(nodeid)
                work_unit = unsorted_workqueue.setdefault(scope, {})
                work_unit[nodeid] = False

            self.workqueue = OrderedDict(
                sorted(
                    unsorted_workqueue.items(),
                    key=lambda item: self._weighted_scope_key(item[0], item[1]),
                )
            )

            extra_nodes = len(self.nodes) - len(self.workqueue)
            if extra_nodes > 0:
                self.log(f"Shutting down {extra_nodes} nodes")
                for _ in range(extra_nodes):
                    unused_node, assigned = self.assigned_work.popitem()
                    self.log(f"Shutting down unused node {unused_node}")
                    unused_node.shutdown()

            for node in self.nodes:
                self._assign_work_unit(node)

            for node in self.nodes:
                self._reschedule(node)

            if not self.workqueue:
                for node in self.nodes:
                    node.shutdown()

        def _weighted_scope_key(
            self,
            scope: str,
            work_unit: dict[str, bool],
        ) -> tuple[int, float, int, int, str]:
            if scope in self._file_weights:
                duration_seconds, case_count = self._file_weights[scope]
                return (0, -duration_seconds, -case_count, 0, scope)
            return (1, 0.0, 0, -len(work_unit), scope)


def pytest_configure(config: pytest.Config) -> None:
    """Initialize shared timing state for the pytest session."""
    global _TIMING_STATE
    if hasattr(config, "workerinput"):
        return

    if _configured_worker_count(config) <= 1:
        _set_scheduler_mode(config, "serial")
    elif getattr(config.option, "dist", "") == "loadfile":
        _set_scheduler_mode(config, "loadfile")
    else:
        _set_scheduler_mode(config, str(getattr(config.option, "dist", "parallel")))
    _TIMING_STATE = _TimingState(cases={})


def pytest_xdist_make_scheduler(config: pytest.Config, log: Any) -> Any:
    if LoadFileScheduling is None:
        return None
    if getattr(config.option, "dist", "") != "loadfile":
        return None

    file_weights = _load_weighted_file_durations(_timing_output_path())
    if not file_weights:
        return None

    _set_scheduler_mode(config, "loadfile(weighted)")
    return _WeightedLoadFileScheduling(config, log, file_weights)


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Apply repo-wide gate/slow markers during collection."""
    del config
    for item in items:
        path = str(item.path)
        basename = Path(path).name
        if _GATE_TEST_PATH_RE.search(path):
            item.add_marker(pytest.mark.gate)
        if basename in _SLOW_TEST_FILES:
            item.add_marker(pytest.mark.slow)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Accumulate per-test total runtime across setup/call/teardown phases."""
    if _TIMING_STATE is None:
        return
    if report.when not in {"setup", "call", "teardown"}:
        return

    entry = _TIMING_STATE.cases.setdefault(
        report.nodeid,
        _TimingCase(nodeid=report.nodeid, phase=_phase_for_nodeid(report.nodeid)),
    )
    entry.duration_seconds += report.duration
    worker_id = getattr(report, "worker_id", None)
    if worker_id is not None:
        entry.worker_id = str(worker_id)
    entry.outcome = _merge_outcome(entry.outcome, report)


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print compact phase and slow-test timing summaries."""
    del exitstatus
    if hasattr(config, "workerinput") or _TIMING_STATE is None:
        return

    payload = _timing_payload(config)
    terminalreporter.section("Pytest timing summary")
    terminalreporter.write_line(f"Timing log: {_timing_output_path()}")
    terminalreporter.write_line(f"Scheduling: {payload['scheduler_mode']}")

    for summary in payload["phase_summaries"][:5]:
        terminalreporter.write_line(
            "Phase {phase}: {total:.3f}s across {count} cases "
            "({passed} passed, {failed} failed, {skipped} skipped)".format(
                phase=summary["phase"],
                total=summary["total_duration_seconds"],
                count=summary["test_case_count"],
                passed=summary["passed"],
                failed=summary["failed"],
                skipped=summary["skipped"],
            )
        )

    for case in payload["test_cases"][:10]:
        terminalreporter.write_line(
            "Slow test: {duration:.3f}s [{outcome}] {nodeid}".format(
                duration=case["duration_seconds"],
                outcome=case["outcome"],
                nodeid=case["nodeid"],
            )
        )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Persist pytest timing data to a structured JSON report."""
    del exitstatus
    if hasattr(session.config, "workerinput") or _TIMING_STATE is None:
        return

    output_path = _timing_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_timing_payload(session.config), indent=2) + "\n")


@pytest.fixture(autouse=True)
def _enable_test_only_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIND_ALLOW_SQLITE_FOR_TESTS", "1")


# ---------------------------------------------------------------------------
# Shared store factory
# ---------------------------------------------------------------------------


@pytest.fixture()
def make_store(tmp_path: Path) -> Callable[..., SQLiteMemoryStore]:
    """Return a factory that creates isolated ``SQLiteMemoryStore`` instances.

    Each call returns a *new* store backed by its own SQLite file so tests
    that need multiple stores can simply call the factory twice.

    Usage::

        def test_something(make_store):
            with make_store() as store:
                ...
    """
    _counter = 0

    def _factory(name: str | None = None) -> SQLiteMemoryStore:
        nonlocal _counter
        _counter += 1
        fname = f"{name or 'store'}.sqlite3" if name else f"store_{_counter}.sqlite3"
        return SQLiteMemoryStore(tmp_path / fname)

    return _factory


# ---------------------------------------------------------------------------
# Shared FakeOfflineJobStore — stub tier (no-op claim/complete/fail/cancel)
# ---------------------------------------------------------------------------


class FakeJobStoreStub:
    """Minimal ``OfflineJobStore`` stub: records enqueued jobs, returns them
    via ``iter_offline_jobs``.  Claim always returns ``None``; lifecycle
    methods are no-ops.  Suitable for tests that only need to inspect which
    jobs were enqueued.
    """

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
        return sorted(jobs, key=lambda j: (j.created_at, j.job_id))

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        return None

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        pass

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        pass

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# Shared FakeOfflineJobStore — full-fidelity tier (real lifecycle)
# ---------------------------------------------------------------------------


class FakeJobStoreFull:
    """In-memory ``OfflineJobStore`` with full job lifecycle: claim picks the
    highest-priority pending job, and complete/fail/cancel update status.
    Initialise with a list of pre-seeded jobs for worker tests.
    """

    def __init__(self, jobs: list[OfflineJob] | None = None) -> None:
        self._jobs: dict[str, OfflineJob] = (
            {job.job_id: job for job in jobs} if jobs else {}
        )

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
            jobs = [job for job in jobs if job.status in allowed]
        return sorted(jobs, key=lambda job: (job.created_at, job.job_id))

    def claim_offline_job(
        self,
        *,
        worker_id: str,
        now: datetime,
        job_kinds: Iterable[OfflineJobKind] = (),
    ) -> OfflineJob | None:
        allowed_job_kinds = set(job_kinds)
        candidates = [
            job
            for job in self._jobs.values()
            if job.status is OfflineJobStatus.PENDING
            and job.available_at <= now
            and job.attempt_count < job.max_attempts
            and (not allowed_job_kinds or job.job_kind in allowed_job_kinds)
        ]
        if not candidates:
            return None
        selected = max(
            candidates,
            key=lambda job: (job.priority, -job.created_at.timestamp()),
        )
        claimed = selected.model_copy(
            update={
                "status": OfflineJobStatus.RUNNING,
                "attempt_count": selected.attempt_count + 1,
                "locked_by": worker_id,
                "locked_at": now,
                "updated_at": now,
            },
        )
        self._jobs[claimed.job_id] = claimed
        return claimed

    def complete_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.SUCCEEDED,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "result": result,
                "error": None,
            },
        )

    def fail_offline_job(
        self,
        job_id: str,
        *,
        worker_id: str,
        failed_at: datetime,
        error: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.FAILED,
                "completed_at": failed_at,
                "updated_at": failed_at,
                "result": None,
                "error": error,
            },
        )

    def cancel_offline_job(
        self,
        job_id: str,
        *,
        cancelled_at: datetime,
        error: dict[str, Any],
    ) -> None:
        job = self._jobs[job_id]
        self._jobs[job_id] = job.model_copy(
            update={
                "status": OfflineJobStatus.FAILED,
                "completed_at": cancelled_at,
                "updated_at": cancelled_at,
                "result": None,
                "error": error,
            },
        )

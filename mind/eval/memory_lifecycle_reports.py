"""Artifact helpers for lifecycle benchmark reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mind.eval.memory_lifecycle import (
    MemoryLifecycleAskMetrics,
    MemoryLifecycleBenchmarkReport,
    MemoryLifecycleCostSnapshot,
    MemoryLifecycleMemorySnapshot,
    MemoryLifecycleStageReport,
    write_memory_lifecycle_benchmark_report_json,
)


@dataclass(frozen=True)
class MemoryLifecycleBenchmarkArtifactPaths:
    """Filesystem layout used by persisted lifecycle benchmark runs."""

    root_dir: Path
    run_dir: Path
    report_path: Path
    telemetry_path: Path
    store_path: Path


def prepare_memory_lifecycle_benchmark_artifacts(
    root_dir: str | Path,
    *,
    run_id: str,
) -> MemoryLifecycleBenchmarkArtifactPaths:
    """Prepare deterministic artifact paths for one lifecycle benchmark run."""

    root = Path(root_dir)
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return MemoryLifecycleBenchmarkArtifactPaths(
        root_dir=root,
        run_dir=run_dir,
        report_path=run_dir / "report.json",
        telemetry_path=run_dir / "telemetry.jsonl",
        store_path=run_dir / "benchmark.sqlite3",
    )


def persist_memory_lifecycle_benchmark_report(
    artifacts: MemoryLifecycleBenchmarkArtifactPaths,
    report: MemoryLifecycleBenchmarkReport,
) -> Path:
    """Persist one lifecycle benchmark report into its artifact directory."""

    return write_memory_lifecycle_benchmark_report_json(artifacts.report_path, report)


def load_memory_lifecycle_benchmark_report(
    root_dir: str | Path,
    *,
    run_id: str | None = None,
) -> tuple[MemoryLifecycleBenchmarkReport, Path]:
    """Load one lifecycle benchmark report by run id or most recent artifact."""

    root = Path(root_dir)
    report_path = root / run_id / "report.json" if run_id else _latest_report_path(root)
    if not report_path.exists():
        raise FileNotFoundError(f"memory lifecycle benchmark report not found: {report_path}")
    return read_memory_lifecycle_benchmark_report_json(report_path), report_path


def read_memory_lifecycle_benchmark_report_json(
    path: str | Path,
) -> MemoryLifecycleBenchmarkReport:
    """Read a persisted lifecycle benchmark report from JSON."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    stage_reports = tuple(_stage_from_dict(item) for item in payload.get("stage_reports", ()))
    return MemoryLifecycleBenchmarkReport(
        dataset_name=str(payload["dataset_name"]),
        source_path=str(payload["source_path"]),
        fixture_name=str(payload["fixture_name"]),
        run_id=str(payload["run_id"]),
        telemetry_path=(
            str(payload["telemetry_path"])
            if payload.get("telemetry_path") is not None
            else None
        ),
        store_path=str(payload["store_path"]) if payload.get("store_path") is not None else None,
        bundle_count=int(payload["bundle_count"]),
        answer_case_count=int(payload["answer_case_count"]),
        stage_reports=stage_reports,
        frontend_debug_query={
            str(key): str(value) for key, value in dict(payload["frontend_debug_query"]).items()
        },
        notes=tuple(str(item) for item in payload.get("notes", ())),
    )


def _latest_report_path(root_dir: Path) -> Path:
    report_paths = sorted(
        root_dir.glob("*/report.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not report_paths:
        raise FileNotFoundError(
            f"memory lifecycle benchmark reports directory is empty: {root_dir}"
        )
    return report_paths[0]


def _stage_from_dict(payload: dict[str, Any]) -> MemoryLifecycleStageReport:
    return MemoryLifecycleStageReport(
        stage_name=str(payload["stage_name"]),
        ask=MemoryLifecycleAskMetrics(
            answer_case_count=int(payload["ask"]["answer_case_count"]),
            average_answer_quality=float(payload["ask"]["average_answer_quality"]),
            task_success_rate=float(payload["ask"]["task_success_rate"]),
            candidate_hit_rate=float(payload["ask"]["candidate_hit_rate"]),
            selected_hit_rate=float(payload["ask"]["selected_hit_rate"]),
            reuse_rate=float(payload["ask"]["reuse_rate"]),
            pollution_rate=float(payload["ask"]["pollution_rate"]),
        ),
        memory=MemoryLifecycleMemorySnapshot(
            active_object_count=int(payload["memory"]["active_object_count"]),
            total_object_versions=int(payload["memory"]["total_object_versions"]),
            active_object_counts={
                str(key): int(value)
                for key, value in dict(payload["memory"]["active_object_counts"]).items()
            },
        ),
        cost=MemoryLifecycleCostSnapshot(
            total_cost=float(payload["cost"]["total_cost"]),
            generation_cost=float(payload["cost"]["generation_cost"]),
            maintenance_cost=float(payload["cost"]["maintenance_cost"]),
            retrieval_cost=float(payload["cost"]["retrieval_cost"]),
            read_cost=float(payload["cost"]["read_cost"]),
            write_cost=float(payload["cost"]["write_cost"]),
            storage_cost=float(payload["cost"]["storage_cost"]),
            offline_job_count=int(payload["cost"]["offline_job_count"]),
        ),
        operation_notes=tuple(str(item) for item in payload.get("operation_notes", ())),
    )
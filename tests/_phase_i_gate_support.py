from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from mind.access import (
    AccessAutoAuditResult,
    AccessBenchmarkResult,
    AccessMode,
    AccessRunResponse,
    AccessTaskFamily,
    evaluate_access_auto_audit,
    evaluate_access_benchmark,
    evaluate_access_fixed_lock_audit,
)


@lru_cache(maxsize=12)
def benchmark_result(
    task_family: AccessTaskFamily,
    requested_modes: tuple[AccessMode, ...] | None = None,
    episode_ids: tuple[str, ...] | None = None,
) -> AccessBenchmarkResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        return evaluate_access_benchmark(
            db_path=Path(tmp_dir) / f"phase_i_{task_family.value}.sqlite3",
            task_families=(task_family,),
            requested_modes=requested_modes,
            episode_ids=episode_ids,
        )


@lru_cache(maxsize=4)
def fixed_lock_runs(mode: AccessMode) -> tuple[AccessRunResponse, ...]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        return evaluate_access_fixed_lock_audit(
            Path(tmp_dir) / f"phase_i_fixed_{mode.value}.sqlite3",
            requested_modes=(mode,),
        )


@lru_cache(maxsize=1)
def auto_audit() -> AccessAutoAuditResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        return evaluate_access_auto_audit(Path(tmp_dir) / "phase_i_auto.sqlite3")

from __future__ import annotations

from functools import lru_cache

import pytest

from mind.access import (
    AccessBenchmarkResult,
    AccessMode,
    AccessTaskFamily,
    evaluate_access_benchmark,
)
from mind.cli import mind_main


@lru_cache(maxsize=1)
def _cached_access_benchmark_result() -> AccessBenchmarkResult:
    return evaluate_access_benchmark(
        task_families=(AccessTaskFamily.SPEED_SENSITIVE,),
        requested_modes=(AccessMode.FLASH, AccessMode.AUTO),
    )


def test_access_benchmark_prints_frontier_summary_for_speed_family(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.evaluate_access_benchmark",
        lambda *args, **kwargs: _cached_access_benchmark_result(),
    )

    exit_code = mind_main(["access", "benchmark"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "backend=sqlite" in output
    assert "storage_scope=isolated" in output
    assert "case_count=20" in output
    assert "run_count=40" in output
    assert "aggregate_count=2" in output
    assert "frontier_count=1" in output
    assert "speed_sensitive" in output

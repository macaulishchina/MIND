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
from tests._access_benchmark_support import episode_chunks

_EPISODE_CHUNKS = episode_chunks(chunk_size=10)
_HIGH_CORRECTNESS_FRONTIER_MODES = (
    ("reconstruct", (AccessMode.RECONSTRUCT, AccessMode.AUTO)),
    ("reflective", (AccessMode.REFLECTIVE_ACCESS, AccessMode.AUTO)),
)


@lru_cache(maxsize=4)
def _cached_access_benchmark_result(
    requested_modes: tuple[AccessMode, ...],
    episode_ids: tuple[str, ...],
) -> AccessBenchmarkResult:
    return evaluate_access_benchmark(
        task_families=(AccessTaskFamily.HIGH_CORRECTNESS,),
        requested_modes=requested_modes,
        episode_ids=episode_ids,
    )


@pytest.mark.parametrize(
    ("mode_name", "requested_modes"),
    _HIGH_CORRECTNESS_FRONTIER_MODES,
    ids=[mode_name for mode_name, _ in _HIGH_CORRECTNESS_FRONTIER_MODES],
)
@pytest.mark.parametrize(
    ("chunk_name", "episode_ids"),
    _EPISODE_CHUNKS,
    ids=[chunk_name for chunk_name, _ in _EPISODE_CHUNKS],
)
def test_access_benchmark_prints_frontier_summary_for_high_correctness_family(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode_name: str,
    requested_modes: tuple[AccessMode, ...],
    chunk_name: str,
    episode_ids: tuple[str, ...],
) -> None:
    assert mode_name
    assert chunk_name
    monkeypatch.setattr(
        "mind.cli_primitive_cmds.evaluate_access_benchmark",
        lambda *args, **kwargs: _cached_access_benchmark_result(requested_modes, episode_ids),
    )

    exit_code = mind_main(["access", "benchmark"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "backend=sqlite" in output
    assert "storage_scope=isolated" in output
    assert "case_count=10" in output
    assert "run_count=20" in output
    assert "aggregate_count=2" in output
    assert "frontier_count=1" in output
    assert "high_correctness" in output

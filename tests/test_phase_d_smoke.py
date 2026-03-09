from __future__ import annotations

from pathlib import Path

from mind.fixtures.episode_answer_bench import build_episode_answer_bench_v1
from mind.fixtures.retrieval_benchmark import (
    build_retrieval_benchmark_v0,
    build_retrieval_benchmark_v1,
)
from mind.workspace import assert_phase_d_smoke, evaluate_phase_d_smoke


def test_retrieval_benchmark_v0_is_frozen() -> None:
    cases = build_retrieval_benchmark_v0()

    assert len(cases) == 12
    assert {case.case_id for case in cases} == {
        "keyword_showcase_task_episode",
        "keyword_episode_004_summary",
        "keyword_episode_008_reflection",
        "keyword_showcase_schema",
        "time_window_episode_001_pair",
        "time_window_episode_010_pair",
        "time_window_episode_004_reflection",
        "time_window_showcase_trio",
        "vector_showcase_summary",
        "vector_episode_010_summary",
        "vector_episode_020_reflection",
        "vector_showcase_entity",
    }


def test_retrieval_benchmark_v1_is_frozen() -> None:
    cases = build_retrieval_benchmark_v1()

    assert len(cases) == 100
    assert cases[0].case_id == "episode-001_keyword_task_episode"
    assert cases[1].case_id == "episode-001_keyword_summary"
    assert cases[2].case_id == "episode-001_time_window_pair"
    assert cases[3].case_id == "episode-001_vector_summary"
    assert cases[4].case_id == "episode-001_keyword_final_raw"
    assert cases[-1].case_id == "episode-020_keyword_final_raw"


def test_episode_answer_bench_v1_is_frozen() -> None:
    cases = build_episode_answer_bench_v1()

    assert len(cases) == 100
    assert cases[0].case_id == "episode-001_keyword_task_episode"
    assert cases[3].case_id == "episode-001_vector_summary"
    assert cases[-1].case_id == "episode-020_keyword_final_raw"


def test_phase_d_smoke_passes_on_sqlite(tmp_path: Path) -> None:
    result = evaluate_phase_d_smoke(tmp_path / "phase_d_smoke.sqlite3")

    assert_phase_d_smoke(result)
    assert result.phase_d_smoke_pass
    assert result.smoke_case_count == 12
    assert result.benchmark_case_count == 100
    assert result.answer_benchmark_case_count == 100
    assert result.candidate_recall_at_20 == 1.0
    assert result.workspace_gold_fact_coverage == 1.0
    assert result.workspace_slot_discipline_rate == 1.0
    assert result.workspace_source_ref_coverage == 1.0
    assert result.d5_measured is True
    assert result.median_token_cost_ratio <= 0.60
    assert result.raw_top20_task_success_rate == 1.0
    assert result.workspace_task_success_rate == 1.0
    assert result.task_success_drop_pp == 0.0
    assert result.raw_top20_answer_quality_score == 1.0
    assert result.workspace_answer_quality_score == 1.0
    assert result.raw_top20_task_success_proxy_rate == 1.0
    assert result.workspace_task_success_proxy_rate == 1.0
    assert result.task_success_proxy_drop_pp == 0.0
    assert result.d5_pass

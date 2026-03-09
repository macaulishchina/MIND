"""RetrievalBenchmark v0 fixtures for Phase D smoke evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mind.fixtures.golden_episode_set import (
    EpisodeFixture,
    build_core_object_showcase,
    build_golden_episode_set,
)
from mind.primitives.contracts import RetrieveQueryMode

SHOWCASE_SUMMARY_ID = "showcase-summary"


@dataclass(frozen=True)
class RetrievalBenchmarkCase:
    case_id: str
    task_id: str
    query: str | dict[str, Any]
    query_modes: tuple[RetrieveQueryMode, ...]
    filters: dict[str, Any]
    gold_candidate_ids: tuple[str, ...]
    gold_fact_ids: tuple[str, ...]
    slot_limit: int
    vector_scores: tuple[tuple[str, float], ...] = ()


def build_phase_d_seed_objects() -> list[dict[str, Any]]:
    """Return the canonical object seed used by Phase D smoke checks."""

    objects = build_core_object_showcase()
    for episode in build_golden_episode_set():
        objects.extend(episode.objects)
    return objects


def build_retrieval_benchmark_v0() -> list[RetrievalBenchmarkCase]:
    """Return the fixed RetrievalBenchmark v0 set for Phase D smoke."""

    cases = [
        RetrievalBenchmarkCase(
            case_id="keyword_showcase_task_episode",
            task_id="showcase-task",
            query="showcase episode",
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["TaskEpisode"], "task_id": "showcase-task"},
            gold_candidate_ids=("showcase-episode",),
            gold_fact_ids=("showcase-episode",),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id="keyword_episode_004_summary",
            task_id="task-004",
            query="Episode 4 revised corrected replay hints",
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["SummaryNote"]},
            gold_candidate_ids=("episode-004-summary",),
            gold_fact_ids=("episode-004-summary",),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id="keyword_episode_008_reflection",
            task_id="task-008",
            query="Episode 8 stale memory revalidated",
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["ReflectionNote"]},
            gold_candidate_ids=("episode-008-reflection",),
            gold_fact_ids=("episode-008-reflection",),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id="keyword_showcase_schema",
            task_id="showcase-task",
            query="stable procedure semantic",
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["SchemaNote"]},
            gold_candidate_ids=("showcase-schema",),
            gold_fact_ids=("showcase-schema",),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id="time_window_episode_001_pair",
            task_id="task-001",
            query={
                "start": "2026-01-01T01:03:00+00:00",
                "end": "2026-01-01T01:04:30+00:00",
            },
            query_modes=(RetrieveQueryMode.TIME_WINDOW,),
            filters={"object_types": ["TaskEpisode", "SummaryNote"]},
            gold_candidate_ids=("episode-001", "episode-001-summary"),
            gold_fact_ids=("episode-001", "episode-001-summary"),
            slot_limit=2,
        ),
        RetrievalBenchmarkCase(
            case_id="time_window_episode_010_pair",
            task_id="task-010",
            query={
                "start": "2026-01-01T10:08:00+00:00",
                "end": "2026-01-01T10:09:30+00:00",
            },
            query_modes=(RetrieveQueryMode.TIME_WINDOW,),
            filters={"object_types": ["TaskEpisode", "SummaryNote"]},
            gold_candidate_ids=("episode-010", "episode-010-summary"),
            gold_fact_ids=("episode-010", "episode-010-summary"),
            slot_limit=2,
        ),
        RetrievalBenchmarkCase(
            case_id="time_window_episode_004_reflection",
            task_id="task-004",
            query={
                "start": "2026-01-01T04:08:00+00:00",
                "end": "2026-01-01T04:08:30+00:00",
            },
            query_modes=(RetrieveQueryMode.TIME_WINDOW,),
            filters={"object_types": ["ReflectionNote"]},
            gold_candidate_ids=("episode-004-reflection",),
            gold_fact_ids=("episode-004-reflection",),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id="time_window_showcase_trio",
            task_id="showcase-task",
            query={
                "start": "2026-01-01T00:01:00+00:00",
                "end": "2026-01-01T00:01:00+00:00",
            },
            query_modes=(RetrieveQueryMode.TIME_WINDOW,),
            filters={"object_types": ["TaskEpisode", "SummaryNote", "ReflectionNote"]},
            gold_candidate_ids=("showcase-episode", "showcase-summary", "showcase-reflection"),
            gold_fact_ids=("showcase-episode", "showcase-summary", "showcase-reflection"),
            slot_limit=3,
        ),
        RetrievalBenchmarkCase(
            case_id="vector_showcase_summary",
            task_id="showcase-task",
            query="vector:showcase-summary",
            query_modes=(RetrieveQueryMode.VECTOR,),
            filters={"object_types": ["SummaryNote"]},
            gold_candidate_ids=("showcase-summary",),
            gold_fact_ids=("showcase-summary",),
            slot_limit=1,
            vector_scores=(("showcase-summary", 1.0), ("episode-001-summary", 0.25)),
        ),
        RetrievalBenchmarkCase(
            case_id="vector_episode_010_summary",
            task_id="task-010",
            query="vector:episode-010-summary",
            query_modes=(RetrieveQueryMode.VECTOR,),
            filters={"object_types": ["SummaryNote"]},
            gold_candidate_ids=("episode-010-summary",),
            gold_fact_ids=("episode-010-summary",),
            slot_limit=1,
            vector_scores=(("episode-010-summary", 1.0), ("episode-002-summary", 0.2)),
        ),
        RetrievalBenchmarkCase(
            case_id="vector_episode_020_reflection",
            task_id="task-020",
            query="vector:episode-020-reflection",
            query_modes=(RetrieveQueryMode.VECTOR,),
            filters={"object_types": ["ReflectionNote"]},
            gold_candidate_ids=("episode-020-reflection",),
            gold_fact_ids=("episode-020-reflection",),
            slot_limit=1,
            vector_scores=(("episode-020-reflection", 1.0), ("episode-004-reflection", 0.3)),
        ),
        RetrievalBenchmarkCase(
            case_id="vector_showcase_entity",
            task_id="showcase-task",
            query="vector:showcase-entity",
            query_modes=(RetrieveQueryMode.VECTOR,),
            filters={"object_types": ["EntityNode"]},
            gold_candidate_ids=("showcase-entity",),
            gold_fact_ids=("showcase-entity",),
            slot_limit=1,
            vector_scores=(("showcase-entity", 1.0),),
        ),
    ]
    if len(cases) != 12:
        raise RuntimeError(f"RetrievalBenchmark v0 expected 12 cases, got {len(cases)}")
    return cases


def build_retrieval_benchmark_v1() -> list[RetrievalBenchmarkCase]:
    """Return the fixed RetrievalBenchmark v1 set for Phase D benchmark evaluation."""

    cases: list[RetrievalBenchmarkCase] = []
    for episode in build_golden_episode_set():
        cases.extend(_build_episode_benchmark_cases(episode))

    if len(cases) != 100:
        raise RuntimeError(f"RetrievalBenchmark v1 expected 100 cases, got {len(cases)}")
    return cases


def _build_episode_benchmark_cases(episode: EpisodeFixture) -> list[RetrievalBenchmarkCase]:
    episode_object = next(obj for obj in episode.objects if obj["id"] == episode.episode_id)
    summary_id = f"{episode.episode_id}-summary"
    summary_versions = [obj for obj in episode.objects if obj["id"] == summary_id]
    latest_summary = max(summary_versions, key=lambda obj: int(obj["version"]))
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    final_raw_record = raw_records[-1]

    return [
        RetrievalBenchmarkCase(
            case_id=f"{episode.episode_id}_keyword_task_episode",
            task_id=episode.task_id,
            query=(
                f"{episode_object['content']['title']} "
                f"{episode_object['metadata']['result']}"
            ),
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["TaskEpisode"], "task_id": episode.task_id},
            gold_candidate_ids=(episode.episode_id,),
            gold_fact_ids=(episode.episode_id,),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id=f"{episode.episode_id}_keyword_summary",
            task_id=episode.task_id,
            query=str(latest_summary["content"]["summary"]),
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["SummaryNote"]},
            gold_candidate_ids=(summary_id,),
            gold_fact_ids=(summary_id,),
            slot_limit=1,
        ),
        RetrievalBenchmarkCase(
            case_id=f"{episode.episode_id}_time_window_pair",
            task_id=episode.task_id,
            query={
                "start": episode_object["created_at"],
                "end": latest_summary["updated_at"],
            },
            query_modes=(RetrieveQueryMode.TIME_WINDOW,),
            filters={"object_types": ["TaskEpisode", "SummaryNote"]},
            gold_candidate_ids=(episode.episode_id, summary_id),
            gold_fact_ids=(episode.episode_id, summary_id),
            slot_limit=2,
        ),
        RetrievalBenchmarkCase(
            case_id=f"{episode.episode_id}_vector_summary",
            task_id=episode.task_id,
            query=f"vector:{summary_id}",
            query_modes=(RetrieveQueryMode.VECTOR,),
            filters={"object_types": ["SummaryNote"]},
            gold_candidate_ids=(summary_id,),
            gold_fact_ids=(summary_id,),
            slot_limit=1,
            vector_scores=((summary_id, 1.0), (SHOWCASE_SUMMARY_ID, 0.2)),
        ),
        RetrievalBenchmarkCase(
            case_id=f"{episode.episode_id}_keyword_final_raw",
            task_id=episode.task_id,
            query=str(final_raw_record["content"]["text"]),
            query_modes=(RetrieveQueryMode.KEYWORD,),
            filters={"object_types": ["RawRecord"], "episode_id": episode.episode_id},
            gold_candidate_ids=(final_raw_record["id"],),
            gold_fact_ids=(final_raw_record["id"],),
            slot_limit=1,
        ),
    ]

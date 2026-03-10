"""EpisodeAnswerBench v1 fixtures for answer-level workspace evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mind.fixtures.golden_episode_set import EpisodeFixture, build_golden_episode_set


class AnswerKind(StrEnum):
    TASK_RESULT = "task_result"
    SUMMARY = "summary"
    RESULT_AND_SUMMARY = "result_and_summary"
    FINAL_RAW = "final_raw"


@dataclass(frozen=True)
class EpisodeAnswerBenchCase:
    case_id: str
    task_id: str
    episode_id: str
    prompt: str
    answer_kind: AnswerKind
    required_fragments: tuple[str, ...]
    gold_fact_ids: tuple[str, ...]
    gold_memory_refs: tuple[str, ...]
    max_answer_tokens: int


def build_episode_answer_bench_v1() -> list[EpisodeAnswerBenchCase]:
    """Return the fixed EpisodeAnswerBench v1 set aligned with RetrievalBenchmark v1."""

    cases: list[EpisodeAnswerBenchCase] = []
    for episode in build_golden_episode_set():
        cases.extend(_build_episode_answer_cases(episode))

    if len(cases) != 100:
        raise RuntimeError(f"EpisodeAnswerBench v1 expected 100 cases, got {len(cases)}")
    return cases


def _build_episode_answer_cases(episode: EpisodeFixture) -> list[EpisodeAnswerBenchCase]:
    episode_object = next(obj for obj in episode.objects if obj["id"] == episode.episode_id)
    result = str(episode_object["metadata"]["result"])
    summary_id = f"{episode.episode_id}-summary"
    summary_versions = [obj for obj in episode.objects if obj["id"] == summary_id]
    latest_summary = max(summary_versions, key=lambda obj: int(obj["version"]))
    summary_text = str(latest_summary["content"]["summary"])
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    final_raw_record = raw_records[-1]
    final_raw_text = str(final_raw_record["content"]["text"])

    return [
        EpisodeAnswerBenchCase(
            case_id=f"{episode.episode_id}_keyword_task_episode",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id} / {episode.task_id}, what was the task result?",
            answer_kind=AnswerKind.TASK_RESULT,
            required_fragments=(episode.task_id, result),
            gold_fact_ids=(episode.episode_id,),
            gold_memory_refs=(episode.episode_id,),
            max_answer_tokens=8,
        ),
        EpisodeAnswerBenchCase(
            case_id=f"{episode.episode_id}_keyword_summary",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, provide the episode summary.",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=(summary_text,),
            gold_fact_ids=(summary_id,),
            gold_memory_refs=(summary_id,),
            max_answer_tokens=24,
        ),
        EpisodeAnswerBenchCase(
            case_id=f"{episode.episode_id}_time_window_pair",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, provide the task result and summary.",
            answer_kind=AnswerKind.RESULT_AND_SUMMARY,
            required_fragments=(episode.task_id, result, summary_text),
            gold_fact_ids=(episode.episode_id, summary_id),
            gold_memory_refs=(episode.episode_id, summary_id),
            max_answer_tokens=32,
        ),
        EpisodeAnswerBenchCase(
            case_id=f"{episode.episode_id}_vector_summary",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, provide the exact summary.",
            answer_kind=AnswerKind.SUMMARY,
            required_fragments=(summary_text,),
            gold_fact_ids=(summary_id,),
            gold_memory_refs=(summary_id,),
            max_answer_tokens=24,
        ),
        EpisodeAnswerBenchCase(
            case_id=f"{episode.episode_id}_keyword_final_raw",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, quote the final assistant message.",
            answer_kind=AnswerKind.FINAL_RAW,
            required_fragments=(final_raw_text,),
            gold_fact_ids=(final_raw_record["id"],),
            gold_memory_refs=(final_raw_record["id"],),
            max_answer_tokens=24,
        ),
    ]

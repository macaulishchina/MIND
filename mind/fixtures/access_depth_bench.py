"""AccessDepthBench v1 fixtures for runtime access evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from mind.access.contracts import AccessMode, AccessTaskFamily
from mind.fixtures.golden_episode_set import EpisodeFixture, build_golden_episode_set


@dataclass(frozen=True)
class AccessDepthBenchCase:
    case_id: str
    task_id: str
    episode_id: str
    prompt: str
    task_family: AccessTaskFamily
    recommended_mode: AccessMode
    time_budget_ms: int
    hard_constraints: tuple[str, ...]
    required_fragments: tuple[str, ...]
    gold_fact_ids: tuple[str, ...]
    gold_memory_refs: tuple[str, ...]
    max_answer_tokens: int


def build_access_depth_bench_v1() -> list[AccessDepthBenchCase]:
    """Return the fixed AccessDepthBench v1 set for access evaluation."""

    cases: list[AccessDepthBenchCase] = []
    for episode in build_golden_episode_set():
        cases.extend(_build_episode_access_cases(episode))

    if len(cases) != 60:
        raise RuntimeError(f"AccessDepthBench v1 expected 60 cases, got {len(cases)}")
    return cases


def _build_episode_access_cases(episode: EpisodeFixture) -> list[AccessDepthBenchCase]:
    episode_object = next(obj for obj in episode.objects if obj["id"] == episode.episode_id)
    summary = _latest_summary(episode)
    raw_records = [obj for obj in episode.objects if obj["type"] == "RawRecord"]
    final_raw_record = raw_records[-1]
    reflection = next(
        (obj for obj in episode.objects if obj["type"] == "ReflectionNote"),
        None,
    )
    tool_result_record = next(
        (
            obj
            for obj in raw_records
            if str(obj["metadata"]["record_kind"]) == "tool_result"
        ),
        None,
    )

    result = str(episode_object["metadata"]["result"])
    summary_text = str(summary["content"]["summary"])
    final_raw_text = str(final_raw_record["content"]["text"])
    tool_result_text = (
        str(tool_result_record["content"]["result"])
        if tool_result_record is not None
        else None
    )

    high_correctness_required_fragments: tuple[str, ...]
    high_correctness_gold_refs: tuple[str, ...]
    high_correctness_prompt: str
    high_correctness_constraints: tuple[str, ...]
    high_correctness_mode: AccessMode
    high_correctness_budget_ms: int
    high_correctness_tokens: int

    if reflection is not None:
        reflection_text = str(reflection["content"]["summary"])
        high_correctness_required_fragments = (
            result,
            final_raw_text,
            reflection_text,
        )
        high_correctness_gold_refs = (
            episode.episode_id,
            summary["id"],
            final_raw_record["id"],
            reflection["id"],
        )
        high_correctness_prompt = (
            f"For {episode.episode_id}, reconstruct what happened, explain the failure, "
            "and name the follow-up revalidation signal."
        )
        high_correctness_constraints = (
            "must identify whether the episode succeeded or failed",
            "must include the failure or revalidation signal when present",
            "must stay within 48 tokens",
        )
        high_correctness_mode = AccessMode.REFLECTIVE_ACCESS
        high_correctness_budget_ms = 1500
        high_correctness_tokens = 48
    else:
        high_correctness_required_fragments = tuple(
            fragment
            for fragment in (result, final_raw_text, tool_result_text)
            if fragment is not None
        )
        high_correctness_gold_refs = tuple(
            ref
            for ref in (
                episode.episode_id,
                summary["id"],
                final_raw_record["id"],
                tool_result_record["id"] if tool_result_record is not None else None,
            )
            if ref is not None
        )
        high_correctness_prompt = (
            f"For {episode.episode_id}, reconstruct the episode, include any tool result, "
            "and give the final outcome."
        )
        high_correctness_constraints = (
            "must identify whether the episode succeeded or failed",
            "must include tool usage when present",
            "must stay within 40 tokens",
        )
        high_correctness_mode = AccessMode.RECONSTRUCT
        high_correctness_budget_ms = 1200
        high_correctness_tokens = 40

    return [
        AccessDepthBenchCase(
            case_id=f"{episode.episode_id}_flash_result_only",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, reply with only success or failure.",
            task_family=AccessTaskFamily.SPEED_SENSITIVE,
            recommended_mode=AccessMode.FLASH,
            time_budget_ms=150,
            hard_constraints=(
                "must answer with only success or failure",
                "must stay within 2 tokens",
            ),
            required_fragments=(result,),
            gold_fact_ids=(episode.episode_id,),
            gold_memory_refs=(episode.episode_id,),
            max_answer_tokens=2,
        ),
        AccessDepthBenchCase(
            case_id=f"{episode.episode_id}_recall_result_plus_summary",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=f"For {episode.episode_id}, provide the result and the concise summary.",
            task_family=AccessTaskFamily.BALANCED,
            recommended_mode=AccessMode.RECALL,
            time_budget_ms=450,
            hard_constraints=(
                "must include the task result",
                "must include the latest episode summary",
                "must stay within 28 tokens",
            ),
            required_fragments=(result, summary_text),
            gold_fact_ids=(episode.episode_id, summary["id"]),
            gold_memory_refs=(episode.episode_id, summary["id"]),
            max_answer_tokens=28,
        ),
        AccessDepthBenchCase(
            case_id=f"{episode.episode_id}_high_correctness_detailed",
            task_id=episode.task_id,
            episode_id=episode.episode_id,
            prompt=high_correctness_prompt,
            task_family=AccessTaskFamily.HIGH_CORRECTNESS,
            recommended_mode=high_correctness_mode,
            time_budget_ms=high_correctness_budget_ms,
            hard_constraints=high_correctness_constraints,
            required_fragments=high_correctness_required_fragments,
            gold_fact_ids=high_correctness_gold_refs,
            gold_memory_refs=high_correctness_gold_refs,
            max_answer_tokens=high_correctness_tokens,
        ),
    ]


def _latest_summary(episode: EpisodeFixture) -> dict:
    summary_id = f"{episode.episode_id}-summary"
    summary_versions = [obj for obj in episode.objects if obj["id"] == summary_id]
    return max(summary_versions, key=lambda obj: int(obj["version"]))

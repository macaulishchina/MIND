from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from mind.access.benchmark import _generate_answer
from mind.access.contracts import AccessContextKind
from mind.capabilities import (
    AnswerRequest,
    AnswerResponse,
    CapabilityInvocationTrace,
    CapabilityName,
    CapabilityProviderFamily,
)
from mind.fixtures.episode_answer_bench import AnswerKind, EpisodeAnswerBenchCase
from mind.workspace.answer_benchmark import answer_from_raw_topk, answer_from_workspace
from mind.workspace.context_protocol import SerializedContext


def _fixed_clock() -> datetime:
    return datetime(2026, 3, 11, 22, 0, tzinfo=UTC)


def test_workspace_answer_path_delegates_to_capability_service() -> None:
    captured: dict[str, AnswerRequest] = {}

    class _FakeCapabilityService:
        def answer(self, request: AnswerRequest) -> AnswerResponse:
            captured["request"] = request
            return AnswerResponse(
                answer_text="delegated workspace answer",
                support_ids=list(request.support_ids),
                trace=_trace(),
            )

    case = EpisodeAnswerBenchCase(
        case_id="workspace-summary",
        task_id="task-001",
        episode_id="episode-001",
        prompt="For episode-001, provide the summary.",
        answer_kind=AnswerKind.SUMMARY,
        required_fragments=("Episode 1 summary.",),
        gold_fact_ids=("summary-1",),
        gold_memory_refs=("summary-1",),
        max_answer_tokens=24,
    )
    context = SerializedContext(
        protocol="mind.phase_d_context.v1",
        kind="workspace",
        object_ids=("summary-1",),
        text=json.dumps(
            {
                "selected_object_ids": ["summary-1"],
                "slots": [
                    {
                        "summary": "Episode 1 summary.",
                        "source_refs": ["summary-1"],
                    }
                ],
            }
        ),
        token_count=6,
    )

    answer = answer_from_workspace(case, context, capability_service=_FakeCapabilityService())

    assert answer.text == "delegated workspace answer"
    assert answer.support_ids == ("summary-1",)
    assert captured["request"].capability is CapabilityName.ANSWER
    assert captured["request"].question == case.prompt
    assert captured["request"].context_text == "Episode 1 summary."
    assert captured["request"].support_ids == ["summary-1"]


def test_raw_topk_answer_path_delegates_to_capability_service() -> None:
    captured: dict[str, AnswerRequest] = {}

    class _FakeCapabilityService:
        def answer(self, request: AnswerRequest) -> AnswerResponse:
            captured["request"] = request
            return AnswerResponse(
                answer_text="delegated raw answer",
                support_ids=list(request.support_ids),
                trace=_trace(),
            )

    case = EpisodeAnswerBenchCase(
        case_id="raw-task-result",
        task_id="task-001",
        episode_id="episode-001",
        prompt="For episode-001 / task-001, what was the task result?",
        answer_kind=AnswerKind.TASK_RESULT,
        required_fragments=("task-001", "success"),
        gold_fact_ids=("episode-001",),
        gold_memory_refs=("episode-001",),
        max_answer_tokens=8,
    )
    context = SerializedContext(
        protocol="mind.phase_d_context.v1",
        kind="raw_topk",
        object_ids=("episode-001",),
        text=json.dumps(
            {
                "objects": [
                    {
                        "id": "episode-001",
                        "type": "TaskEpisode",
                        "content": {"result_summary": "success"},
                        "metadata": {"result": "success", "task_id": "task-001"},
                    }
                ]
            }
        ),
        token_count=6,
    )

    answer = answer_from_raw_topk(case, context, capability_service=_FakeCapabilityService())

    assert answer.text == "delegated raw answer"
    assert answer.support_ids == ("episode-001",)
    assert captured["request"].question == case.prompt
    assert captured["request"].context_text == "task-001: success"
    assert captured["request"].support_ids == ["episode-001"]


def test_access_benchmark_answer_generation_delegates_to_capability_service() -> None:
    captured: dict[str, AnswerRequest] = {}

    class _FakeCapabilityService:
        def answer(self, request: AnswerRequest) -> AnswerResponse:
            captured["request"] = request
            return AnswerResponse(
                answer_text="success",
                support_ids=list(request.support_ids),
                trace=_trace(),
            )

    case = SimpleNamespace(
        prompt="For episode-001, reply with only success or failure.",
        required_fragments=("success",),
        hard_constraints=("must answer with only success or failure",),
        gold_fact_ids=("episode-001",),
        max_answer_tokens=2,
    )
    context = SerializedContext(
        protocol="mind.gate_context.v1",
        kind="raw_topk",
        object_ids=("episode-001",),
        text=json.dumps(
            {
                "objects": [
                    {
                        "id": "episode-001",
                        "type": "TaskEpisode",
                        "content": {"result_summary": "success"},
                    }
                ]
            }
        ),
        token_count=4,
    )

    answer = _generate_answer(
        case,
        AccessContextKind.RAW_TOPK,
        context,
        capability_service=_FakeCapabilityService(),
    )

    assert answer.text == "success"
    assert answer.support_ids == ("episode-001",)
    assert answer.matched_fragments == ("success",)
    assert captured["request"].question == case.prompt
    assert captured["request"].context_text == "success"
    assert captured["request"].hard_constraints == ["must answer with only success or failure"]
    assert captured["request"].support_ids == ["episode-001"]


def _trace() -> CapabilityInvocationTrace:
    return CapabilityInvocationTrace(
        provider_family=CapabilityProviderFamily.DETERMINISTIC,
        model="deterministic",
        endpoint="local://deterministic",
        version="deterministic-v1",
        started_at=_fixed_clock(),
        completed_at=_fixed_clock(),
        duration_ms=0,
    )

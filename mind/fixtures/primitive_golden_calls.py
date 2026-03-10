"""PrimitiveGoldenCalls v1 fixtures for primitive gate evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mind.fixtures.golden_episode_set import build_core_object_showcase, build_golden_episode_set
from mind.primitives.contracts import (
    PrimitiveErrorCode,
    PrimitiveName,
    PrimitiveOutcome,
)

SHOWCASE_RAW_ID = "showcase-raw"
SHOWCASE_SUMMARY_ID = "showcase-summary"
SHOWCASE_REFLECTION_ID = "showcase-reflection"
SHOWCASE_ENTITY_ID = "showcase-entity"
ARCHIVED_SUMMARY_ID = "gate-archived-summary"
INVALID_SUMMARY_ID = "gate-invalid-summary"


@dataclass(frozen=True)
class PrimitiveGoldenCallExpectation:
    outcome: PrimitiveOutcome
    error_code: PrimitiveErrorCode | None = None
    tags: tuple[str, ...] = ()
    inject_fault: bool = False


@dataclass(frozen=True)
class PrimitiveGoldenCallCase:
    case_id: str
    primitive: PrimitiveName
    request: dict[str, Any]
    context: dict[str, Any]
    expectation: PrimitiveGoldenCallExpectation


def build_primitive_seed_objects() -> list[dict[str, Any]]:
    """Return the base object set used by primitive golden calls."""

    objects = build_core_object_showcase()
    for episode in build_golden_episode_set():
        objects.extend(episode.objects)

    objects.append(
        {
            "id": ARCHIVED_SUMMARY_ID,
            "type": "SummaryNote",
            "content": {"summary": "archived baseline summary"},
            "source_refs": [SHOWCASE_RAW_ID],
            "created_at": "2026-03-09T00:00:00+00:00",
            "updated_at": "2026-03-09T00:00:00+00:00",
            "version": 1,
            "status": "archived",
            "priority": 0.3,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": [SHOWCASE_RAW_ID],
                "compression_ratio_estimate": 0.5,
            },
        }
    )
    objects.append(
        {
            "id": INVALID_SUMMARY_ID,
            "type": "SummaryNote",
            "content": {"summary": "invalid baseline summary"},
            "source_refs": [SHOWCASE_RAW_ID],
            "created_at": "2026-03-09T00:01:00+00:00",
            "updated_at": "2026-03-09T00:01:00+00:00",
            "version": 1,
            "status": "invalid",
            "priority": 0.1,
            "metadata": {
                "summary_scope": "episode",
                "input_refs": [SHOWCASE_RAW_ID],
                "compression_ratio_estimate": 0.5,
            },
        }
    )
    return objects


def build_primitive_golden_calls_v1() -> list[PrimitiveGoldenCallCase]:
    """Return the fixed 200-call primitive evaluation set."""

    calls: list[PrimitiveGoldenCallCase] = []
    calls.extend(_build_success_calls())
    calls.extend(_build_abnormal_calls())
    calls.extend(_build_budget_calls())
    calls.extend(_build_rollback_calls())
    if len(calls) != 200:
        raise RuntimeError(f"PrimitiveGoldenCalls v1 expected 200 cases, got {len(calls)}")
    return calls


def _build_success_calls() -> list[PrimitiveGoldenCallCase]:
    cases: list[PrimitiveGoldenCallCase] = []
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.WRITE_RAW,
            count=10,
            smoke=True,
            request_factory=lambda index: {
                "record_kind": "assistant_message",
                "content": {"text": f"success write raw {index}"},
                "episode_id": f"episode-{(index % 20) + 1:03d}",
                "timestamp_order": 100 + index,
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.READ,
            count=10,
            smoke=True,
            request_factory=lambda index: {
                "object_ids": [SHOWCASE_RAW_ID if index % 2 == 0 else SHOWCASE_SUMMARY_ID],
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.RETRIEVE,
            count=10,
            smoke=True,
            request_factory=lambda index: {
                "query": "showcase summary" if index % 2 == 0 else "task episode success",
                "query_modes": ["keyword"] if index % 3 else ["keyword", "time_window"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": _retrieve_success_filters(index),
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.SUMMARIZE,
            count=10,
            smoke=True,
            request_factory=lambda index: {
                "input_refs": [SHOWCASE_RAW_ID],
                "summary_scope": "episode" if index % 2 == 0 else "object_set",
                "target_kind": f"summary_note_{index}",
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.LINK,
            count=10,
            smoke=True,
            request_factory=lambda index: {
                "src_id": SHOWCASE_ENTITY_ID,
                "dst_id": SHOWCASE_SUMMARY_ID,
                "relation_type": "supports" if index % 2 == 0 else "depends_on",
                "evidence_refs": [SHOWCASE_RAW_ID],
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.REFLECT,
            count=5,
            smoke=True,
            request_factory=lambda index: {
                "episode_id": f"episode-{index + 1:03d}",
                "focus": f"reflection focus {index}",
            },
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.REORGANIZE_SIMPLE,
            count=5,
            smoke=True,
            request_factory=lambda index: {
                "target_refs": [SHOWCASE_SUMMARY_ID],
                "operation": "reprioritize",
                "reason": "boost summary priority" if index % 2 == 0 else "lower stale priority",
            },
        )
    )
    return cases


def _build_abnormal_calls() -> list[PrimitiveGoldenCallCase]:
    cases: list[PrimitiveGoldenCallCase] = []
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.READ,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {"object_ids": [f"missing-object-{index}"]},
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.OBJECT_NOT_FOUND,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.READ,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {"object_ids": [INVALID_SUMMARY_ID]},
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.OBJECT_INACCESSIBLE,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.RETRIEVE,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "query": "vector retrieval unavailable",
                "query_modes": ["vector"],
                "budget": {"max_cost": 5.0, "max_candidates": 5},
                "filters": {},
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.RETRIEVAL_BACKEND_UNAVAILABLE,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.SUMMARIZE,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "input_refs": [SHOWCASE_RAW_ID],
                "summary_scope": "unsupported_scope",
                "target_kind": f"bad_summary_{index}",
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.UNSUPPORTED_SCOPE,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.LINK,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "src_id": SHOWCASE_SUMMARY_ID,
                "dst_id": SHOWCASE_SUMMARY_ID,
                "relation_type": "duplicate",
                "evidence_refs": [SHOWCASE_RAW_ID],
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.SELF_LINK_NOT_ALLOWED,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.LINK,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "src_id": SHOWCASE_ENTITY_ID,
                "dst_id": SHOWCASE_SUMMARY_ID,
                "relation_type": "supports",
                "evidence_refs": [f"missing-evidence-{index}"],
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.EVIDENCE_MISSING,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.REFLECT,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "episode_id": f"missing-episode-{index}",
                "focus": "episode missing",
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.EPISODE_MISSING,
        )
    )
    cases.extend(
        _build_loop_cases(
            primitive=PrimitiveName.REORGANIZE_SIMPLE,
            count=5,
            tag="abnormal",
            request_factory=lambda index: {
                "target_refs": [ARCHIVED_SUMMARY_ID],
                "operation": "archive",
                "reason": "archive again",
            },
            expected_outcome=PrimitiveOutcome.REJECTED,
            expected_error_code=PrimitiveErrorCode.UNSAFE_STATE_TRANSITION,
        )
    )
    return cases


def _build_budget_calls() -> list[PrimitiveGoldenCallCase]:
    primitives = [
        PrimitiveName.WRITE_RAW,
        PrimitiveName.READ,
        PrimitiveName.RETRIEVE,
        PrimitiveName.SUMMARIZE,
        PrimitiveName.LINK,
        PrimitiveName.REFLECT,
        PrimitiveName.REORGANIZE_SIMPLE,
    ]
    return [
        PrimitiveGoldenCallCase(
            case_id=f"budget-{index:03d}",
            primitive=primitive,
            request=_budget_request(primitive, index),
            context=_context(f"budget-{index:03d}", budget_limit=0.0),
            expectation=PrimitiveGoldenCallExpectation(
                outcome=PrimitiveOutcome.REJECTED,
                error_code=PrimitiveErrorCode.BUDGET_EXHAUSTED,
                tags=("budget",),
            ),
        )
        for index, primitive in enumerate((primitives * 8)[:50], start=1)
    ]


def _build_rollback_calls() -> list[PrimitiveGoldenCallCase]:
    primitives = [
        PrimitiveName.WRITE_RAW,
        PrimitiveName.SUMMARIZE,
        PrimitiveName.LINK,
        PrimitiveName.REFLECT,
        PrimitiveName.REORGANIZE_SIMPLE,
    ]
    return [
        PrimitiveGoldenCallCase(
            case_id=f"rollback-{index:03d}",
            primitive=primitive,
            request=_rollback_request(primitive, index),
            context=_context(f"rollback-{index:03d}", budget_limit=100.0),
            expectation=PrimitiveGoldenCallExpectation(
                outcome=PrimitiveOutcome.ROLLED_BACK,
                error_code=PrimitiveErrorCode.INTERNAL_ERROR,
                tags=("rollback",),
                inject_fault=True,
            ),
        )
        for index, primitive in enumerate((primitives * 10)[:50], start=1)
    ]


def _build_loop_cases(
    *,
    primitive: PrimitiveName,
    count: int,
    request_factory: Callable[[int], dict[str, Any]],
    smoke: bool = False,
    tag: str = "success",
    expected_outcome: PrimitiveOutcome = PrimitiveOutcome.SUCCESS,
    expected_error_code: PrimitiveErrorCode | None = None,
) -> list[PrimitiveGoldenCallCase]:
    cases: list[PrimitiveGoldenCallCase] = []
    for index in range(count):
        tags = (tag, "smoke") if smoke and index == 0 else (tag,)
        cases.append(
            PrimitiveGoldenCallCase(
                case_id=f"{tag}-{primitive.value}-{index + 1:03d}",
                primitive=primitive,
                request=request_factory(index),
                context=_context(f"{tag}-{primitive.value}-{index + 1:03d}", budget_limit=100.0),
                expectation=PrimitiveGoldenCallExpectation(
                    outcome=expected_outcome,
                    error_code=expected_error_code,
                    tags=tags,
                ),
            )
        )
    return cases


def _budget_request(primitive: PrimitiveName, index: int) -> dict[str, Any]:
    if primitive is PrimitiveName.WRITE_RAW:
        return {
            "record_kind": "assistant_message",
            "content": {"text": f"budget write raw {index}"},
            "episode_id": f"episode-{(index % 20) + 1:03d}",
            "timestamp_order": 500 + index,
        }
    if primitive is PrimitiveName.READ:
        return {"object_ids": [SHOWCASE_RAW_ID]}
    if primitive is PrimitiveName.RETRIEVE:
        return {
            "query": "showcase summary",
            "query_modes": ["keyword"],
            "budget": {"max_cost": 5.0, "max_candidates": 5},
            "filters": {"object_types": ["SummaryNote"]},
        }
    if primitive is PrimitiveName.SUMMARIZE:
        return {
            "input_refs": [SHOWCASE_RAW_ID],
            "summary_scope": "episode",
            "target_kind": f"budget_summary_{index}",
        }
    if primitive is PrimitiveName.LINK:
        return {
            "src_id": SHOWCASE_ENTITY_ID,
            "dst_id": SHOWCASE_SUMMARY_ID,
            "relation_type": "supports",
            "evidence_refs": [SHOWCASE_RAW_ID],
        }
    if primitive is PrimitiveName.REFLECT:
        return {
            "episode_id": f"episode-{(index % 20) + 1:03d}",
            "focus": "budget reflection",
        }
    return {
        "target_refs": [SHOWCASE_SUMMARY_ID],
        "operation": "reprioritize",
        "reason": "boost summary priority",
    }


def _rollback_request(primitive: PrimitiveName, index: int) -> dict[str, Any]:
    if primitive is PrimitiveName.WRITE_RAW:
        return {
            "record_kind": "assistant_message",
            "content": {"text": f"rollback write raw {index}"},
            "episode_id": f"episode-{(index % 20) + 1:03d}",
            "timestamp_order": 800 + index,
        }
    if primitive is PrimitiveName.SUMMARIZE:
        return {
            "input_refs": [SHOWCASE_RAW_ID],
            "summary_scope": "episode",
            "target_kind": f"rollback_summary_{index}",
        }
    if primitive is PrimitiveName.LINK:
        return {
            "src_id": SHOWCASE_ENTITY_ID,
            "dst_id": SHOWCASE_SUMMARY_ID,
            "relation_type": "supports",
            "evidence_refs": [SHOWCASE_RAW_ID],
        }
    if primitive is PrimitiveName.REFLECT:
        return {
            "episode_id": f"episode-{(index % 20) + 1:03d}",
            "focus": f"rollback reflection {index}",
        }
    return {
        "target_refs": [SHOWCASE_SUMMARY_ID, SHOWCASE_REFLECTION_ID],
        "operation": "synthesize_schema",
        "reason": f"rollback synthesize schema {index}",
    }


def _retrieve_success_filters(index: int) -> dict[str, Any]:
    if index % 2 == 0:
        return {"object_types": ["SummaryNote"]}
    return {
        "episode_id": f"episode-{(index % 20) + 1:03d}",
        "object_types": ["TaskEpisode", "SummaryNote"],
    }


def _context(case_id: str, *, budget_limit: float) -> dict[str, Any]:
    return {
        "actor": "phase-c-golden",
        "budget_scope_id": case_id,
        "budget_limit": budget_limit,
    }

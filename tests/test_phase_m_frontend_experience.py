from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from mind.app.context import SessionContext
from mind.app.contracts import AppRequest
from mind.frontend import (
    FrontendAccessRequest,
    FrontendOfflineSubmitRequest,
    build_frontend_access_result,
    build_frontend_experience_catalog,
    build_frontend_gate_demo_page,
    build_frontend_ingest_result,
    build_frontend_offline_submit_result,
    build_frontend_retrieve_result,
)
from mind.offline_jobs import OfflineJobKind


def _request(input_payload: dict[str, Any], *, request_id: str) -> AppRequest:
    return AppRequest(
        request_id=request_id,
        session=SessionContext(session_id="phase-m-front-session", request_id=request_id),
        input=input_payload,
    )


def test_frontend_experience_catalog_projects_frozen_bench() -> None:
    page = build_frontend_experience_catalog()

    assert page.bench_version == "FrontendExperienceBench v1"
    assert [entry.entrypoint.value for entry in page.entries] == [
        "ingest",
        "retrieve",
        "access",
        "offline",
        "gate_demo",
    ]

    gate_demo = next(entry for entry in page.entries if entry.entrypoint.value == "gate_demo")
    assert gate_demo.requires_dev_mode is False
    assert gate_demo.supported_viewports == ["desktop", "mobile"]
    assert len(gate_demo.scenario_ids) == 2


def test_frontend_gate_demo_page_projects_summary_surface() -> None:
    page = build_frontend_gate_demo_page()

    assert page.page_version == "FrontendGateDemoPage v1"
    assert [entry.kind.value for entry in page.entries] == [
        "demo",
        "demo",
        "demo",
        "gate",
        "gate",
        "report",
        "report",
    ]
    assert all(entry.supported_viewports == ["desktop", "mobile"] for entry in page.entries)
    assert all(len(entry.scenario_ids) == 2 for entry in page.entries)


def test_frontend_access_request_accepts_focus_alias() -> None:
    request = FrontendAccessRequest(query="what happened", depth="focus", explain=True)

    assert request.depth == "focus"
    assert request.explain is True


def test_frontend_offline_submit_request_validates_payload_shape() -> None:
    with pytest.raises(ValueError, match="episode_id"):
        FrontendOfflineSubmitRequest(
            job_kind=OfflineJobKind.REFLECT_EPISODE,
            payload={"focus": "missing episode"},
        )

    request = FrontendOfflineSubmitRequest(
        job_kind=OfflineJobKind.PROMOTE_SCHEMA,
        payload={"target_refs": ["ref-1", "ref-2"], "reason": "repeat pattern"},
    )

    assert request.job_kind is OfflineJobKind.PROMOTE_SCHEMA
    assert request.priority == 0.5


def test_frontend_access_result_aliases_recall_to_focus() -> None:
    result = build_frontend_access_result(
        {
            "resolved_mode": "recall",
            "context_kind": "workspace",
            "context_object_ids": ["obj-1"],
            "candidate_ids": ["obj-1"],
            "candidate_summaries": [
                {
                    "object_id": "obj-1",
                    "type": "RawRecord",
                    "episode_id": "ep-1",
                    "content_preview": "remember me",
                    "score": 0.91,
                }
            ],
            "selected_object_ids": ["obj-1"],
            "selected_summaries": [
                {
                    "object_id": "obj-1",
                    "type": "RawRecord",
                    "episode_id": "ep-1",
                    "content_preview": "remember me",
                }
            ],
            "answer_text": "remember me",
            "answer_support_ids": ["obj-1"],
            "answer_trace": {
                "provider_family": "deterministic",
                "fallback_used": False,
            },
            "trace": {"events": [{"summary": "recall completed with 1 candidate"}]},
        }
    )

    assert result.resolved_depth == "focus"
    assert result.candidate_count == 1
    assert result.selected_count == 1
    assert result.summary == "remember me"
    assert result.answer is not None
    assert result.answer.text == "remember me"
    assert result.answer.support_ids == ["obj-1"]
    assert result.answer.trace is not None
    assert result.answer.trace.provider_family == "deterministic"
    assert result.answer.trace.request_text is None


def test_frontend_access_projection_includes_llm_request_text_for_web_access() -> None:
    result = build_frontend_access_result(
        {
            "resolved_mode": "recall",
            "context_kind": "workspace",
            "context_object_ids": ["obj-1"],
            "context_text": "{\"kind\":\"workspace\",\"slots\":[{\"summary\":\"\\u4f60\\u597d\\uff0c\\u4eca\\u5929\\u4e0b\\u96e8\\uff0c\\u8bb0\\u5f97\\u5e26\\u4f1e\\u3002\"}]}",
            "candidate_ids": ["obj-1"],
            "candidate_summaries": [
                {
                    "object_id": "obj-1",
                    "type": "RawRecord",
                    "episode_id": "ep-1",
                    "content_preview": "你好，今天下雨，记得带伞。",
                    "score": 0.91,
                }
            ],
            "selected_object_ids": ["obj-1"],
            "selected_summaries": [
                {
                    "object_id": "obj-1",
                    "type": "RawRecord",
                    "episode_id": "ep-1",
                    "content_preview": "你好，今天下雨，记得带伞。",
                }
            ],
            "answer_text": "你好，今天记得带伞。",
            "answer_support_ids": ["obj-1"],
            "answer_trace": {
                "provider_family": "openai",
                "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "fallback_used": False,
                "response_text": "{\"answer_text\":\"你好，今天记得带伞。\"}",
            },
            "trace": {"events": [{"summary": "recall completed with 1 candidate"}]},
        },
        frontend_request=FrontendAccessRequest(query="你好", depth="focus"),
        runtime_provider="openai",
    )

    assert result.answer is not None
    assert result.answer.trace is not None
    assert result.answer.trace.request_text is not None
    assert "You are the MIND answer capability." in result.answer.trace.request_text
    assert "Question: 你好" in result.answer.trace.request_text
    assert '"obj-1"' in result.answer.trace.request_text
    assert "你好，今天下雨，记得带伞。" in result.answer.trace.request_text
    assert "\\u4f60\\u597d" not in result.answer.trace.request_text
    assert result.answer.trace.response_text is not None
    assert "你好，今天记得带伞。" in result.answer.trace.response_text
    assert result.answer.trace.exchanges[0].order == 1
    assert result.answer.trace.exchanges[0].request_text is not None
    assert result.answer.trace.exchanges[0].response_text is not None


def test_frontend_access_projection_preserves_llm_exchange_order() -> None:
    result = build_frontend_access_result(
        {
            "resolved_mode": "recall",
            "context_kind": "workspace",
            "context_object_ids": ["obj-1"],
            "candidate_ids": ["obj-1"],
            "selected_object_ids": ["obj-1"],
            "answer_text": "最终回答",
            "answer_support_ids": ["obj-1"],
            "answer_trace": {
                "provider_family": "openai",
                "endpoint": "https://api.deepseek.com/v1/chat/completions",
                "fallback_used": False,
                "exchanges": [
                    {
                        "request_text": "第一轮请求",
                        "response_text": "第一轮回答",
                    },
                    {
                        "request_text": "第二轮请求",
                        "response_text": "第二轮回答",
                    },
                ],
            },
            "trace": {"events": [{"summary": "recall completed with 1 candidate"}]},
        },
        frontend_request=FrontendAccessRequest(query="你好", depth="focus"),
        runtime_provider="openai",
    )

    assert result.answer is not None
    assert result.answer.trace is not None
    assert [item.order for item in result.answer.trace.exchanges] == [1, 2]
    assert result.answer.trace.exchanges[0].request_text == "第一轮请求"
    assert result.answer.trace.exchanges[1].response_text == "第二轮回答"


def test_frontend_experience_projections_use_real_app_services(tmp_path: Path) -> None:
    from mind.app.registry import build_app_registry
    from mind.cli_config import resolve_cli_config

    config = resolve_cli_config(
        backend="sqlite",
        sqlite_path=str(tmp_path / "phase_m_frontend_experience.sqlite3"),
        allow_sqlite=True,
    )

    episode_id = f"phase-m-ep-{uuid.uuid4().hex[:8]}"
    with build_app_registry(config) as registry:
        ingest_response = registry.memory_ingest_service.remember(
            _request(
                {
                    "content": "frontend experience seed",
                    "episode_id": episode_id,
                    "timestamp_order": 1,
                },
                request_id="req-front-ingest",
            )
        )
        ingest_view = build_frontend_ingest_result(ingest_response)

        retrieve_response = registry.memory_query_service.recall(
            _request(
                {
                    "query": "frontend experience",
                    "filters": {"episode_id": episode_id},
                    "max_candidates": 5,
                },
                request_id="req-front-retrieve",
            )
        )
        retrieve_view = build_frontend_retrieve_result(retrieve_response)

        access_response = registry.memory_access_service.ask(
            _request(
                {
                    "query": "what did I store for frontend experience?",
                    "episode_id": episode_id,
                },
                request_id="req-front-access",
            )
        )
        access_view = build_frontend_access_result(access_response)

        offline_response = registry.offline_job_app_service.submit_job(
            _request(
                {
                    "job_kind": "reflect_episode",
                    "payload": {
                        "episode_id": episode_id,
                        "focus": "phase m frontend reflection",
                    },
                },
                request_id="req-front-offline",
            )
        )
        offline_view = build_frontend_offline_submit_result(offline_response)

    assert ingest_view.object_id.startswith("raw-")
    assert ingest_view.episode_id == episode_id
    assert ingest_view.trace_ref is not None

    assert retrieve_view.candidate_count >= 1
    assert retrieve_view.candidates[0].object_id == ingest_view.object_id
    assert retrieve_view.trace_ref is not None

    assert access_view.resolved_depth in {"flash", "focus", "reconstruct", "reflective_access"}
    assert access_view.candidate_count >= 1
    assert access_view.answer is not None
    assert access_view.answer.text
    assert access_view.answer.support_ids
    assert any(item.object_id == ingest_view.object_id for item in access_view.candidate_objects)
    assert access_view.trace_ref is not None

    assert offline_view.job_id.startswith("offline-job-")
    assert offline_view.status == "pending"

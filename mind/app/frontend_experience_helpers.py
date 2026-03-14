"""Internal projection helpers for frontend experience surfaces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mind.app.contracts import AppResponse
    from mind.app.frontend_experience import (
        FrontendAccessAnswerView,
        FrontendAccessEvidenceView,
        FrontendAccessLlmExchangeView,
        FrontendAccessRequest,
        FrontendGateDemoPage,
        FrontendRetrieveCandidateView,
    )
    from mind.fixtures import FrontendExperienceScenario


def build_frontend_gate_demo_page(
    scenarios: list[FrontendExperienceScenario] | None = None,
) -> FrontendGateDemoPage:
    """Project the frozen gate/demo frontend summary surface."""
    from mind.app.frontend_experience import (
        FrontendGateDemoEntry as _Entry,
    )
    from mind.app.frontend_experience import (
        FrontendGateDemoEntryKind as _Kind,
    )
    from mind.app.frontend_experience import (
        FrontendGateDemoPage as _Page,
    )
    from mind.fixtures import build_frontend_experience_bench_v1

    frozen_scenarios = scenarios or build_frontend_experience_bench_v1()
    gate_demo_scenarios = [
        scenario
        for scenario in frozen_scenarios
        if scenario.category == "experience" and scenario.entrypoint == "gate_demo"
    ]
    if not gate_demo_scenarios:
        raise RuntimeError("missing frontend experience bench entrypoint gate_demo")

    supported_viewports = _viewport_order({scenario.viewport for scenario in gate_demo_scenarios})
    scenario_ids = [scenario.scenario_id for scenario in gate_demo_scenarios]

    return _Page(
        page_version="FrontendGateDemoPage v1",
        entries=[
            _Entry(
                entry_id="demo_memory_flow",
                kind=_Kind.DEMO,
                title="Memory Flow Demo",
                summary=(
                    "Summarize the guided ingest/read path that mirrors the product memory "
                    "boundary without exposing raw developer commands."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="demo_access_flow",
                kind=_Kind.DEMO,
                title="Access Flow Demo",
                summary=(
                    "Summarize the access walkthrough that explains resolved depth, "
                    "context shape, and evidence selection."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="demo_offline_flow",
                kind=_Kind.DEMO,
                title="Offline Flow Demo",
                summary=(
                    "Summarize the offline submission path for reflection or schema "
                    "promotion without changing runtime semantics implicitly."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="gate_capability_readiness",
                kind=_Kind.GATE,
                title="Capability Readiness Gate",
                summary=(
                    "Expose the capability-layer readiness checkpoint as a stable frontend "
                    "summary instead of a developer-facing phase command."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="gate_telemetry_readiness",
                kind=_Kind.GATE,
                title="Telemetry Readiness Gate",
                summary=(
                    "Expose telemetry coverage and debug-safety readiness as a frontend "
                    "summary for internal review."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="report_provider_compatibility",
                kind=_Kind.REPORT,
                title="Provider Compatibility Report",
                summary=(
                    "Summarize provider compatibility artifacts for the capability layer "
                    "without binding the UI to raw report file formats."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            _Entry(
                entry_id="report_telemetry_audit",
                kind=_Kind.REPORT,
                title="Telemetry Audit Report",
                summary=(
                    "Summarize trace, delta, and timeline audit artifacts behind the "
                    "Phase L telemetry readiness checks."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
        ],
    )


def _coerce_ok_payload(
    response_or_payload: AppResponse | Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    from mind.app.contracts import AppResponse as _AppResponse
    from mind.app.contracts import AppStatus as _AppStatus

    if isinstance(response_or_payload, _AppResponse):
        if response_or_payload.status is not _AppStatus.OK or response_or_payload.result is None:
            raise ValueError("frontend projections require an AppResponse with status=ok")
        return dict(response_or_payload.result), response_or_payload.trace_ref
    return dict(response_or_payload), None


def _project_evidence_collection(
    raw_summaries: Any,
    *,
    candidate_ids: list[str],
    fallback_scores: list[float] | None = None,
) -> list[FrontendAccessEvidenceView]:
    from mind.app.frontend_experience import FrontendAccessEvidenceView as _View

    fallback_scores = fallback_scores or []
    if not raw_summaries:
        return [
            _View(
                object_id=object_id,
                object_type="unknown",
                score=fallback_scores[index] if index < len(fallback_scores) else None,
            )
            for index, object_id in enumerate(candidate_ids)
        ]

    views: list[_View] = []
    for index, raw_summary in enumerate(raw_summaries):
        if not isinstance(raw_summary, Mapping):
            continue
        object_id = str(
            raw_summary.get("object_id")
            or (candidate_ids[index] if index < len(candidate_ids) else "")
        )
        if not object_id:
            continue
        raw_score = raw_summary.get("score")
        score = (
            float(raw_score)
            if isinstance(raw_score, int | float)
            else (fallback_scores[index] if index < len(fallback_scores) else None)
        )
        views.append(
            _View(
                object_id=object_id,
                object_type=str(
                    raw_summary.get("object_type") or raw_summary.get("type") or "unknown"
                ),
                episode_id=(
                    str(raw_summary["episode_id"])
                    if raw_summary.get("episode_id") is not None
                    else None
                ),
                score=score,
                preview=(
                    str(raw_summary["content_preview"])
                    if raw_summary.get("content_preview") is not None
                    else None
                ),
            )
        )
    return views


def _project_access_answer(
    payload: Mapping[str, Any],
    *,
    fallback_support_ids: list[str],
    frontend_request: FrontendAccessRequest | None = None,
    runtime_provider: str | None = None,
) -> FrontendAccessAnswerView | None:
    from mind.app.frontend_experience import (
        FrontendAccessAnswerTraceView as _TraceView,
    )
    from mind.app.frontend_experience import (
        FrontendAccessAnswerView as _AnswerView,
    )

    raw_text = payload.get("answer_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None

    raw_trace = payload.get("answer_trace")
    answer_trace: _TraceView | None = None
    provider_family = _resolve_frontend_access_provider_family(
        raw_trace if isinstance(raw_trace, Mapping) else None,
        runtime_provider=runtime_provider,
    )
    request_text = (
        _format_frontend_access_trace_text(raw_trace.get("request_text"))
        if isinstance(raw_trace, Mapping)
        else None
    ) or _build_frontend_access_llm_request_text(
        provider_family=provider_family,
        frontend_request=frontend_request,
        payload=payload,
        fallback_support_ids=fallback_support_ids,
    )
    response_text = (
        _format_frontend_access_trace_text(raw_trace.get("response_text"))
        if isinstance(raw_trace, Mapping)
        else None
    )
    exchanges = _build_frontend_access_llm_exchanges(
        raw_trace if isinstance(raw_trace, Mapping) else None,
        request_text=request_text,
        response_text=response_text,
    )
    if isinstance(raw_trace, Mapping):
        fallback_reason = raw_trace.get("fallback_reason")
        answer_trace = _TraceView(
            provider_family=(
                str(raw_trace["provider_family"])
                if raw_trace.get("provider_family") is not None
                else None
            ),
            endpoint=(
                str(raw_trace["endpoint"]) if raw_trace.get("endpoint") is not None else None
            ),
            fallback_used=bool(raw_trace.get("fallback_used")),
            fallback_reason=(
                str(fallback_reason)
                if isinstance(fallback_reason, str) and fallback_reason.strip()
                else None
            ),
            request_text=request_text,
            response_text=response_text,
            exchanges=exchanges,
        )
    elif request_text is not None or response_text is not None:
        answer_trace = _TraceView(
            provider_family=provider_family,
            request_text=request_text,
            response_text=response_text,
            exchanges=exchanges,
        )

    raw_support_ids = payload.get("answer_support_ids") or fallback_support_ids
    return _AnswerView(
        text=raw_text,
        support_ids=[str(item) for item in raw_support_ids],
        trace=answer_trace,
    )


def _resolve_frontend_access_provider_family(
    raw_trace: Mapping[str, Any] | None,
    *,
    runtime_provider: str | None,
) -> str | None:
    if raw_trace is not None and raw_trace.get("provider_family") is not None:
        raw_family = str(raw_trace["provider_family"]).strip()
        if raw_family in {"openai", "claude", "gemini"}:
            return raw_family
    provider = str(runtime_provider or "").strip().lower()
    aliases = {
        "openai": "openai",
        "claude": "claude",
        "anthropic": "claude",
        "gemini": "gemini",
        "google": "gemini",
    }
    return aliases.get(provider)


def _build_frontend_access_llm_request_text(
    *,
    provider_family: str | None,
    frontend_request: FrontendAccessRequest | None,
    payload: Mapping[str, Any],
    fallback_support_ids: list[str],
) -> str | None:
    if provider_family not in {"openai", "claude", "gemini"} or frontend_request is None:
        return None
    context_text = str(payload.get("context_text") or "").strip()
    if not context_text:
        return None
    support_ids = [
        str(item) for item in (payload.get("answer_support_ids") or fallback_support_ids or ())
    ]
    if provider_family == "openai":
        response_line = "Return JSON only."
    else:
        response_line = "Return JSON only with key answer_text."
    return (
        "You are the MIND answer capability.\n"
        f"{response_line}\n"
        f"Question: {frontend_request.query}\n"
        f"Hard constraints: {json.dumps([], ensure_ascii=False)}\n"
        f"Support ids: {json.dumps(support_ids, ensure_ascii=False)}\n"
        "Context text:\n"
        f"{_format_frontend_access_request_text(context_text)}"
    )


def _build_frontend_access_llm_exchanges(
    raw_trace: Mapping[str, Any] | None,
    *,
    request_text: str | None,
    response_text: str | None,
) -> list[FrontendAccessLlmExchangeView]:
    from mind.app.frontend_experience import FrontendAccessLlmExchangeView as _ExchangeView

    if isinstance(raw_trace, Mapping):
        raw_exchanges = raw_trace.get("exchanges")
        if isinstance(raw_exchanges, list):
            exchanges: list[_ExchangeView] = []
            for index, item in enumerate(raw_exchanges, start=1):
                if not isinstance(item, Mapping):
                    continue
                exchange_request = _format_frontend_access_trace_text(item.get("request_text"))
                exchange_response = _format_frontend_access_trace_text(item.get("response_text"))
                if not exchange_request and not exchange_response:
                    continue
                exchanges.append(
                    _ExchangeView(
                        order=index,
                        request_text=exchange_request,
                        response_text=exchange_response,
                    )
                )
            if exchanges:
                return exchanges
    if request_text is None and response_text is None:
        return []
    return [
        _ExchangeView(
            order=1,
            request_text=request_text,
            response_text=response_text,
        )
    ]


def _format_frontend_access_trace_text(raw_text: Any) -> str | None:
    if not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return text
    if isinstance(parsed, dict | list):
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    if isinstance(parsed, str):
        return parsed
    return str(parsed)


def _format_frontend_access_request_text(context_text: str) -> str:
    try:
        parsed = json.loads(context_text)
    except (TypeError, ValueError):
        return context_text
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def _project_retrieve_candidates(
    raw_summaries: Any,
    *,
    candidate_ids: list[str],
    fallback_scores: list[float] | None = None,
) -> list[FrontendRetrieveCandidateView]:
    from mind.app.frontend_experience import FrontendRetrieveCandidateView as _View

    fallback_scores = fallback_scores or []
    if not raw_summaries:
        return [
            _View(
                object_id=object_id,
                object_type="unknown",
                score=fallback_scores[index] if index < len(fallback_scores) else None,
            )
            for index, object_id in enumerate(candidate_ids)
        ]

    views: list[_View] = []
    for index, raw_summary in enumerate(raw_summaries):
        if not isinstance(raw_summary, Mapping):
            continue
        object_id = str(
            raw_summary.get("object_id")
            or (candidate_ids[index] if index < len(candidate_ids) else "")
        )
        if not object_id:
            continue
        raw_score = raw_summary.get("score")
        score = (
            float(raw_score)
            if isinstance(raw_score, int | float)
            else (fallback_scores[index] if index < len(fallback_scores) else None)
        )
        views.append(
            _View(
                object_id=object_id,
                object_type=str(
                    raw_summary.get("object_type") or raw_summary.get("type") or "unknown"
                ),
                score=score,
                content_preview=(
                    str(raw_summary["content_preview"])
                    if raw_summary.get("content_preview") is not None
                    else None
                ),
            )
        )
    return views


def _frontend_access_depth(raw_depth: Any) -> str:
    normalized = str(raw_depth or "unknown")
    if normalized == "recall":
        return "focus"
    return normalized


def _viewport_order(viewports: set[str]) -> list[str]:
    ordering = {"desktop": 0, "mobile": 1, "shared": 2}
    return sorted(viewports, key=lambda viewport: (ordering.get(viewport, 99), viewport))

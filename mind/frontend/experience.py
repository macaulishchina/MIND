"""Frontend-facing experience surface contracts for Phase M prework."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from mind.app.contracts import AppResponse, AppStatus
from mind.fixtures import FrontendExperienceScenario, build_frontend_experience_bench_v1
from mind.offline_jobs import (
    OfflineJobKind,
    PromoteSchemaJobPayload,
    ReflectEpisodeJobPayload,
)

from .contracts import FrontendModel


class FrontendExperienceEntrypoint(StrEnum):
    """Frozen top-level experience entrypoints for Phase M."""

    INGEST = "ingest"
    RETRIEVE = "retrieve"
    ACCESS = "access"
    OFFLINE = "offline"
    GATE_DEMO = "gate_demo"


class FrontendIngestRequest(FrontendModel):
    """Frontend-facing ingest submission contract."""

    content: str | dict[str, Any]
    episode_id: str | None = None
    timestamp_order: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def enforce_non_empty_content(self) -> FrontendIngestRequest:
        if isinstance(self.content, str) and not self.content.strip():
            raise ValueError("frontend ingest requests require non-empty content")
        if isinstance(self.content, dict) and not self.content:
            raise ValueError("frontend ingest requests require non-empty content")
        return self


class FrontendIngestResult(FrontendModel):
    """Frontend-facing ingest result projection."""

    object_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    provenance_id: str | None = None
    trace_ref: str | None = None


class FrontendRetrieveRequest(FrontendModel):
    """Frontend-facing retrieval request contract."""

    query: str = Field(min_length=1)
    episode_id: str | None = None
    max_candidates: int = Field(default=10, ge=1, le=50)
    query_modes: list[str] = Field(default_factory=lambda: ["keyword"], min_length=1)


class FrontendRetrieveCandidateView(FrontendModel):
    """Frontend-facing retrieval candidate summary."""

    object_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    score: float | None = None
    content_preview: str | None = None


class FrontendRetrieveResult(FrontendModel):
    """Frontend-facing retrieval result projection."""

    candidate_count: int = Field(ge=0)
    evidence_summary: str | dict[str, Any] | None = None
    candidates: list[FrontendRetrieveCandidateView] = Field(default_factory=list)
    trace_ref: str | None = None

    @model_validator(mode="after")
    def enforce_candidate_count(self) -> FrontendRetrieveResult:
        if self.candidate_count != len(self.candidates):
            raise ValueError("candidate_count must match candidate list length")
        return self


class FrontendAccessRequest(FrontendModel):
    """Frontend-facing access submission contract."""

    query: str = Field(min_length=1)
    depth: str = Field(default="auto", min_length=1)
    episode_id: str | None = None
    task_id: str | None = None
    query_modes: list[str] = Field(default_factory=lambda: ["keyword"], min_length=1)
    explain: bool = False

    @model_validator(mode="after")
    def enforce_known_depth(self) -> FrontendAccessRequest:
        allowed_depths = {
            "auto",
            "flash",
            "focus",
            "recall",
            "reconstruct",
            "reflective_access",
        }
        if self.depth not in allowed_depths:
            raise ValueError(
                "frontend access depth must be one of "
                "auto/flash/focus/recall/reconstruct/reflective_access"
            )
        return self


class FrontendAccessEvidenceView(FrontendModel):
    """Frontend-facing evidence summary used by retrieval/access surfaces."""

    object_id: str = Field(min_length=1)
    object_type: str = Field(min_length=1)
    episode_id: str | None = None
    score: float | None = None
    preview: str | None = None


class FrontendAccessLlmExchangeView(FrontendModel):
    """One ordered request/response exchange projected for the web frontend."""

    order: int = Field(ge=1)
    request_text: str | None = None
    response_text: str | None = None


class FrontendAccessAnswerTraceView(FrontendModel):
    """Stable frontend-facing answer trace subset."""

    provider_family: str | None = None
    endpoint: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    request_text: str | None = None
    response_text: str | None = None
    exchanges: list[FrontendAccessLlmExchangeView] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_fallback_reason(self) -> FrontendAccessAnswerTraceView:
        if self.fallback_reason and not self.fallback_used:
            raise ValueError("fallback_reason requires fallback_used")
        return self


class FrontendAccessAnswerView(FrontendModel):
    """Stable frontend-facing answer projection."""

    text: str = Field(min_length=1)
    support_ids: list[str] = Field(default_factory=list)
    trace: FrontendAccessAnswerTraceView | None = None


class FrontendAccessResult(FrontendModel):
    """Frontend-facing access result projection."""

    resolved_depth: str = Field(min_length=1)
    context_kind: str = Field(min_length=1)
    context_object_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    summary: str = Field(min_length=1)
    answer: FrontendAccessAnswerView | None = None
    candidate_objects: list[FrontendAccessEvidenceView] = Field(default_factory=list)
    selected_objects: list[FrontendAccessEvidenceView] = Field(default_factory=list)
    trace_ref: str | None = None

    @model_validator(mode="after")
    def enforce_counts(self) -> FrontendAccessResult:
        if self.candidate_count != len(self.candidate_objects):
            raise ValueError("candidate_count must match candidate_objects length")
        if self.selected_count != len(self.selected_objects):
            raise ValueError("selected_count must match selected_objects length")
        return self


class FrontendOfflineSubmitRequest(FrontendModel):
    """Frontend-facing offline job submission contract."""

    job_kind: OfflineJobKind
    payload: dict[str, Any]
    priority: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def enforce_payload_shape(self) -> FrontendOfflineSubmitRequest:
        if self.job_kind is OfflineJobKind.REFLECT_EPISODE:
            ReflectEpisodeJobPayload.model_validate(self.payload)
        elif self.job_kind is OfflineJobKind.PROMOTE_SCHEMA:
            PromoteSchemaJobPayload.model_validate(self.payload)
        return self


class FrontendOfflineSubmitResult(FrontendModel):
    """Frontend-facing offline submission result projection."""

    job_id: str = Field(min_length=1)
    status: str = Field(min_length=1)


class FrontendExperienceCatalogEntry(FrontendModel):
    """Stable catalog entry for one experience entrypoint."""

    entrypoint: FrontendExperienceEntrypoint
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supported_viewports: list[str] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)
    requires_dev_mode: bool


class FrontendExperienceCatalogPage(FrontendModel):
    """Frontend-facing catalog of top-level experience entrypoints."""

    bench_version: str = Field(min_length=1)
    entries: list[FrontendExperienceCatalogEntry] = Field(default_factory=list)


class FrontendGateDemoEntryKind(StrEnum):
    """Stable gate/demo summary buckets for the frontend workbench."""

    DEMO = "demo"
    GATE = "gate"
    REPORT = "report"


class FrontendGateDemoEntry(FrontendModel):
    """One summary row for the frontend gate/demo workbench."""

    entry_id: str = Field(min_length=1)
    kind: FrontendGateDemoEntryKind
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supported_viewports: list[str] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)
    requires_dev_mode: bool = False


class FrontendGateDemoPage(FrontendModel):
    """Frozen gate/demo summary surface exposed to the lightweight frontend."""

    page_version: str = Field(min_length=1)
    entries: list[FrontendGateDemoEntry] = Field(default_factory=list)


def build_frontend_ingest_result(
    response_or_payload: AppResponse | Mapping[str, Any],
) -> FrontendIngestResult:
    """Project an ingest app response into the frontend-facing view."""

    payload, trace_ref = _coerce_ok_payload(response_or_payload)
    return FrontendIngestResult(
        object_id=str(payload["object_id"]),
        episode_id=str(payload["episode_id"]),
        version=int(payload["version"]),
        provenance_id=(
            str(payload["provenance_id"]) if payload.get("provenance_id") is not None else None
        ),
        trace_ref=trace_ref,
    )


def build_frontend_retrieve_result(
    response_or_payload: AppResponse | Mapping[str, Any],
) -> FrontendRetrieveResult:
    """Project a recall/search app response into the frontend-facing view."""

    payload, trace_ref = _coerce_ok_payload(response_or_payload)
    candidate_ids = [str(item) for item in payload.get("candidate_ids") or ()]
    scores = [float(item) for item in payload.get("scores") or ()]
    raw_summaries = payload.get("candidate_summaries") or payload.get("candidates") or ()
    candidates = _project_retrieve_candidates(
        raw_summaries,
        candidate_ids=candidate_ids,
        fallback_scores=scores,
    )
    return FrontendRetrieveResult(
        candidate_count=len(candidates),
        evidence_summary=payload.get("evidence_summary"),
        candidates=candidates,
        trace_ref=trace_ref,
    )


def build_frontend_access_result(
    response_or_payload: AppResponse | Mapping[str, Any],
    *,
    frontend_request: FrontendAccessRequest | None = None,
    runtime_provider: str | None = None,
) -> FrontendAccessResult:
    """Project an access app response into the frontend-facing view."""

    payload, trace_ref = _coerce_ok_payload(response_or_payload)
    candidate_ids = [str(item) for item in payload.get("candidate_ids") or ()]
    selected_ids = [str(item) for item in payload.get("selected_object_ids") or ()]
    candidate_objects = _project_evidence_collection(
        payload.get("candidate_summaries") or (),
        candidate_ids=candidate_ids,
    )
    selected_objects = _project_evidence_collection(
        payload.get("selected_summaries") or (),
        candidate_ids=selected_ids,
    )
    context_object_ids = [str(item) for item in payload.get("context_object_ids") or ()]
    trace = payload.get("trace") or {}
    events = trace.get("events") or ()
    answer = _project_access_answer(
        payload,
        fallback_support_ids=selected_ids,
        frontend_request=frontend_request,
        runtime_provider=runtime_provider,
    )
    summary = "access completed"
    if answer is not None:
        summary = answer.text
    elif events:
        last_event = events[-1]
        if isinstance(last_event, Mapping) and last_event.get("summary"):
            summary = str(last_event["summary"])
    return FrontendAccessResult(
        resolved_depth=_frontend_access_depth(payload.get("resolved_mode")),
        context_kind=str(payload.get("context_kind") or "unknown"),
        context_object_count=len(context_object_ids),
        candidate_count=len(candidate_objects),
        selected_count=len(selected_objects),
        summary=summary,
        answer=answer,
        candidate_objects=candidate_objects,
        selected_objects=selected_objects,
        trace_ref=trace_ref,
    )


def build_frontend_offline_submit_result(
    response_or_payload: AppResponse | Mapping[str, Any],
) -> FrontendOfflineSubmitResult:
    """Project an offline submission app response into the frontend-facing view."""

    payload, _ = _coerce_ok_payload(response_or_payload)
    return FrontendOfflineSubmitResult(
        job_id=str(payload["job_id"]),
        status=str(payload["status"]),
    )


def build_frontend_experience_catalog(
    scenarios: list[FrontendExperienceScenario] | None = None,
) -> FrontendExperienceCatalogPage:
    """Project the frozen experience bench into the frontend-facing catalog."""

    frozen_scenarios = scenarios or build_frontend_experience_bench_v1()
    grouped: dict[str, list[FrontendExperienceScenario]] = defaultdict(list)
    for scenario in frozen_scenarios:
        if scenario.category != "experience":
            continue
        grouped[scenario.entrypoint].append(scenario)

    ordered_entries = [
        FrontendExperienceEntrypoint.INGEST,
        FrontendExperienceEntrypoint.RETRIEVE,
        FrontendExperienceEntrypoint.ACCESS,
        FrontendExperienceEntrypoint.OFFLINE,
        FrontendExperienceEntrypoint.GATE_DEMO,
    ]
    entries: list[FrontendExperienceCatalogEntry] = []
    for entrypoint in ordered_entries:
        entry_scenarios = grouped.get(entrypoint.value, [])
        if not entry_scenarios:
            raise RuntimeError(f"missing frontend experience bench entrypoint {entrypoint.value}")
        entries.append(
            FrontendExperienceCatalogEntry(
                entrypoint=entrypoint,
                title=_ENTRYPOINT_TITLES[entrypoint],
                summary=_ENTRYPOINT_SUMMARIES[entrypoint],
                supported_viewports=_viewport_order(
                    {scenario.viewport for scenario in entry_scenarios}
                ),
                scenario_ids=[scenario.scenario_id for scenario in entry_scenarios],
                requires_dev_mode=any(scenario.requires_dev_mode for scenario in entry_scenarios),
            )
        )
    return FrontendExperienceCatalogPage(
        bench_version="FrontendExperienceBench v1",
        entries=entries,
    )


def build_frontend_gate_demo_page(
    scenarios: list[FrontendExperienceScenario] | None = None,
) -> FrontendGateDemoPage:
    """Project the frozen gate/demo frontend summary surface."""

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

    return FrontendGateDemoPage(
        page_version="FrontendGateDemoPage v1",
        entries=[
            FrontendGateDemoEntry(
                entry_id="demo_memory_flow",
                kind=FrontendGateDemoEntryKind.DEMO,
                title="Memory Flow Demo",
                summary=(
                    "Summarize the guided ingest/read path that mirrors the product memory "
                    "boundary without exposing raw developer commands."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="demo_access_flow",
                kind=FrontendGateDemoEntryKind.DEMO,
                title="Access Flow Demo",
                summary=(
                    "Summarize the access walkthrough that explains resolved depth, "
                    "context shape, and evidence selection."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="demo_offline_flow",
                kind=FrontendGateDemoEntryKind.DEMO,
                title="Offline Flow Demo",
                summary=(
                    "Summarize the offline submission path for reflection or schema "
                    "promotion without changing runtime semantics implicitly."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="gate_capability_readiness",
                kind=FrontendGateDemoEntryKind.GATE,
                title="Capability Readiness Gate",
                summary=(
                    "Expose the capability-layer readiness checkpoint as a stable frontend "
                    "summary instead of a developer-facing phase command."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="gate_telemetry_readiness",
                kind=FrontendGateDemoEntryKind.GATE,
                title="Telemetry Readiness Gate",
                summary=(
                    "Expose telemetry coverage and debug-safety readiness as a frontend "
                    "summary for internal review."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="report_provider_compatibility",
                kind=FrontendGateDemoEntryKind.REPORT,
                title="Provider Compatibility Report",
                summary=(
                    "Summarize provider compatibility artifacts for the capability layer "
                    "without binding the UI to raw report file formats."
                ),
                supported_viewports=supported_viewports,
                scenario_ids=scenario_ids,
            ),
            FrontendGateDemoEntry(
                entry_id="report_telemetry_audit",
                kind=FrontendGateDemoEntryKind.REPORT,
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
    if isinstance(response_or_payload, AppResponse):
        if response_or_payload.status is not AppStatus.OK or response_or_payload.result is None:
            raise ValueError("frontend projections require an AppResponse with status=ok")
        return dict(response_or_payload.result), response_or_payload.trace_ref
    return dict(response_or_payload), None


def _project_evidence_collection(
    raw_summaries: Any,
    *,
    candidate_ids: list[str],
    fallback_scores: list[float] | None = None,
) -> list[FrontendAccessEvidenceView]:
    fallback_scores = fallback_scores or []
    if not raw_summaries:
        return [
            FrontendAccessEvidenceView(
                object_id=object_id,
                object_type="unknown",
                score=fallback_scores[index] if index < len(fallback_scores) else None,
            )
            for index, object_id in enumerate(candidate_ids)
        ]

    views: list[FrontendAccessEvidenceView] = []
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
            FrontendAccessEvidenceView(
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
    raw_text = payload.get("answer_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None

    raw_trace = payload.get("answer_trace")
    answer_trace: FrontendAccessAnswerTraceView | None = None
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
        answer_trace = FrontendAccessAnswerTraceView(
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
        answer_trace = FrontendAccessAnswerTraceView(
            provider_family=provider_family,
            request_text=request_text,
            response_text=response_text,
            exchanges=exchanges,
        )

    raw_support_ids = payload.get("answer_support_ids") or fallback_support_ids
    return FrontendAccessAnswerView(
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
    if isinstance(raw_trace, Mapping):
        raw_exchanges = raw_trace.get("exchanges")
        if isinstance(raw_exchanges, list):
            exchanges: list[FrontendAccessLlmExchangeView] = []
            for index, item in enumerate(raw_exchanges, start=1):
                if not isinstance(item, Mapping):
                    continue
                exchange_request = _format_frontend_access_trace_text(item.get("request_text"))
                exchange_response = _format_frontend_access_trace_text(item.get("response_text"))
                if not exchange_request and not exchange_response:
                    continue
                exchanges.append(
                    FrontendAccessLlmExchangeView(
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
        FrontendAccessLlmExchangeView(
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
    fallback_scores = fallback_scores or []
    if not raw_summaries:
        return [
            FrontendRetrieveCandidateView(
                object_id=object_id,
                object_type="unknown",
                score=fallback_scores[index] if index < len(fallback_scores) else None,
            )
            for index, object_id in enumerate(candidate_ids)
        ]

    views: list[FrontendRetrieveCandidateView] = []
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
            FrontendRetrieveCandidateView(
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


_ENTRYPOINT_TITLES = {
    FrontendExperienceEntrypoint.INGEST: "Ingest",
    FrontendExperienceEntrypoint.RETRIEVE: "Retrieve",
    FrontendExperienceEntrypoint.ACCESS: "Access",
    FrontendExperienceEntrypoint.OFFLINE: "Offline Jobs",
    FrontendExperienceEntrypoint.GATE_DEMO: "Gate / Demo",
}

_ENTRYPOINT_SUMMARIES = {
    FrontendExperienceEntrypoint.INGEST: (
        "Store one memory through the product boundary and return the created object id."
    ),
    FrontendExperienceEntrypoint.RETRIEVE: (
        "Run ranked recall against stored memories and return compact candidate summaries."
    ),
    FrontendExperienceEntrypoint.ACCESS: (
        "Run ask/access and surface resolved depth, context shape, and selected evidence."
    ),
    FrontendExperienceEntrypoint.OFFLINE: (
        "Submit offline maintenance jobs without changing runtime semantics implicitly."
    ),
    FrontendExperienceEntrypoint.GATE_DEMO: (
        "Expose gate, report, and demo entry summaries "
        "without coupling the UI to raw developer CLI."
    ),
}

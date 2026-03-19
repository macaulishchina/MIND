"""Frontend-facing lifecycle benchmark contracts and projections."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

from pydantic import Field

from mind.app.contracts import AppResponse, FrontendModel
from mind.app.frontend_experience_helpers import _coerce_ok_payload


class FrontendMemoryLifecycleBenchmarkLaunchRequest(FrontendModel):
    """Frontend-facing lifecycle benchmark launch request."""

    dataset_name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)


class FrontendMemoryLifecycleBenchmarkQueryRequest(FrontendModel):
    """Frontend-facing lifecycle benchmark report query."""

    run_id: str | None = None


class FrontendMemoryLifecycleBenchmarkWorkspaceQuery(FrontendModel):
    """Frontend-facing lifecycle benchmark workspace query."""


class FrontendMemoryLifecycleBenchmarkDatasetOption(FrontendModel):
    """One dataset option shown in the benchmark workspace."""

    dataset_name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    supported_outputs: list[str] = Field(default_factory=list)
    default_slice_path: str | None = None
    default_raw_source_path: str | None = None
    default_output_path: str | None = None
    raw_source_kind: str = Field(min_length=1)
    selector_kind: str | None = None
    selector_label: str | None = None
    selector_placeholder: str | None = None


class FrontendMemoryLifecycleBenchmarkRawSourceOption(FrontendModel):
    """One raw source option that can be compiled into a local slice."""

    dataset_name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    path_kind: str = Field(min_length=1)


class FrontendMemoryLifecycleBenchmarkSliceOption(FrontendModel):
    """One local slice option available to run through the benchmark."""

    dataset_name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    bundle_count: int = Field(ge=0)
    updated_at: str | None = None


class FrontendMemoryLifecycleBenchmarkReportOption(FrontendModel):
    """One persisted benchmark report option."""

    run_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    is_latest: bool = False


class FrontendMemoryLifecycleBenchmarkWorkspaceResult(FrontendModel):
    """Frontend-facing workspace metadata for the lifecycle benchmark page."""

    datasets: list[FrontendMemoryLifecycleBenchmarkDatasetOption] = Field(default_factory=list)
    raw_sources: list[FrontendMemoryLifecycleBenchmarkRawSourceOption] = Field(default_factory=list)
    slice_options: list[FrontendMemoryLifecycleBenchmarkSliceOption] = Field(default_factory=list)
    report_options: list[FrontendMemoryLifecycleBenchmarkReportOption] = Field(default_factory=list)
    default_dataset_name: str | None = None
    default_slice_path: str | None = None
    default_raw_source_path: str | None = None
    default_output_path: str | None = None
    default_report_run_id: str | None = None


class FrontendMemoryLifecycleBenchmarkSliceGenerationRequest(FrontendModel):
    """Frontend-facing request for compiling a raw public dataset slice."""

    dataset_name: str = Field(min_length=1)
    raw_source_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    selector_values: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1)


class FrontendMemoryLifecycleBenchmarkSliceGenerationResult(FrontendModel):
    """Frontend-facing result for one compiled local slice."""

    dataset_name: str = Field(min_length=1)
    raw_source_path: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    bundle_count: int = Field(ge=0)
    sequence_count: int = Field(ge=0)
    selector_kind: str | None = None
    selector_values: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1)


class FrontendMemoryLifecycleAskMetricsView(FrontendModel):
    """Frontend-facing ask metrics for one lifecycle stage."""

    answer_case_count: int = Field(ge=0)
    average_answer_quality: float = Field(ge=0)
    task_success_rate: float = Field(ge=0)
    candidate_hit_rate: float = Field(ge=0)
    selected_hit_rate: float = Field(ge=0)
    reuse_rate: float = Field(ge=0)
    pollution_rate: float = Field(ge=0)


class FrontendMemoryLifecycleMemorySnapshotView(FrontendModel):
    """Frontend-facing memory footprint snapshot for one stage."""

    active_object_count: int = Field(ge=0)
    total_object_versions: int = Field(ge=0)
    active_object_counts: dict[str, int] = Field(default_factory=dict)


class FrontendMemoryLifecycleCostSnapshotView(FrontendModel):
    """Frontend-facing cost snapshot for one stage."""

    total_cost: float = Field(ge=0)
    generation_cost: float = Field(ge=0)
    maintenance_cost: float = Field(ge=0)
    retrieval_cost: float = Field(ge=0)
    read_cost: float = Field(ge=0)
    write_cost: float = Field(ge=0)
    storage_cost: float = Field(ge=0)
    offline_job_count: int = Field(ge=0)


class FrontendMemoryLifecycleStageView(FrontendModel):
    """Frontend-facing lifecycle benchmark stage projection."""

    stage_name: str = Field(min_length=1)
    ask: FrontendMemoryLifecycleAskMetricsView
    memory: FrontendMemoryLifecycleMemorySnapshotView
    cost: FrontendMemoryLifecycleCostSnapshotView
    operation_notes: list[str] = Field(default_factory=list)


class FrontendMemoryLifecycleBenchmarkResult(FrontendModel):
    """Frontend-facing lifecycle benchmark report projection."""

    dataset_name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    fixture_name: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    telemetry_path: str | None = None
    store_path: str | None = None
    bundle_count: int = Field(ge=0)
    answer_case_count: int = Field(ge=0)
    stage_count: int = Field(ge=0)
    latest_stage_name: str = Field(min_length=1)
    frontend_debug_query: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    stage_reports: list[FrontendMemoryLifecycleStageView] = Field(default_factory=list)


class _ReportLike(Protocol):
    dataset_name: str
    source_path: str
    fixture_name: str
    run_id: str
    telemetry_path: str | None
    store_path: str | None
    bundle_count: int
    answer_case_count: int
    frontend_debug_query: Mapping[str, str]
    notes: tuple[str, ...]
    stage_reports: tuple[Any, ...]


def build_frontend_memory_lifecycle_benchmark_workspace_result(
    payload: Mapping[str, Any] | object,
) -> FrontendMemoryLifecycleBenchmarkWorkspaceResult:
    """Validate and project benchmark workspace metadata for the web UI."""

    mapping = dict(payload if isinstance(payload, Mapping) else cast(Mapping[str, Any], payload))
    return FrontendMemoryLifecycleBenchmarkWorkspaceResult(
        datasets=[
            FrontendMemoryLifecycleBenchmarkDatasetOption.model_validate(item)
            for item in mapping.get("datasets", ())
        ],
        raw_sources=[
            FrontendMemoryLifecycleBenchmarkRawSourceOption.model_validate(item)
            for item in mapping.get("raw_sources", ())
        ],
        slice_options=[
            FrontendMemoryLifecycleBenchmarkSliceOption.model_validate(item)
            for item in mapping.get("slice_options", ())
        ],
        report_options=[
            FrontendMemoryLifecycleBenchmarkReportOption.model_validate(item)
            for item in mapping.get("report_options", ())
        ],
        default_dataset_name=_optional_string(mapping.get("default_dataset_name")),
        default_slice_path=_optional_string(mapping.get("default_slice_path")),
        default_raw_source_path=_optional_string(mapping.get("default_raw_source_path")),
        default_output_path=_optional_string(mapping.get("default_output_path")),
        default_report_run_id=_optional_string(mapping.get("default_report_run_id")),
    )


def build_frontend_memory_lifecycle_benchmark_slice_generation_result(
    payload: Mapping[str, Any] | object,
) -> FrontendMemoryLifecycleBenchmarkSliceGenerationResult:
    """Validate and project one compiled local slice result."""

    mapping = dict(payload if isinstance(payload, Mapping) else cast(Mapping[str, Any], payload))
    return FrontendMemoryLifecycleBenchmarkSliceGenerationResult(
        dataset_name=str(mapping["dataset_name"]),
        raw_source_path=str(mapping["raw_source_path"]),
        source_path=str(mapping["source_path"]),
        bundle_count=int(mapping["bundle_count"]),
        sequence_count=int(mapping["sequence_count"]),
        selector_kind=_optional_string(mapping.get("selector_kind")),
        selector_values=[str(item) for item in mapping.get("selector_values", ())],
        max_items=int(mapping["max_items"]) if mapping.get("max_items") is not None else None,
    )


def build_frontend_memory_lifecycle_benchmark_result(
    response_or_payload: AppResponse | Mapping[str, Any] | object,
) -> FrontendMemoryLifecycleBenchmarkResult:
    """Project a lifecycle benchmark report into the frontend-facing view."""

    payload, _ = _coerce_report_payload(response_or_payload)
    stage_reports = [
        FrontendMemoryLifecycleStageView(
            stage_name=str(stage["stage_name"]),
            ask=FrontendMemoryLifecycleAskMetricsView.model_validate(stage["ask"]),
            memory=FrontendMemoryLifecycleMemorySnapshotView.model_validate(stage["memory"]),
            cost=FrontendMemoryLifecycleCostSnapshotView.model_validate(stage["cost"]),
            operation_notes=[str(item) for item in stage.get("operation_notes", ())],
        )
        for stage in payload.get("stage_reports", ())
    ]
    if not stage_reports:
        raise ValueError("lifecycle benchmark frontend projection requires at least one stage")
    return FrontendMemoryLifecycleBenchmarkResult(
        dataset_name=str(payload["dataset_name"]),
        source_path=str(payload["source_path"]),
        fixture_name=str(payload["fixture_name"]),
        run_id=str(payload["run_id"]),
        report_path=str(payload["report_path"]),
        telemetry_path=(
            str(payload["telemetry_path"])
            if payload.get("telemetry_path") is not None
            else None
        ),
        store_path=str(payload["store_path"]) if payload.get("store_path") is not None else None,
        bundle_count=int(payload["bundle_count"]),
        answer_case_count=int(payload["answer_case_count"]),
        stage_count=len(stage_reports),
        latest_stage_name=stage_reports[-1].stage_name,
        frontend_debug_query={
            str(key): str(value)
            for key, value in dict(payload.get("frontend_debug_query") or {}).items()
        },
        notes=[str(item) for item in payload.get("notes", ())],
        stage_reports=stage_reports,
    )


def _coerce_report_payload(
    response_or_payload: AppResponse | Mapping[str, Any] | object,
) -> tuple[dict[str, Any], str | None]:
    if not isinstance(response_or_payload, AppResponse | Mapping):
        return _report_to_payload(cast(_ReportLike, response_or_payload)), None
    payload, trace_ref = _coerce_ok_payload(response_or_payload)
    return dict(payload), trace_ref


def _report_to_payload(report: _ReportLike) -> dict[str, Any]:
    return {
        "dataset_name": report.dataset_name,
        "source_path": report.source_path,
        "fixture_name": report.fixture_name,
        "run_id": report.run_id,
        "report_path": "",
        "telemetry_path": report.telemetry_path,
        "store_path": report.store_path,
        "bundle_count": report.bundle_count,
        "answer_case_count": report.answer_case_count,
        "frontend_debug_query": dict(report.frontend_debug_query),
        "notes": list(report.notes),
        "stage_reports": [
            {
                "stage_name": stage.stage_name,
                "ask": {
                    "answer_case_count": stage.ask.answer_case_count,
                    "average_answer_quality": stage.ask.average_answer_quality,
                    "task_success_rate": stage.ask.task_success_rate,
                    "candidate_hit_rate": stage.ask.candidate_hit_rate,
                    "selected_hit_rate": stage.ask.selected_hit_rate,
                    "reuse_rate": stage.ask.reuse_rate,
                    "pollution_rate": stage.ask.pollution_rate,
                },
                "memory": {
                    "active_object_count": stage.memory.active_object_count,
                    "total_object_versions": stage.memory.total_object_versions,
                    "active_object_counts": dict(stage.memory.active_object_counts),
                },
                "cost": {
                    "total_cost": stage.cost.total_cost,
                    "generation_cost": stage.cost.generation_cost,
                    "maintenance_cost": stage.cost.maintenance_cost,
                    "retrieval_cost": stage.cost.retrieval_cost,
                    "read_cost": stage.cost.read_cost,
                    "write_cost": stage.cost.write_cost,
                    "storage_cost": stage.cost.storage_cost,
                    "offline_job_count": stage.cost.offline_job_count,
                },
                "operation_notes": list(stage.operation_notes),
            }
            for stage in report.stage_reports
        ],
    }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
